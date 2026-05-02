import os
import requests
from pathlib import Path
from typing import Any


PROMPT_PROVIDER = os.environ.get("PROMPT_PROVIDER", "strategos").strip().lower()
STRATEGOS_BASE_URL = os.environ.get("STRATEGOS_BASE_URL", "http://localhost:38007").rstrip("/")
STRATEGOS_TIMEOUT_MS = int(os.environ.get("STRATEGOS_TIMEOUT_MS", "300000"))
DEFAULT_PROJECT_PATH = str(Path(__file__).resolve().parents[1])


def _resolve_project_path() -> str:
    return os.environ.get("STRATEGOS_PROJECT_PATH") or DEFAULT_PROJECT_PATH


def _resolve_provider() -> str:
    provider = os.environ.get("PROMPT_PROVIDER", PROMPT_PROVIDER).strip().lower()
    if provider not in {"strategos", "ollama"}:
        raise ValueError(
            f"Unsupported PROMPT_PROVIDER={provider!r}. Expected 'strategos' or 'ollama'."
        )
    return provider


def _resolve_model(model: str | None) -> str:
    return model or os.environ.get("OLLAMA_MODEL") or "deepseek-r1:8b"


def _build_strategos_prompt(messages: list[dict], system_content: str, user_content: str) -> str:
    prompt_sections = [
        "You are generating one step of a social-media content pipeline.",
        "Follow the system instruction exactly and return only the requested output.",
        "",
        "SYSTEM INSTRUCTION:",
        system_content.strip(),
    ]
    if messages:
        prompt_sections.extend(["", "PRIOR CONVERSATION:"])
        for message in messages:
            role = str(message.get("role", "user")).upper()
            content = str(message.get("content", "")).strip()
            prompt_sections.append(f"{role}: {content}")
    prompt_sections.extend([
        "",
        "CURRENT USER REQUEST:",
        user_content.strip(),
        "",
        "Return only the requested text with no prefacing commentary.",
    ])
    return "\n".join(prompt_sections)


def _run_strategos_prompt(prompt: str) -> str:
    payload: dict[str, Any] = {
        "projectPath": _resolve_project_path(),
        "prompt": prompt,
        "mode": "headless",
        "timeout": STRATEGOS_TIMEOUT_MS,
        "outputFormat": "json",
    }
    response = requests.post(
        f"{STRATEGOS_BASE_URL}/api/integration/workflow-execute",
        json=payload,
        timeout=max(10, (STRATEGOS_TIMEOUT_MS // 1000) + 15),
    )
    response.raise_for_status()
    body = response.json()
    result = body.get("result") or {}
    raw_content = (
        result.get("result")
        or result.get("output")
        or body.get("output")
        or ""
    )
    content = str(raw_content).strip()
    if not content:
        raise ValueError(
            "Strategos returned an empty response. "
            f"Top-level keys: {sorted(body.keys())}; result keys: {sorted(result.keys()) if isinstance(result, dict) else 'n/a'}"
        )
    return content


def _run_ollama_prompt(messages: list[dict], model: str | None = None) -> str:
    try:
        from ollama import chat
    except ImportError as exc:
        raise ImportError(
            "Ollama support requires the 'ollama' Python package. "
            "Install it with `pip install ollama` or switch PROMPT_PROVIDER to strategos."
        ) from exc

    response = chat(model=_resolve_model(model), messages=messages)
    content = response.message.content.strip()
    if not content:
        raise ValueError("Ollama returned an empty response.")
    return content


def chat_step(messages: list | None, system_content: str, user_content: str, model: str | None = None) -> str:
    if messages is None:
        messages = []
    messages.append({"role": "system", "content": system_content})
    messages.append({"role": "user", "content": user_content})
    provider = _resolve_provider()
    if provider == "strategos":
        prompt = _build_strategos_prompt(messages[:-2], system_content, user_content)
        content = _run_strategos_prompt(prompt)
    else:
        content = _run_ollama_prompt(messages, model=model)
    messages.append({"role": "assistant", "content": content})
    return content
