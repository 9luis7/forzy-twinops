"""Validated embedding clients for Vercel AI Gateway and direct Gemini."""

import math
import re
from typing import Protocol, Sequence

import httpx


DEFAULT_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"
DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_GEMINI_TASK_TYPES = frozenset(
    {"RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY", "SEMANTIC_SIMILARITY"}
)


class EmbeddingGatewayError(RuntimeError):
    pass


class EmbeddingClient(Protocol):
    model: str
    dimensions: int

    async def embed(
        self, texts: Sequence[str]
    ) -> tuple[tuple[float, ...], ...]: ...


class EmbeddingGatewayClient:
    def __init__(
        self,
        http,
        *,
        api_key: str,
        model: str,
        dimensions: int,
        timeout_seconds: float = 10.0,
        base_url: str = DEFAULT_GATEWAY_BASE_URL,
    ) -> None:
        if not api_key or dimensions <= 0 or timeout_seconds <= 0:
            raise ValueError("embedding Gateway configuration is incomplete")
        self._http = http
        self._api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self._timeout_seconds = timeout_seconds
        self._base_url = base_url.rstrip("/")

    async def embed(
        self, texts: Sequence[str]
    ) -> tuple[tuple[float, ...], ...]:
        if not texts or any(not isinstance(text, str) or not text for text in texts):
            raise ValueError("embedding input must contain non-empty strings")
        try:
            response = await self._http.post(
                f"{self._base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": list(texts),
                    "dimensions": self.dimensions,
                },
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            data = payload["data"]
            if not isinstance(data, list) or len(data) != len(texts):
                raise ValueError
            ordered: list[tuple[float, ...] | None] = [None] * len(texts)
            for item in data:
                index = item["index"]
                raw = item["embedding"]
                if (
                    not isinstance(index, int)
                    or not 0 <= index < len(texts)
                    or ordered[index] is not None
                    or not isinstance(raw, list)
                    or len(raw) != self.dimensions
                ):
                    raise ValueError
                vector = tuple(float(value) for value in raw)
                if not all(math.isfinite(value) for value in vector):
                    raise ValueError
                ordered[index] = vector
            if any(item is None for item in ordered):
                raise ValueError
            return tuple(item for item in ordered if item is not None)
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            raise EmbeddingGatewayError("embedding_gateway_unavailable") from None


class GeminiEmbeddingClient:
    """Native Gemini batch embeddings with pinned dimensions and task semantics."""

    def __init__(
        self,
        http,
        *,
        api_key: str,
        model: str,
        dimensions: int,
        task_type: str,
        timeout_seconds: float = 10.0,
        base_url: str = DEFAULT_GEMINI_BASE_URL,
    ) -> None:
        if (
            not api_key
            or re.fullmatch(r"[A-Za-z0-9._-]+", model) is None
            or dimensions <= 0
            or task_type not in _GEMINI_TASK_TYPES
            or timeout_seconds <= 0
        ):
            raise ValueError("Gemini embedding configuration is incomplete")
        self._http = http
        self._api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self._task_type = task_type
        self._timeout_seconds = timeout_seconds
        self._base_url = base_url.rstrip("/")

    async def embed(
        self, texts: Sequence[str]
    ) -> tuple[tuple[float, ...], ...]:
        if not texts or any(not isinstance(text, str) or not text for text in texts):
            raise ValueError("embedding input must contain non-empty strings")
        model_name = f"models/{self.model}"
        try:
            response = await self._http.post(
                f"{self._base_url}/{model_name}:batchEmbedContents",
                headers={
                    "x-goog-api-key": self._api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "requests": [
                        {
                            "model": model_name,
                            "content": {"parts": [{"text": text}]},
                            "embedContentConfig": {
                                "outputDimensionality": self.dimensions,
                                "taskType": self._task_type,
                            },
                        }
                        for text in texts
                    ]
                },
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            raw_embeddings = response.json()["embeddings"]
            if not isinstance(raw_embeddings, list) or len(raw_embeddings) != len(texts):
                raise ValueError
            vectors: list[tuple[float, ...]] = []
            for item in raw_embeddings:
                raw = item["values"]
                if not isinstance(raw, list) or len(raw) != self.dimensions:
                    raise ValueError
                vector = tuple(float(value) for value in raw)
                if not all(math.isfinite(value) for value in vector):
                    raise ValueError
                vectors.append(vector)
            return tuple(vectors)
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            raise EmbeddingGatewayError("embedding_gateway_unavailable") from None
