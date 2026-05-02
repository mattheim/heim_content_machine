import json
import re


def _strip_trailing_commas(text: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _balanced_json_objects(text: str) -> list[str]:
    objects: list[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(text[start:index + 1])
                start = None

    return objects


def _extract_json_payload(raw_text: str) -> dict:
    text = raw_text.strip()
    if not text:
        raise ValueError("Expected JSON content but received an empty response.")

    candidates = [text]
    if "```json" in text:
        start = text.find("```json") + len("```json")
        end = text.rfind("```")
        if end > start:
            candidates.insert(0, text[start:end].strip())
    elif "```" in text:
        start = text.find("```") + len("```")
        end = text.rfind("```")
        if end > start:
            candidates.insert(0, text[start:end].strip())

    candidates.extend(_balanced_json_objects(text))

    for candidate in candidates:
        for variant in (candidate, _strip_trailing_commas(candidate)):
            try:
                payload = json.loads(variant)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload

    raise ValueError(f"Could not parse JSON payload from model response: {raw_text[:400]}")


def _clean_line(text: str, max_len: int | None = None) -> str:
    cleaned = " ".join(str(text).replace("\n", " ").split()).strip()
    cleaned = cleaned.strip("\"' ")
    if max_len and len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    return cleaned


def _normalize_hashtags(raw_hashtags) -> list[str]:
    if isinstance(raw_hashtags, str):
        tokens = raw_hashtags.replace(",", " ").split()
    elif isinstance(raw_hashtags, list):
        tokens = [str(tag) for tag in raw_hashtags]
    else:
        tokens = []

    seen: set[str] = set()
    normalized: list[str] = []
    for token in tokens:
        clean = "".join(ch for ch in token.strip() if ch.isalnum() or ch == "#")
        if not clean:
            continue
        if not clean.startswith("#"):
            clean = f"#{clean}"
        clean = clean.lower()
        if clean not in seen:
            seen.add(clean)
            normalized.append(clean)
    return normalized[:10]
