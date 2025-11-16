"""
Lightweight Ollama API client for this repository.

Supports chat, text generation, and embeddings via Ollama's HTTP API.

Defaults to `http://localhost:11434` and allows overriding with env vars:
  - `OLLAMA_BASE_URL`
  - `OLLAMA_MODEL`

Usage example:

  from ollama_client import OllamaClient

  client = OllamaClient()
  res = client.chat(messages=[
      {"role": "user", "content": "Write a short haiku about code."}
  ], model="llama3.1:8b")
  print(res["message"]["content"])  # or print(res.get("response")) for /generate
"""

from __future__ import annotations

import os
import json
from typing import Any, Dict, List, Optional, Union

import requests

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.environ.get(name)
    return val if val is not None else default


class OllamaClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: int = 60,
    ) -> None:
        self.base_url = (base_url or _env("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.default_model = default_model or _env("OLLAMA_MODEL")
        self.timeout = timeout

    # --- Core HTTP helpers ---
    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = requests.post(url, json=payload, timeout=self.timeout)
        if resp.status_code >= 400:
            # Try to surface helpful error data
            try:
                data = resp.json()
                msg = data.get("error") or data
            except Exception:
                msg = resp.text
            raise requests.HTTPError(f"{resp.status_code} error POST {path}: {msg}")
        # Non-streamed responses are a single JSON object
        return resp.json()

    def _get(self, path: str) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = requests.get(url, timeout=self.timeout)
        if resp.status_code >= 400:
            try:
                data = resp.json()
                msg = data.get("error") or data
            except Exception:
                msg = resp.text
            raise requests.HTTPError(f"{resp.status_code} error GET {path}: {msg}")
        return resp.json()

    # --- High-level APIs ---
    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        Calls /api/chat. messages is a list of {role, content} dicts.
        Returns the last non-streamed response object.
        """
        mdl = model or self.default_model
        if not mdl:
            raise ValueError("No model provided. Set OLLAMA_MODEL or pass model explicitly.")

        payload: Dict[str, Any] = {
            "model": mdl,
            "messages": messages,
            "stream": stream,
        }
        if options:
            payload["options"] = options

        return self._post("/api/chat", payload)

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        system: Optional[str] = None,
        template: Optional[str] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        Calls /api/generate for simple text completion with a single prompt string.
        Returns the non-streamed response object containing "response".
        """
        mdl = model or self.default_model
        if not mdl:
            raise ValueError("No model provided. Set OLLAMA_MODEL or pass model explicitly.")

        payload: Dict[str, Any] = {
            "model": mdl,
            "prompt": prompt,
            "stream": stream,
        }
        if options:
            payload["options"] = options
        if system is not None:
            payload["system"] = system
        if template is not None:
            payload["template"] = template

        return self._post("/api/generate", payload)

    def embeddings(
        self,
        input: Union[str, List[str]],
        model: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Calls /api/embeddings. Returns a dict with "embedding" or "embeddings".
        """
        mdl = model or self.default_model
        if not mdl:
            raise ValueError("No model provided. Set OLLAMA_MODEL or pass model explicitly.")

        payload: Dict[str, Any] = {
            "model": mdl,
            "input": input,
        }
        if options:
            payload["options"] = options

        return self._post("/api/embeddings", payload)

    # --- Utility endpoints ---
    def version(self) -> Dict[str, Any]:
        """Returns Ollama version info if server is reachable."""
        return self._get("/api/version")

    def list_models(self) -> Dict[str, Any]:
        """Returns available models (same as `ollama list`)."""
        return self._get("/api/tags")

    def is_model_available(self, name: str) -> bool:
        try:
            tags = self.list_models()
        except Exception:
            return False
        models = tags.get("models", [])
        return any(m.get("name") == name for m in models)


__all__ = ["OllamaClient"]
