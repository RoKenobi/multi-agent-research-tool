import os
import anthropic


def create_client() -> tuple:
    token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
    region = os.environ.get("AWS_REGION", "us-east-1")

    if token:
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = token

    client = anthropic.AnthropicBedrock(aws_region=region)
    model = os.environ.get(
        "ANTHROPIC_MODEL",
        "us.anthropic.claude-sonnet-5-20251101-v1:0",
    )
    return client, model
