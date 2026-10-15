"""End-to-end API tests: real Qdrant + real FastAPI app + fake NIM over HTTP."""

import time

from qdrant_store import get_store
from tests.conftest import TEST_API_KEY

CRYPTO = "Cryptography uses public key encryption and symmetric encryption to protect confidential data in transit."
COOKING = "Sourdough bread needs flour water salt and a long fermentation with wild yeast starter culture."


def upload(client, pdf_bytes, name="crypto.pdf", chunk_size=None):
    params = {"chunk_size": chunk_size} if chunk_size else {}
    return client.post("/api/upload", params=params, files=[("files", (name, pdf_bytes, "application/pdf"))])


def test_health_reports_ready_stack_without_secrets(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["app"] == "Vectora"
    assert body["vector_store"]["state"] == "ready" and body["vector_store"]["distance"] == "Cosine"
    assert body["llm"]["model"] == "meta/llama-3.3-70b-instruct"
    assert body["embeddings"]["dimension"] == 2048
    assert body["embeddings"]["model"] == "nvidia/nemotron-3-embed-1b"
    assert TEST_API_KEY not in client.get("/api/health").text


def test_health_is_503_when_key_missing_but_app_still_serves(client, configure, qdrant_server):
    import config

    config.get_settings.cache_clear()
    import os

    os.environ["NVIDIA_API_KEY"] = ""
    try:
        response = client.get("/api/health")
        assert response.status_code == 503
        assert "NVIDIA_API_KEY" in response.json()["message"]
        assert client.get("/api/chats").status_code == 200  # app itself keeps serving
    finally:
        os.environ["NVIDIA_API_KEY"] = TEST_API_KEY
        config.get_settings.cache_clear()


def test_session_cookie_is_httponly_signed_and_reused(client):
    r = client.get("/api/session")
    set_cookie = r.headers["set-cookie"]
    assert "vectora_session=" in set_cookie and "HttpOnly" in set_cookie and "SameSite=lax" in set_cookie
    assert "Secure" not in set_cookie  # plain http locally
    before = client.cookies.get("vectora_session")
    client.get("/api/chats")
    assert client.cookies.get("vectora_session") == before  # same identity afterwards


def test_cookie_is_secure_behind_https_proxy(client):
    r = client.get("/api/session", headers={"X-Forwarded-Proto": "https"})
    assert "Secure" in r.headers["set-cookie"]


def test_forged_cookie_gets_a_fresh_identity_not_someone_elses(client, second_client, make_pdf):
    assert upload(client, make_pdf([CRYPTO])).json()["results"][0]["status"] == "success"
    victim_id = client.cookies.get("vectora_session").split(".")[0]
    second_client.cookies.set("vectora_session", f"{victim_id}.forgedsignature")
    assert second_client.get("/api/documents").json() == []


def test_upload_index_search_and_answer_roundtrip(client, nim, make_pdf):
    result = upload(client, make_pdf([CRYPTO, COOKING])).json()["results"][0]
    assert result["status"] == "success" and result["chunks"] == 2
    assert result["chunk_size_applied"] == 500  # UI/default value, within the embedding window

    docs = client.get("/api/documents").json()
    assert [(d["filename"], d["status"], d["chunks"]) for d in docs] == [("crypto.pdf", "success", 2)]
    assert docs[0]["created_at"].endswith("Z")

    # embeddings were requested as passages for indexing, and as a query for search
    assert {r["input_type"] for r in nim.embedding_requests} == {"passage"}
    reply = client.post("/api/chat", json={"query": "How does public key encryption protect data?"}).json()
    assert nim.embedding_requests[-1]["input_type"] == "query"

    assert "Cryptography uses public key encryption" in reply["answer"]  # grounded in retrieved chunk
    assert "<think>" not in reply["answer"] and not reply["answer"].startswith("Answer:")
    assert "[Source 1] crypto.pdf (page 1)" in reply["context"]
    assert "Sourdough" not in reply["context"]  # irrelevant page filtered by score threshold
    assert reply["title"] == "Fake Chat Title"

    stats = client.get("/api/vector-store/stats").json()
    assert stats["total_vectors"] == 2 and stats["distance"] == "Cosine" and stats["dimension"] == 2048


def test_rag_disabled_skips_retrieval_and_returns_no_context(client, nim, make_pdf):
    upload(client, make_pdf([CRYPTO]))
    n = len(nim.embedding_requests)
    reply = client.post("/api/chat", json={"query": "hello there", "rag_enabled": False}).json()
    assert reply["context"] is None and len(nim.embedding_requests) == n
    assert "No document context was provided." in nim.chat_requests[0]["messages"][-1]["content"]


def test_chat_history_is_persisted_and_sent_to_the_model(client, nim):
    first = client.post("/api/chat", json={"query": "first question", "rag_enabled": False}).json()
    second = client.post(
        "/api/chat", json={"query": "second question", "chat_id": first["chat_id"], "rag_enabled": False}
    ).json()
    assert second["chat_id"] == first["chat_id"]
    sent = [m["content"] for m in nim.chat_requests[-1]["messages"]]
    assert "first question" in sent and nim.chat_requests[-1]["messages"][0]["role"] == "system"

    chat = client.get(f"/api/chat/{first['chat_id']}").json()
    assert [m["role"] for m in chat["messages"]] == ["user", "assistant", "user", "assistant"]
    assert [c["chat_id"] for c in client.get("/api/chats").json()] == [first["chat_id"]]


def test_chat_created_at_is_stable_and_list_orders_by_activity(client):
    a = client.post("/api/chat", json={"query": "chat A", "rag_enabled": False}).json()["chat_id"]
    created = client.get("/api/chats").json()[0]["created_at"]
    time.sleep(1.1)
    b = client.post("/api/chat", json={"query": "chat B", "rag_enabled": False}).json()["chat_id"]
    time.sleep(1.1)
    client.post("/api/chat", json={"query": "again", "chat_id": a, "rag_enabled": False})
    chats = client.get("/api/chats").json()
    assert [c["chat_id"] for c in chats] == [a, b]  # most recently active first
    assert [c for c in chats if c["chat_id"] == a][0]["created_at"] == created  # not reset by new messages


def test_users_cannot_see_or_use_each_others_documents_chats_or_vectors(client, second_client, make_pdf):
    upload(client, make_pdf([CRYPTO]), name="private.pdf")
    chat_id = client.post("/api/chat", json={"query": "about encryption"}).json()["chat_id"]

    assert second_client.get("/api/documents").json() == []
    assert second_client.get("/api/chats").json() == []
    assert second_client.get(f"/api/chat/{chat_id}").status_code == 404
    assert second_client.delete(f"/api/chat/{chat_id}").status_code == 404
    assert second_client.post("/api/chat", json={"query": "x", "chat_id": chat_id}).status_code == 404
    assert second_client.get("/api/vector-store/stats").json()["total_vectors"] == 0

    # the other user's semantic search finds nothing from the first user's PDF
    reply = second_client.post("/api/chat", json={"query": "public key encryption data"}).json()
    assert "Cryptography" not in reply["answer"] and reply["context"] == "No relevant context found."

    # same filename for both users is allowed and independent
    upload(second_client, make_pdf([COOKING]), name="private.pdf")
    assert len(client.get("/api/documents").json()) == 1 and len(second_client.get("/api/documents").json()) == 1
    doc_id = client.get("/api/documents").json()[0]["id"]
    assert second_client.delete(f"/api/documents/{doc_id}").status_code == 404  # not theirs
    assert client.get("/api/vector-store/stats").json()["total_vectors"] == 1


def test_clear_wipes_only_the_callers_data(client, second_client, make_pdf):
    upload(client, make_pdf([CRYPTO]), name="a.pdf")
    upload(second_client, make_pdf([COOKING]), name="b.pdf")
    assert client.post("/api/vector-store/clear").json() == {"status": "success"}
    assert client.get("/api/vector-store/stats").json()["total_vectors"] == 0
    assert client.get("/api/documents").json() == []  # registry stays consistent with the index
    assert second_client.get("/api/vector-store/stats").json()["total_vectors"] == 1
    assert len(second_client.get("/api/documents").json()) == 1
    assert get_store().status()["ok"]  # collection itself still exists


def test_delete_document_removes_vectors_and_registry(client, make_pdf):
    upload(client, make_pdf([CRYPTO]), name="a.pdf")
    upload(client, make_pdf([COOKING]), name="b.pdf")
    doc = [d for d in client.get("/api/documents").json() if d["filename"] == "a.pdf"][0]
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 200
    assert [d["filename"] for d in client.get("/api/documents").json()] == ["b.pdf"]
    assert client.get("/api/vector-store/stats").json()["total_vectors"] == 1
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 404


def test_reupload_same_filename_replaces_instead_of_duplicating(client, make_pdf):
    upload(client, make_pdf([CRYPTO]), name="same.pdf")
    upload(client, make_pdf([CRYPTO, COOKING]), name="same.pdf")
    assert client.get("/api/vector-store/stats").json()["total_vectors"] == 2
    assert len(client.get("/api/documents").json()) == 1


def test_chunk_size_setting_is_honoured_and_clamped(client, make_pdf):
    long_text = " ".join(f"word{i}" for i in range(120))
    r = upload(client, make_pdf([long_text]), chunk_size=50).json()["results"][0]
    assert r["chunk_size_applied"] == 50 and r["chunks"] >= 3
    r = upload(client, make_pdf([long_text]), name="big.pdf", chunk_size=2000).json()["results"][0]
    assert r["chunk_size_applied"] == 1500  # clamped to the embedding model window
    r = upload(client, make_pdf([long_text]), name="tiny.pdf", chunk_size=1).json()["results"][0]
    assert r["chunk_size_applied"] == 50


def test_upload_error_paths_report_per_file_and_keep_good_files(client, make_pdf):
    files = [
        ("files", ("notes.txt", b"hello", "text/plain")),
        ("files", ("UPPER.PDF", make_pdf([CRYPTO]), "application/pdf")),  # extension check is case-insensitive
        ("files", ("fake.pdf", b"not really a pdf", "application/pdf")),
        ("files", ("blank.pdf", make_pdf([""]), "application/pdf")),
        ("files", ("../../etc/passwd.pdf", make_pdf([COOKING]), "application/pdf")),  # path is stripped
    ]
    results = {r["filename"]: r for r in client.post("/api/upload", files=files).json()["results"]}
    assert results["notes.txt"]["error"] == "Not a PDF"
    assert results["UPPER.PDF"]["status"] == "success"
    assert "PDF" in results["fake.pdf"]["error"]
    assert "No extractable text" in results["blank.pdf"]["error"]
    assert results["passwd.pdf"]["status"] == "success"


def test_failed_reupload_does_not_clobber_a_good_document(client, make_pdf, nim):
    upload(client, make_pdf([CRYPTO]), name="keep.pdf")
    nim.fail = {"status": 500, "remaining": 10, "path": "/embeddings"}
    r = upload(client, make_pdf([COOKING]), name="keep.pdf").json()["results"][0]
    assert r["status"] == "error"
    nim.fail = None
    doc = client.get("/api/documents").json()[0]
    assert doc["status"] == "success"
    assert client.get("/api/vector-store/stats").json()["total_vectors"] == 1


def test_oversize_upload_is_rejected(client, configure, make_pdf):
    import os, config
    os.environ["MAX_UPLOAD_MB"] = "1"
    config.get_settings.cache_clear()
    try:
        big = make_pdf([CRYPTO]) + b"0" * (1024 * 1024 + 10)
        r = upload(client, big, name="big.pdf").json()["results"][0]
        assert r["status"] == "error" and "1 MB" in r["error"]
    finally:
        del os.environ["MAX_UPLOAD_MB"]
        config.get_settings.cache_clear()


def test_llm_failure_returns_fallback_with_retrieved_context_and_never_the_key(client, nim, make_pdf):
    upload(client, make_pdf([CRYPTO]))
    nim.fail = {"status": 401, "remaining": 99, "path": "/chat/completions"}
    r = client.post("/api/chat", json={"query": "public key encryption"})
    assert r.status_code == 200
    answer = r.json()["answer"]
    assert answer.startswith("LLM request failed:") and "NVIDIA_API_KEY" in answer
    assert "Cryptography uses public key" in answer  # retrieved context still shown to the user
    assert TEST_API_KEY not in r.text
    # failed turns are stored but are not fed back to the model next time
    nim.fail = None
    cid = r.json()["chat_id"]
    client.post("/api/chat", json={"query": "retry", "chat_id": cid, "rag_enabled": False})
    assert all("LLM request failed" not in m["content"] for m in nim.chat_requests[-1]["messages"])


def test_transient_llm_errors_are_retried(client, nim):
    nim.fail = {"status": 503, "remaining": 1, "path": "/chat/completions"}
    r = client.post("/api/chat", json={"query": "hi", "rag_enabled": False}).json()
    assert not r["answer"].startswith("LLM request failed")


def test_wrong_model_gives_actionable_message(client, nim, configure):
    import os, config
    os.environ["NVIDIA_MODEL"] = "missing/model"
    config.get_settings.cache_clear()
    try:
        answer = client.post("/api/chat", json={"query": "hi", "rag_enabled": False}).json()["answer"]
        assert "NVIDIA_MODEL" in answer and "missing/model" in answer
    finally:
        del os.environ["NVIDIA_MODEL"]
        config.get_settings.cache_clear()


def test_embedding_failure_during_chat_degrades_gracefully(client, nim):
    nim.fail = {"status": 500, "remaining": 99, "path": "/embeddings"}
    r = client.post("/api/chat", json={"query": "anything"}).json()
    assert "searching your documents failed" in r["answer"]
    assert r["context"] == "Error retrieving context."


def test_embedding_dimension_mismatch_from_model_is_reported(client, nim, make_pdf):
    nim.embed_dim = 512  # server returns vectors that do not match EMBEDDING_DIMENSION
    r = upload(client, make_pdf([CRYPTO])).json()["results"][0]
    assert r["status"] == "error" and "512" in r["error"] and "EMBEDDING_DIMENSION" in r["error"]
    assert client.get("/api/vector-store/stats").json()["total_vectors"] == 0


def test_validation_errors(client):
    assert client.post("/api/chat", json={"query": "   "}).status_code == 400
    assert client.post("/api/chat", json={"query": "x" * 9000}).status_code == 422
    assert client.get("/api/chat/does-not-exist").status_code == 404
    assert client.post("/api/upload").status_code == 422


def test_test_llm_endpoint(client):
    body = client.get("/api/test-llm", params={"prompt": "ping"}).json()
    assert body["provider"] == "nvidia-nim" and body["response"].startswith("Based on context")


def test_no_wildcard_cors_by_default(client):
    r = client.options(
        "/api/chats", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in r.headers


def test_legacy_database_is_migrated_without_losing_rows(configure, tmp_path):
    import sqlite3, database
    s = configure()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(s.db_path)
    conn.executescript(
        """
        CREATE TABLE chats (chat_id TEXT PRIMARY KEY, title TEXT, messages TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE documents (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT UNIQUE, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO chats (chat_id, title, messages) VALUES ('old1', 'Old chat', '[]');
        INSERT INTO documents (filename, status) VALUES ('old.pdf', 'success');
        """
    )
    conn.commit(); conn.close()
    database.init_db()
    database.init_db()  # idempotent
    assert database.get_all_chats("someone") == []  # legacy rows are not visible to anyone
    conn = sqlite3.connect(s.db_path)
    assert conn.execute("select count(*) from chats where chat_id='old1'").fetchone()[0] == 1
    assert conn.execute("select count(*) from documents_legacy").fetchone()[0] == 1
    conn.close()


def test_test_embeddings_endpoint_ok_and_reports_retired_model(client, nim):
    body = client.get("/api/test-embeddings").json()
    assert body["status"] == "ok" and body["returned_dimension"] == 2048
    assert body["model"] == "nvidia/nemotron-3-embed-1b"

    import os, config
    os.environ["EMBEDDING_MODEL"] = "nvidia/nv-embedqa-e5-v5"
    config.get_settings.cache_clear()
    try:
        r = client.get("/api/test-embeddings")
        assert r.status_code == 503 and "has been retired" in r.json()["detail"]
    finally:
        del os.environ["EMBEDDING_MODEL"]
        config.get_settings.cache_clear()
