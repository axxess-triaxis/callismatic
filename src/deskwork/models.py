"""Picks the model provider Strands should run on.

Bedrock is the default -- this project targets an AWS-sponsored hackathon and
Bedrock is the AWS-native path. Model access for the chosen model must be
enabled in the AWS console for the target account/region before this works;
that's an account-level step this code can't do for you.
"""

from __future__ import annotations

import os

import boto3
from strands.models import BedrockModel


def get_model() -> BedrockModel:
    region = os.environ.get("BEDROCK_REGION", "us-west-2")
    session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"), region_name=region)
    return BedrockModel(
        model_id=os.environ.get("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-6"),
        boto_session=session,
        temperature=0.2,
    )
