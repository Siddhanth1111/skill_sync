"""LLM access: Ollama client plus a validate-and-retry helper.

The LLM is only used to extract structure. It never produces scores.
"""
import json
from typing import Dict, List, Protocol, Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from ..config import Settings

T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(Exception):
    """Ollama unreachable or erroring. Callers fall back to the rule extractor."""


class LLMInvalidOutput(Exception):
    """The model never produced output matching the schema, even after retries."""


class LLMClient(Protocol):
    def chat(self, messages: List[Dict[str, str]], schema: dict) -> str:
        """Send chat messages, return the raw model reply (expected to be JSON)."""


class OllamaClient:
    def __init__(self, settings: Settings):
        self.url = settings.ollama_url.rstrip("/")
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout_s

    def chat(self, messages: List[Dict[str, str]], schema: dict) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": schema,  # Ollama constrains decoding to this JSON schema
            "options": {"temperature": 0},
        }
        try:
            r = httpx.post(self.url + "/api/chat", json=payload, timeout=self.timeout)
            r.raise_for_status()
            return r.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise LLMUnavailable("%s: %s" % (type(exc).__name__, exc))


def generate_validated(client: LLMClient, system: str, prompt: str, model_cls: Type[T], max_retries: int) -> T:
    """Ask for JSON matching model_cls. On a validation failure, feed the error back and retry
    (up to max_retries extra attempts). LLMUnavailable propagates immediately."""
    schema = model_cls.model_json_schema()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    last_error = "no attempt made"
    for _ in range(max_retries + 1):
        reply = client.chat(messages, schema)
        try:
            return model_cls.model_validate_json(reply)
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            last_error = str(exc)
            messages.append({"role": "assistant", "content": reply})
            messages.append({
                "role": "user",
                "content": "Your reply did not match the schema. Error: %s\nReturn corrected JSON only." % last_error[:800],
            })
    raise LLMInvalidOutput(last_error[:300])
