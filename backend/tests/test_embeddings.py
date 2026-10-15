import sys
import types

import pytest

from embeddings import generate
from tests.conftest import TEST_API_KEY


@pytest.fixture
def nim_env(configure, nim):
    def apply(**extra):
        return configure(NVIDIA_API_KEY=TEST_API_KEY, NVIDIA_BASE_URL=nim.base_url, **extra)

    return apply


def test_batches_requests_and_preserves_order(nim_env, nim):
    nim_env(EMBEDDING_BATCH_SIZE="2")
    texts = [f"unique{i} token" for i in range(5)]
    vectors = generate.get_embeddings(texts)
    assert len(vectors) == 5 and all(len(v) == 1024 for v in vectors)
    assert [len(r["input"]) for r in nim.embedding_requests] == [2, 2, 1]
    # order preserved: each vector equals the standalone embedding of the same text
    again = generate.get_embeddings([texts[3]])[0]
    assert again == vectors[3]


def test_passages_and_queries_use_distinct_input_types(nim_env, nim):
    nim_env()
    generate.get_embeddings(["a doc"])
    generate.get_query_embedding("a question")
    assert [r["input_type"] for r in nim.embedding_requests] == ["passage", "query"]
    assert all(r["model"] == "nvidia/nv-embedqa-e5-v5" for r in nim.embedding_requests)


def test_symmetric_models_do_not_receive_input_type(nim_env, nim):
    nim_env(NVIDIA_EMBEDDING_ASYMMETRIC="false", EMBEDDING_MODEL="acme/gte-like", EMBEDDING_DIMENSION="1024")
    generate.get_embeddings(["x"])
    assert "input_type" not in nim.embedding_requests[0] and "truncate" not in nim.embedding_requests[0]


def test_blank_text_is_embeddable_and_empty_list_is_free(nim_env, nim):
    nim_env()
    assert generate.get_embeddings([]) == [] and not nim.embedding_requests
    assert len(generate.get_embeddings(["   "])[0]) == 1024


def test_wrong_dimension_and_api_errors_raise_embedding_error(nim_env, nim):
    nim_env()
    nim.embed_dim = 8
    with pytest.raises(generate.EmbeddingError, match="EMBEDDING_DIMENSION"):
        generate.get_embeddings(["x"])
    nim.reset()
    nim.fail = {"status": 401, "remaining": 5, "path": "/embeddings"}
    with pytest.raises(generate.EmbeddingError, match="NVIDIA_API_KEY"):
        generate.get_embeddings(["x"])


def test_local_provider_uses_sentence_transformers_without_network(configure, monkeypatch):
    """The optional in-container provider, exercised with a stand-in for the real model."""
    calls = {}

    class FakeArray(list):
        def tolist(self):
            return list(self)

    class FakeModel:
        def __init__(self, name):
            calls["name"] = name

        def encode(self, texts, **kwargs):
            calls["n"] = len(texts)
            return FakeArray([[0.5] * 384 for _ in texts])

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = FakeModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    generate._local_model.cache_clear()

    s = configure(EMBEDDING_PROVIDER="local")
    assert s.embedding_dimension == 384
    vectors = generate.get_embeddings(["one", "two"])
    assert len(vectors) == 2 and len(vectors[0]) == 384
    assert calls == {"name": "sentence-transformers/all-MiniLM-L6-v2", "n": 2}
    assert len(generate.get_query_embedding("q")) == 384
    generate._local_model.cache_clear()


def test_local_provider_without_package_gives_actionable_error(configure, monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)  # simulate "not installed"
    generate._local_model.cache_clear()
    configure(EMBEDDING_PROVIDER="local")
    with pytest.raises(generate.EmbeddingError, match="EMBEDDINGS=local"):
        generate.get_embeddings(["x"])
    generate._local_model.cache_clear()
