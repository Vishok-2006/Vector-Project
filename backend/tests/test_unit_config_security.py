import pytest

import config
import security


def test_defaults_use_nvidia_nim_and_2048_dim(configure):
    s = configure()
    assert s.nvidia_base_url == "https://integrate.api.nvidia.com/v1"
    assert s.nvidia_model == "meta/llama-3.3-70b-instruct"
    assert s.embedding_provider == "nvidia"
    assert s.embedding_model == "nvidia/nemotron-3-embed-1b"
    assert s.embedding_dimension == 2048
    assert s.embedding_max_chunk_words == 1500
    assert s.nvidia_api_key == ""  # no secret has a default


def test_env_overrides_and_trailing_slash(configure):
    s = configure(NVIDIA_BASE_URL="http://nim.local/v1/", NVIDIA_MODEL="acme/model", NVIDIA_API_KEY="k")
    assert s.nvidia_base_url == "http://nim.local/v1"
    assert s.nvidia_model == "acme/model"
    assert s.embedding_base_url == "http://nim.local/v1"  # embeddings follow the NIM base URL by default


def test_local_provider_defaults_to_384_dim_and_small_chunks(configure):
    s = configure(EMBEDDING_PROVIDER="local")
    assert s.embedding_dimension == 384
    assert s.embedding_max_chunk_words == 150


def test_unknown_embedding_model_requires_explicit_dimension(configure):
    with pytest.raises(config.ConfigError, match="EMBEDDING_DIMENSION"):
        configure(EMBEDDING_MODEL="acme/mystery-embed")
    s = configure(EMBEDDING_MODEL="acme/mystery-embed", EMBEDDING_DIMENSION=768)
    assert s.embedding_dimension == 768


@pytest.mark.parametrize(
    "env",
    [
        {"EMBEDDING_PROVIDER": "gemini"},
        {"LLM_TIMEOUT_SECONDS": "abc"},
        {"LLM_TIMEOUT_SECONDS": "-1"},
        {"COOKIE_SECURE": "maybe"},
        {"RAG_TOP_K": "0"},
    ],
)
def test_invalid_values_fail_fast(configure, env):
    with pytest.raises(config.ConfigError):
        configure(**env)


def test_token_roundtrip_and_tamper_detection(configure):
    configure(SESSION_SECRET="s3cret")
    token = security.make_token("abc123")
    assert security.verify_token(token) == "abc123"
    assert security.verify_token("other." + token.split(".")[1]) is None  # signature bound to the id
    assert security.verify_token(token[:-2] + "xx") is None
    assert security.verify_token("no-signature") is None
    assert security.verify_token(None) is None
    assert security.verify_token("." + token.split(".")[1]) is None


def test_token_signed_with_other_secret_is_rejected(configure):
    configure(SESSION_SECRET="one")
    token = security.make_token("u1")
    configure(SESSION_SECRET="two")
    assert security.verify_token(token) is None


def test_generated_secret_is_persisted_with_private_permissions(configure, tmp_path):
    s = configure()
    first = security.make_token("u1")
    key_file = s.data_dir / "session_secret"
    assert key_file.exists()
    assert oct(key_file.stat().st_mode & 0o777) == "0o600"
    security.reset_secret_cache()  # simulate a restart
    assert security.verify_token(first) == "u1"
