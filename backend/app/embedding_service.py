from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI


FOUNDRY_ACCOUNT = "doctalk-korea-ai"

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


token_provider = get_bearer_token_provider(
    DefaultAzureCredential(),
    "https://cognitiveservices.azure.com/.default",
)

openai_client = OpenAI(
    base_url=f"https://{FOUNDRY_ACCOUNT}.services.ai.azure.com/openai/v1",
    api_key="placeholder",
    default_headers={
        "Authorization": f"Bearer {token_provider()}"
    },
)


def generate_embedding(text: str) -> list[float]:
    """
    Generate a vector embedding for the supplied text.
    """

    if not text.strip():
        raise ValueError("Text cannot be empty.")

    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )

    embedding = response.data[0].embedding

    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Expected {EMBEDDING_DIMENSIONS} dimensions, "
            f"but received {len(embedding)}."
        )

    return embedding