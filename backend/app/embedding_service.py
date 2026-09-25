from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI


FOUNDRY_ACCOUNT = "doctalk-korea"

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


# Cache the token provider (it handles refresh internally),
# but always create a fresh OpenAI client so the Authorization
# header carries a current token.
_token_provider = None

def _get_token_provider():
    global _token_provider
    if _token_provider is None:
        _token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        )
    return _token_provider

def get_openai_client():
    """
    Return an OpenAI client with a FRESH bearer token every time.
    Azure AD tokens expire after ~1 hour; creating a new client
    on each call guarantees the Authorization header is never stale.
    """
    token = _get_token_provider()()
    return OpenAI(
        base_url=f"https://{FOUNDRY_ACCOUNT}.services.ai.azure.com/openai/v1",
        api_key="placeholder",
        default_headers={
            "Authorization": f"Bearer {token}"
        },
    )


def generate_embedding(text: str) -> list[float]:
    """
    Generate a vector embedding for the supplied text.
    """

    if not text.strip():
        raise ValueError("Text cannot be empty.")

    response = get_openai_client().embeddings.create(
        input=text,
        model=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIMENSIONS,
    )

    embedding = response.data[0].embedding

    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Expected {EMBEDDING_DIMENSIONS} dimensions, "
            f"but received {len(embedding)}."
        )

    return embedding


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for multiple texts in a single API call.
    Much faster than calling generate_embedding() in a loop.
    The OpenAI embeddings API accepts a list of inputs natively.
    """

    if not texts:
        return []

    # Filter out empty texts and track indices
    valid = [(i, t) for i, t in enumerate(texts) if t.strip()]
    if not valid:
        return [[] for _ in texts]

    valid_indices, valid_texts = zip(*valid)

    # OpenAI supports up to 2048 inputs per batch.
    # Using a larger batch size dramatically reduces the number
    # of API round-trips for large documents.
    BATCH_SIZE = 2048
    all_embeddings = [None] * len(texts)

    # Create ONE client for the entire batch run instead of
    # creating a new client (+ token fetch) per batch iteration.
    client = get_openai_client()

    for batch_start in range(0, len(valid_texts), BATCH_SIZE):
        batch_texts = list(valid_texts[batch_start:batch_start + BATCH_SIZE])
        batch_indices = list(valid_indices[batch_start:batch_start + BATCH_SIZE])

        response = client.embeddings.create(
            input=batch_texts,
            model=EMBEDDING_MODEL,
            dimensions=EMBEDDING_DIMENSIONS,
        )

        for j, item in enumerate(response.data):
            all_embeddings[batch_indices[j]] = item.embedding

    # Fill any remaining Nones with empty lists
    return [e if e is not None else [] for e in all_embeddings]