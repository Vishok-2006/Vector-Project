import json

import httpx
import pytest

from services.nim import NimClient, NimError


def client_with(handler, **kw):
    return NimClient(
        "http://nim.test/v1", "key-abc", timeout=5, backoff_base=0, transport=httpx.MockTransport(handler), **kw
    )


def ok_chat(content="hi"):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_chat_sends_bearer_key_model_and_messages():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return ok_chat("pong")

    out = client_with(handler).chat("meta/x", [{"role": "user", "content": "ping"}], temperature=0.3, max_tokens=50)
    assert out == "pong"
    assert seen["auth"] == "Bearer key-abc"
    assert seen["url"] == "http://nim.test/v1/chat/completions"
    assert seen["body"]["model"] == "meta/x"
    assert seen["body"]["max_tokens"] == 50 and seen["body"]["stream"] is False


def test_retries_on_429_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, json={"detail": "slow down"}) if len(calls) < 3 else ok_chat("done")

    assert client_with(handler, max_retries=3).chat("m", []) == "done"
    assert len(calls) == 3


def test_gives_up_after_max_retries_with_friendly_message():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, json={"detail": "busy"})

    with pytest.raises(NimError, match="HTTP 503") as info:
        client_with(handler, max_retries=2).chat("m", [])
    assert len(calls) == 3 and info.value.status == 503


@pytest.mark.parametrize(
    "status,needle",
    [(401, "NVIDIA_API_KEY"), (403, "access"), (404, "NVIDIA_MODEL"), (400, "rejected the request")],
)
def test_client_errors_are_not_retried_and_explain_the_fix(status, needle):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json={"detail": "nope"})

    with pytest.raises(NimError, match=needle):
        client_with(handler, max_retries=3).chat("some/model", [])
    assert len(calls) == 1


def test_key_is_never_in_error_text():
    def handler(request):
        return httpx.Response(401, json={"detail": "bad"})

    with pytest.raises(NimError) as info:
        client_with(handler).chat("m", [])
    assert "key-abc" not in str(info.value)


def test_timeout_and_connection_errors_are_retryable_and_reported():
    def timeout(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(NimError, match="did not answer") as info:
        client_with(timeout, max_retries=1).chat("m", [])
    assert info.value.retryable

    def refuse(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(NimError, match="Could not connect"):
        client_with(refuse, max_retries=0).chat("m", [])


def test_missing_key_fails_before_any_request():
    called = []
    c = NimClient("http://x/v1", "", transport=httpx.MockTransport(lambda r: called.append(1) or ok_chat()))
    with pytest.raises(NimError, match="NVIDIA_API_KEY"):
        c.chat("m", [])
    assert not called


@pytest.mark.parametrize("body", [{"choices": []}, {"choices": [{"message": {"content": "  "}}]}, {}])
def test_empty_or_malformed_completions_raise(body):
    with pytest.raises(NimError):
        client_with(lambda r: httpx.Response(200, json=body)).chat("m", [])


def test_non_json_success_body_raises():
    with pytest.raises(NimError, match="valid JSON"):
        client_with(lambda r: httpx.Response(200, text="<html>")).chat("m", [])


def test_embeddings_send_input_type_and_reorder_by_index():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"data": [{"index": 1, "embedding": [0.2, 0.2]}, {"index": 0, "embedding": [0.1, 0.1]}]},
        )

    out = client_with(handler).embeddings("nvidia/nv-embedqa-e5-v5", ["a", "b"], input_type="passage")
    assert out == [[0.1, 0.1], [0.2, 0.2]]
    assert seen["body"]["input_type"] == "passage" and seen["body"]["truncate"] == "END"
    assert seen["body"]["encoding_format"] == "float"


def test_embeddings_without_input_type_omit_truncate():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})

    client_with(handler).embeddings("m", ["a"], input_type=None)
    assert "input_type" not in seen["body"] and "truncate" not in seen["body"]


def test_embedding_count_mismatch_raises():
    with pytest.raises(NimError, match="embeddings"):
        client_with(lambda r: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})).embeddings(
            "m", ["a", "b"], input_type="query"
        )
