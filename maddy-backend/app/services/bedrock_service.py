import os

import boto3
from botocore.config import Config
from dotenv import load_dotenv


load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID")

if not BEDROCK_MODEL_ID:
    raise RuntimeError(
        "BEDROCK_MODEL_ID must be configured in .env"
    )


bedrock = boto3.client(
    "bedrock-runtime",
    region_name=AWS_REGION,
    config=Config(
        connect_timeout=10,
        read_timeout=120,
        retries={
            "max_attempts": 3,
            "mode": "standard",
        },
    ),
)


def converse(messages, system=None, tool_config=None):
    """Send a conversation to Amazon Bedrock."""

    request = {
        "modelId": BEDROCK_MODEL_ID,
        "messages": messages,
        "inferenceConfig": {
            "maxTokens": 1200,
            "temperature": 0.2,
        },
    }

    if system:
        request["system"] = [
            {"text": system}
        ]

    if tool_config:
        request["toolConfig"] = tool_config

    return bedrock.converse(**request)