import os
import re

def sanitize_filename(text: str, max_len: int = 30) -> str:
    # Replace non-filename chars, collapse spaces, and trim length
    cleaned = re.sub(r"[\r\n\t]", " ", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned[:max_len].strip()
    safe = re.sub(r"[^A-Za-z0-9 _.-]", "", cleaned)
    return safe.replace(" ", "_") or "image"