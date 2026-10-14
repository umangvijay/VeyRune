from abc import ABC, abstractmethod
from typing import List
from backend.config.settings import settings
import logging

logger = logging.getLogger(__name__)

class EmbeddingService(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        pass

class MockEmbeddingService(EmbeddingService):
    def embed_text(self, text: str) -> List[float]:
        # Return a mock 768-dimensional embedding
        return [0.1] * 768

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
        try:
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
            logger.error(f"Failed to generate embedding: {e}")
            raise
