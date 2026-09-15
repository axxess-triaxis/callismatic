from strands.models import BedrockModel
from strands.models.openai import OpenAIModel
from strands.models.routing import ModelRouter

from callismatic import models


def test_get_model_returns_plain_bedrock_when_nebius_unset(monkeypatch):
    # The core backward-compatibility guarantee: unset NEBIUS_API_KEY means
    # get_model() behaves exactly as it always did, for anyone without a
    # Nebius key -- same "absent means unchanged" pattern every other
    # optional integration in this project follows.
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    result = models.get_model()
    assert isinstance(result, BedrockModel)
    assert not isinstance(result, ModelRouter)


def test_get_nebius_model_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    assert models.get_nebius_model() is None


def test_get_nebius_model_configured_correctly(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key-not-real")
    nebius = models.get_nebius_model()
    assert isinstance(nebius, OpenAIModel)
    assert nebius.client_args["api_key"] == "test-key-not-real"
    assert nebius.client_args["base_url"] == models.NEBIUS_DEFAULT_BASE_URL
    assert nebius.config["model_id"] == models.NEBIUS_DEFAULT_MODEL_ID
    # Deliberately generous: Nemotron 3 Nano is a reasoning model that spends
    # tokens on an internal `reasoning` field before emitting `content`, and
    # can't carry that reasoning across turns via the Chat Completions API --
    # it re-derives reasoning from scratch each turn. A real multi-turn triage
    # run raised MaxTokensReachedException at 2000; 8000 completed successfully
    # (confirmed live, see models.py's get_nebius_model docstring).
    assert nebius.config["params"]["max_tokens"] == 8000


def test_get_nebius_model_respects_overrides(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key-not-real")
    monkeypatch.setenv("NEBIUS_MODEL_ID", "nvidia/nemotron-3-super-120b-a12b")
    monkeypatch.setenv("NEBIUS_BASE_URL", "https://example.invalid/v1/")
    monkeypatch.setenv("NEBIUS_MAX_TOKENS", "500")
    nebius = models.get_nebius_model()
    assert nebius.config["model_id"] == "nvidia/nemotron-3-super-120b-a12b"
    assert nebius.client_args["base_url"] == "https://example.invalid/v1/"
    assert nebius.config["params"]["max_tokens"] == 500


def test_get_model_returns_router_with_nebius_first_when_set(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key-not-real")
    monkeypatch.setenv("AWS_PROFILE", "axxess-triaxis")
    result = models.get_model()
    assert isinstance(result, ModelRouter)
    # Nebius must be the first candidate -- FallbackStrategy tries candidates
    # in declaration order, so "Nebius first, Bedrock as the safety net" is a
    # real behavioral guarantee only if Nebius is genuinely listed first, not
    # just present. Confirmed real shape via direct inspection (not guessed):
    # router.candidates is a tuple of RoutingCandidate(model=..., ...).
    assert len(result.candidates) == 2
    assert isinstance(result.candidates[0].model, OpenAIModel)
    assert isinstance(result.candidates[1].model, BedrockModel)
