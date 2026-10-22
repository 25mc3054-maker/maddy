import os

import boto3
from dotenv import load_dotenv

load_dotenv()

region = os.getenv("AWS_REGION", "us-east-1")
model_id = os.getenv("BEDROCK_MODEL_ID")

if not model_id or model_id == "YOUR_ACTUAL_MODEL_ID":
    raise RuntimeError("Set BEDROCK_MODEL_ID in .env first.")

client = boto3.client(
    "bedrock-runtime",
    region_name=region,
)

response = client.converse(
    modelId=model_id,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "text": "Reply with: MADDY AI connection successful."
                }
            ],
        }
    ],
    inferenceConfig={
        "maxTokens": 100,
        "temperature": 0.2,
    },
)

for block in response["output"]["message"]["content"]:
    if "text" in block:
        print(block["text"])