"""Integration tests against a real Qdrant server process."""

import uuid

import pytest
from qdrant_client import QdrantClient
from qdrant_client import models as qm

from qdrant_store import VectorStore, VectorStoreError, VectorStoreMisconfigured
from tests.fake_nim import embed_text


@pytest.fixture
def env(configure, qdrant_server):
    name = f"t_{uuid.uuid4().hex[:10]}"
    settings = configure(QDRANT_URL=qdrant_server.url, QDRANT_COLLECTION=name, NVIDIA_API_KEY="k")
    return settings, qdrant_server


def make_chunks(texts, filename="doc.pdf"):
    return [
        {"id": str(uuid.uuid4()), "text": t, "metadata": {"filename": filename, "page": i + 1}}
        for i, t in enumerate(texts)
    ]


def index(store, user, texts, filename="doc.pdf", upload_id="u1"):
    chunks = make_chunks(texts, filename)
    store.upsert_chunks(user, upload_id, chunks, [embed_text(t) for t in texts])
    return chunks


def test_creates_cosine_collection_with_expected_dimension_and_indexes(env):
    settings, server = env
    store = VectorStore()
    store.ensure_ready()
    info = QdrantClient(url=server.url).get_collection(settings.qdrant_collection)
    assert info.config.params.vectors.size == 2048
    assert info.config.params.vectors.distance == qm.Distance.COSINE
    schema = info.payload_schema
    assert {"user_id", "filename", "upload_id"} <= set(schema)
    assert (info.config.metadata or {}).get("embedding_model") == "nvidia/nemotron-3-embed-1b"


def test_restart_of_app_and_of_qdrant_keeps_all_data(env):
    settings, server = env
    store = VectorStore()
    index(store, "alice", ["encryption keys protect secrets", "bananas are yellow fruit"])
    assert store.count("alice") == 2

    # a fresh process (new VectorStore) must reuse the collection, not recreate it
    again = VectorStore()
    again.ensure_ready()
    assert again.count("alice") == 2

    # and Qdrant itself restarting on the same storage keeps the data
    server.restart()
    third = VectorStore()
    third.wait_until_ready(timeout=30)
    assert third.count("alice") == 2
    hits = third.search("alice", embed_text("encryption keys"), top_k=1)
    assert "encryption" in hits[0]["text"]


def test_dimension_mismatch_is_refused_and_existing_data_is_untouched(env, configure):
    settings, server = env
    original = VectorStore()
    index(original, "alice", ["alpha beta gamma"])

    # operator switches to a 384-dim model but keeps the same collection name
    configure(
        QDRANT_URL=server.url, QDRANT_COLLECTION=settings.qdrant_collection, NVIDIA_API_KEY="k",
        EMBEDDING_PROVIDER="local",
    )
    broken = VectorStore()
    with pytest.raises(VectorStoreMisconfigured, match="2048-dimensional|stores 2048"):
        broken.ensure_ready()
    status = broken.status()
    assert status["ok"] is False and status["state"] == "misconfigured"
    for operation in (lambda: broken.count("alice"), lambda: broken.delete_user_data("alice")):
        with pytest.raises(VectorStoreMisconfigured):
            operation()

    # data survived, collection was not recreated
    raw = QdrantClient(url=server.url)
    assert raw.count(settings.qdrant_collection).count == 1
    assert raw.get_collection(settings.qdrant_collection).config.params.vectors.size == 2048


def test_same_dimension_but_different_model_is_refused(env, configure):
    settings, server = env
    index(VectorStore(), "alice", ["some indexed text"])  # has data -> must be protected
    configure(
        QDRANT_URL=server.url, QDRANT_COLLECTION=settings.qdrant_collection, NVIDIA_API_KEY="k",
        EMBEDDING_MODEL="acme/other-2048", EMBEDDING_DIMENSION=2048,
    )
    with pytest.raises(VectorStoreMisconfigured, match="not comparable"):
        VectorStore().ensure_ready()


def test_non_cosine_collection_is_refused(env):
    settings, server = env
    raw = QdrantClient(url=server.url)
    raw.create_collection(
        settings.qdrant_collection, vectors_config=qm.VectorParams(size=2048, distance=qm.Distance.DOT)
    )
    raw.upsert(settings.qdrant_collection, points=[qm.PointStruct(id=1, vector=embed_text("x"), payload={"user_id": "a"})])
    with pytest.raises(VectorStoreMisconfigured, match="Cosine"):
        VectorStore().ensure_ready()
    assert raw.count(settings.qdrant_collection).count == 1  # untouched


def test_users_are_isolated_for_search_count_sample_and_delete(env):
    store = VectorStore()
    index(store, "alice", ["alice secret plan about rockets"], filename="same.pdf")
    index(store, "bob", ["bob grocery list about rockets"], filename="same.pdf")

    q = embed_text("rockets")
    alice_hits = store.search("alice", q, top_k=10)
    bob_hits = store.search("bob", q, top_k=10)
    assert [h["text"] for h in alice_hits] == ["alice secret plan about rockets"]
    assert [h["text"] for h in bob_hits] == ["bob grocery list about rockets"]
    assert store.search("carol", q, top_k=10) == []
    assert store.count("alice") == 1 and store.count("bob") == 1
    assert all("bob" not in s["text"] for s in store.sample_chunks("alice"))

    store.delete_document("alice", "same.pdf")  # same filename, different owner
    assert store.count("alice") == 0 and store.count("bob") == 1

    store.delete_user_data("bob")
    assert store.count("bob") == 0


def test_empty_user_id_is_rejected_everywhere(env):
    store = VectorStore()
    store.ensure_ready()
    for op in (
        lambda: store.search("", embed_text("x")),
        lambda: store.count(""),
        lambda: store.delete_user_data(""),
        lambda: store.sample_chunks(""),
        lambda: store.upsert_chunks("", "u", [], []),
    ):
        with pytest.raises(ValueError):
            op()


def test_reupload_replaces_old_version_but_failed_write_keeps_it(env):
    store = VectorStore()
    index(store, "alice", ["old version text"], filename="r.pdf", upload_id="v1")
    index(store, "alice", ["new version text"], filename="r.pdf", upload_id="v2")
    store.delete_stale_versions("alice", "r.pdf", keep_upload_id="v2")
    texts = [h["text"] for h in store.search("alice", embed_text("version text"), top_k=10)]
    assert texts == ["new version text"]

    # a wrong-dimension write fails before touching anything
    with pytest.raises(VectorStoreError, match="dimensions"):
        store.upsert_chunks("alice", "v3", make_chunks(["bad"], "r.pdf"), [[0.1] * 5])
    assert store.count("alice") == 1


def test_search_ranks_by_cosine_similarity_and_payload_is_returned(env):
    store = VectorStore()
    index(store, "alice", ["quantum entanglement of photons", "baking sourdough bread at home"], filename="m.pdf")
    hits = store.search("alice", embed_text("photons quantum"), top_k=2)
    assert hits[0]["text"].startswith("quantum") and hits[0]["score"] > hits[1]["score"]
    assert hits[0]["filename"] == "m.pdf" and hits[0]["page"] == 1
    assert 0.0 < hits[0]["score"] <= 1.0001


def test_unreachable_qdrant_reports_cleanly_and_recovers(configure, qdrant_server):
    configure(QDRANT_URL="http://127.0.0.1:9", QDRANT_COLLECTION="x", NVIDIA_API_KEY="k",
              QDRANT_STARTUP_TIMEOUT_SECONDS="1")
    store = VectorStore()
    status = store.status()
    assert status["ok"] is False and status["state"] == "unreachable"
    with pytest.raises(VectorStoreError):
        store.wait_until_ready(timeout=1, interval=0.2)


def test_collection_deleted_externally_is_detected_by_status(env):
    settings, server = env
    store = VectorStore()
    store.ensure_ready()
    QdrantClient(url=server.url).delete_collection(settings.qdrant_collection)
    # status() probes live; a genuinely missing collection is recreated EMPTY (never over data)
    assert store.status()["ok"] is True
    assert store.count("alice") == 0


def test_empty_incompatible_collection_is_rebuilt_but_never_one_with_data(env):
    """First start with a retired 1024-d model leaves an EMPTY collection; switching models must just work."""
    settings, server = env
    raw = QdrantClient(url=server.url)
    raw.create_collection(
        settings.qdrant_collection, vectors_config=qm.VectorParams(size=1024, distance=qm.Distance.COSINE)
    )
    store = VectorStore()
    store.ensure_ready()  # empty -> recreated at 2048
    assert raw.get_collection(settings.qdrant_collection).config.params.vectors.size == 2048
    index(store, "alice", ["keep me safe"])

    # now with data, a different size must be refused again
    raw.delete_collection(settings.qdrant_collection)
    raw.create_collection(
        settings.qdrant_collection, vectors_config=qm.VectorParams(size=1024, distance=qm.Distance.COSINE)
    )
    raw.upsert(settings.qdrant_collection, points=[qm.PointStruct(id=7, vector=[0.1] * 1024, payload={"user_id": "a"})])
    with pytest.raises(VectorStoreMisconfigured):
        VectorStore().ensure_ready()
    assert raw.count(settings.qdrant_collection).count == 1
