"""Alem's OpenAI-compatible Gemma adapter."""

from __future__ import annotations

import os
from typing import Protocol

from openai import OpenAI, OpenAIError


DEFAULT_ALEM_BASE_URL = "https://llm.alem.ai/v1"
DEFAULT_ALEM_MODEL = "gemma4"


class LLMUnavailable(RuntimeError):
    pass


class EnglishExtractionClient(Protocol):
    model_name: str

    def extract(self, prompt: str) -> str: ...


class UnavailableEnglishClient:
    """Explicit runtime placeholder that lets a batch record review issues per source."""

    model_name = ""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def extract(self, prompt: str) -> str:
        raise LLMUnavailable(self.reason)


class AlemGemmaClient:
    """Thin dependency-injectable boundary around the OpenAI-compatible SDK."""

    def __init__(self, api_key: str, base_url: str = DEFAULT_ALEM_BASE_URL, model_name: str = DEFAULT_ALEM_MODEL, *, client: OpenAI | None = None) -> None:
        if not api_key:
            raise LLMUnavailable("ALEM_API_KEY is not configured")
        self.model_name = model_name
        self.base_url = base_url
        self._client = client or OpenAI(api_key=api_key, base_url=base_url)

    @classmethod
    def from_environment(cls) -> "AlemGemmaClient":
        return cls(
            api_key=os.environ.get("ALEM_API_KEY", ""),
            base_url=os.environ.get("ALEM_BASE_URL", DEFAULT_ALEM_BASE_URL),
            model_name=os.environ.get("ALEM_MODEL", DEFAULT_ALEM_MODEL),
        )

    def extract(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                temperature=0,
                messages=[
                    {"role": "system", "content": "You are a bounded extraction component. Return only JSON."},
                    {"role": "user", "content": prompt},
                ],
            )
        except OpenAIError as exc:
            # SDK exception text can contain request details; preserve only a safe class identifier.
            raise LLMUnavailable(f"Alem request failed: {exc.__class__.__name__}") from exc
        content = response.choices[0].message.content
        if not content:
            raise LLMUnavailable("Alem returned an empty completion")
        return content
