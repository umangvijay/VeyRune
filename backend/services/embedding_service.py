from abc import ABC, abstractmethod
from typing import List
from backend.config.settings import settings
import logging
import time

logger = logging.getLogger(__name__)

# When embedding is unavailable, fail fast instead of stalling every write.
# Measured: auth failures took ~6s per attempt under load — memory writes
# crawled at p50 5.8s with embeddings unconfigured. After the first failure
# we skip embedding attempts entirely for a cooldown window.
EMBED_FAIL_COOLDOWN_SECONDS = 60.0

_embed_unavailable_until: float = 0.0


class EmbeddingService(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        pass


class MockEmbeddingService(EmbeddingService):
    def embed_text(self, text: str) -> List[float]:
        # Return a mock 768-dimensional embedding
        return [0.1] * 768


def _embedding_configured() -> bool:
    """True when an embedding provider can plausibly work right now."""
    from backend.services.llm_context import effective_gemini_key, active_llm_provider
    if active_llm_provider() == "vertex":
        return bool(settings.GOOGLE_CLOUD_PROJECT)
    return bool(effective_gemini_key())


class GoogleCloudEmbeddingService(EmbeddingService):
    def __init__(self):
        self.client = None

    def _initialize(self):
        from google import genai

        # Initialize client according to ADK settings structure
        from backend.services.llm_context import effective_gemini_key, active_llm_provider
        if active_llm_provider() != "vertex" and effective_gemini_key():
            self.client = genai.Client(api_key=effective_gemini_key())
        else:
            self.client = genai.Client(
                vertexai=True,
                project=settings.GOOGLE_CLOUD_PROJECT,
                location=settings.GEMINI_EMBEDDING_REGION
            )

    def embed_text(self, text: str) -> List[float]:
        global _embed_unavailable_until
        # Fail fast during the cooldown — memory writes must not queue behind
        # a provider that just told us it is unavailable.
        if time.monotonic() < _embed_unavailable_until:
            raise RuntimeError("Embedding provider unavailable (cooldown after recent failure)")
        try:
            if not _embedding_configured():
                raise RuntimeError(
                    "No embedding provider configured: set a Gemini key or Vertex credentials"
                )
            if self.client is None:
                self._initialize()
            response = self.client.models.embed_content(
                model=settings.GEMINI_EMBEDDING_MODEL,
                contents=text
            )
            # Depending on genai SDK version, the structure varies.
            # Usually response.embeddings[0].values
            return response.embeddings[0].values
        except Exception as e:
            _embed_unavailable_until = time.monotonic() + EMBED_FAIL_COOLDOWN_SECONDS
            logger.warning(f"Embedding unavailable (cooldown {EMBED_FAIL_COOLDOWN_SECONDS:.0f}s): {type(e).__name__}")
            raise
