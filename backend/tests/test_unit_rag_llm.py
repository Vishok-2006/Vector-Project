import pytest

from services import llm_service, rag


# ---------------------------------------------------------------- retrieval helpers
def hit(text, score=0.9, filename="a.pdf", page=1):
    return {"score": score, "filename": filename, "page": page, "text": text}


def test_normalize_filters_by_threshold_and_sorts(configure):
    configure(RAG_MIN_SCORE="0.3")
    out = rag._normalize_results([hit("low", 0.1), hit("mid", 0.5), hit("high", 0.9), hit("", 0.99), "junk"])
    assert [h["text"] for h in out] == ["high", "mid"]


def test_default_threshold_is_configurable(configure):
    configure()
    assert len(rag._normalize_results([hit("x", 0.19), hit("y", 0.21)])) == 1
    configure(RAG_MIN_SCORE="0.8")
    assert rag._normalize_results([hit("x", 0.7)]) == []


def test_dedupe_removes_same_page_near_duplicates_only():
    a = hit("The quick brown fox jumps over the lazy dog")
    dup = hit("the quick brown fox jumps over the lazy dog.")
    other_page = hit("The quick brown fox jumps over the lazy dog", page=2)
    out = rag._dedupe_results([a, dup, other_page])
    assert out == [a, other_page]


def test_context_budget_trims_first_oversized_chunk_and_skips_overflow():
    big = hit(" ".join(["w"] * 3000))
    assert len(rag._limit_context([big])[0]["text"].split()) == 1800
    chunks = [hit(" ".join(["a"] * 1000)), hit(" ".join(["b"] * 1000), page=2), hit("small text", page=3)]
    kept = rag._limit_context(chunks)
    assert [c["page"] for c in kept] == [1, 3]


def test_format_context_labels_sources_and_handles_empty():
    assert rag._format_context([]) == "No relevant context found."
    text = rag._format_context([hit("hello", filename="f.pdf", page=4)])
    assert text.startswith("[Source 1] f.pdf (page 4)\nhello")


# ------------------------------------------------------------------- LLM service
def test_sanitize_strips_reasoning_and_answer_prefix():
    assert llm_service._sanitize_answer("<think>hidden\nthoughts</think>\nAnswer: Hello\n\nWorld") == "Hello\nWorld"
    assert llm_service._sanitize_answer("thoughts without opener</think>Final") == "Final"
    with pytest.raises(llm_service.LLMGenerationError):
        llm_service._sanitize_answer("<think>only thoughts</think>")


def test_history_is_limited_and_failed_turns_are_excluded(configure):
    configure(LLM_HISTORY_MESSAGES="3")
    history = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "LLM request failed: boom"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "q3"},
        {"role": "system", "content": "ignored"},
    ]
    msgs = llm_service._history_to_messages(history)
    assert [m["content"] for m in msgs] == ["q2", "a2", "q3"]


def test_history_disabled(configure):
    configure(LLM_HISTORY_MESSAGES="0")
    assert llm_service._history_to_messages([{"role": "user", "content": "x"}]) == []


def test_user_message_reports_missing_context():
    assert "No document context was provided." in llm_service.build_user_message("", "Why?")
    assert "No document context was provided." in llm_service.build_user_message("Error retrieving context.", "Why?")
    assert "[Source 1] x" in llm_service.build_user_message("[Source 1] x", "Why?")


def test_missing_key_is_reported_not_crashed(configure):
    configure()
    with pytest.raises(llm_service.LLMGenerationError, match="NVIDIA_API_KEY"):
        llm_service.generate_answer("hi", "", [])
    assert llm_service.generate_title("a very long first message that is cut off") .endswith("...")


def test_runtime_config_never_exposes_the_key(configure):
    configure(NVIDIA_API_KEY="super-secret")
    assert "super-secret" not in repr(llm_service.get_llm_runtime_config())
