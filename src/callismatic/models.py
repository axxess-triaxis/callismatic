"""Picks the model provider(s) Strands should run on.

Bedrock is the default and the always-on safety net -- this project targets
an AWS-sponsored hackathon and Bedrock is the AWS-native path. Model access
for the chosen model must be enabled in the AWS console for the target
account/region before this works; that's an account-level step this code
can't do for you.

Nebius Token Factory (Nebius x NVIDIA Global AI Hackathon) is opt-in: unset
NEBIUS_API_KEY means get_model() returns exactly the same plain BedrockModel
it always did -- unchanged behavior for anyone without a Nebius key, the same
"absent means unchanged" pattern every other optional integration in this
project follows. When it IS set, get_model() returns a Strands ModelRouter
trying Nebius/Nemotron first (cheaper, purpose-tuned once fine-tuned per the
AMD ACT III plan; here, the hackathon-required provider) and falling back to
Bedrock automatically via FallbackStrategy if the Nebius-hosted endpoint is
ever unavailable -- Bedrock stays the safety net, not something replaced.
"""

from __future__ import annotations

import os

import boto3
from strands.models import BedrockModel, Model
from strands.models.openai import OpenAIModel
from strands.models.routing import FallbackStrategy, ModelRouter

NEBIUS_DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
# Nemotron 3 Nano, not Super or Ultra -- deliberately, the same reasoning
# AMD_ACT3_ARCHITECTURE.md already gives for the fine-tune target: this is a
# narrow, structured-classification task (5 categories, a handful of boolean
# flags), not open-ended generation, so a smaller model is the right tool.
NEBIUS_DEFAULT_MODEL_ID = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"


def get_bedrock_model() -> BedrockModel:
    region = os.environ.get("BEDROCK_REGION", "us-west-2")
    session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"), region_name=region)
    return BedrockModel(
        model_id=os.environ.get("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-6"),
        boto_session=session,
        temperature=0.2,
    )


def get_nebius_model() -> OpenAIModel | None:
    """Returns a Strands OpenAIModel pointed at Nebius Token Factory, or None if
    NEBIUS_API_KEY isn't set -- Nebius Token Factory is a real, confirmed
    OpenAI-compatible API (verified live: model listing, a plain completion, and
    a real Strands structured_output call through CallTriage all succeeded
    against nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B), so no custom Model subclass
    is needed, only client_args pointing OpenAIModel's underlying openai client
    at Nebius instead of api.openai.com.

    max_tokens defaults to 8000, not OpenAIModel's own default, and not the 2000
    this project started with. Nemotron 3 Nano is a reasoning model that spends
    tokens on an internal `reasoning` field before ever emitting `content`
    (confirmed live: a one-word reply request with max_tokens=20 came back with
    content=None, finish_reason="length"). Inside a real multi-turn Strands tool
    loop this is worse than the single-call case: the OpenAI Chat Completions API
    has no way to carry `reasoningContent` back into the next turn (Strands logs
    "reasoningContent is not supported in multi-turn conversations with the Chat
    Completions API" and drops it each time), so the model re-derives its
    reasoning from scratch on every turn. A real end-to-end triage run of one
    simple voicemail (confirm-appointment, 2 tool calls) spent ~10.7k accumulated
    output tokens across the full run and raised strands.types.exceptions.
    MaxTokensReachedException at the old max_tokens=2000 per-call default; at
    max_tokens=8000 per call it completed successfully. This is a real, open cost
    characteristic of running Nemotron 3 Nano inside an agentic tool loop via this
    API, not a one-off fluke -- expect it to scale with transcript complexity and
    tool-call count.

    Also confirmed live and important: FallbackStrategy (see get_model()) does
    NOT catch MaxTokensReachedException -- it only reacts to an actual call
    failure (verified separately: an invalid NEBIUS_API_KEY correctly triggers
    the fallback to Bedrock in ~11s). Running out of max_tokens crashes the whole
    agent run instead of triggering a fallback. A generous max_tokens is
    therefore the real mitigation for that specific failure mode, not
    FallbackStrategy.
    """
    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key:
        return None
    return OpenAIModel(
        client_args={
            "base_url": os.environ.get("NEBIUS_BASE_URL", NEBIUS_DEFAULT_BASE_URL),
            "api_key": api_key,
        },
        model_id=os.environ.get("NEBIUS_MODEL_ID", NEBIUS_DEFAULT_MODEL_ID),
        params={"max_tokens": int(os.environ.get("NEBIUS_MAX_TOKENS", "8000"))},
    )


def get_model() -> Model:
    bedrock = get_bedrock_model()
    nebius = get_nebius_model()
    if nebius is None:
        return bedrock
    return ModelRouter(models=[nebius, bedrock], strategy=FallbackStrategy())
