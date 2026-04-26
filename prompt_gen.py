import os
import json
import time
import textwrap
import requests
from pathlib import Path

PROMPT_PROVIDER = os.environ.get("PROMPT_PROVIDER", "strategos").strip().lower()
STRATEGOS_BASE_URL = os.environ.get("STRATEGOS_BASE_URL", "http://localhost:38007").rstrip("/")
STRATEGOS_TIMEOUT_MS = int(os.environ.get("STRATEGOS_TIMEOUT_MS", "300000"))
DEFAULT_PROJECT_PATH = str(Path(__file__).resolve().parent)

BASE_SYSTEM = (
    """
        You are an expert prompt engineer specializing in image generation. 
        You always create highly detailed, cinematic prompts optimized for Image generation.
        Your core focus is greek mythology and you should always generate content that lives within that theme
        Greek mythology is eternal drama dressed in gold and marble — gods acting like mortals, mortals acting like fools, and fate laughing in the background.
        This meme tone treats ancient myths like modern tea, mixing cosmic grandeur with the dry humor of someone who’s seen too many prophecies go wrong.

    """
)

BASE_CAPTION = (
  """
  Primary objective:
      Create instantly understandable, saveable, shareable Greek mythology posts.
      Optimize for strong hooks, fast comprehension, and scene-specific jokes that people want to send to a friend.

  Content pillars:
      - Relatable modern pain through myth
      - Petty god behavior
      - Motivational one-liners
      - Relationship memes
      - Oracle / prophecy / fate office humor

  Content rubric:
      - The first-line hook must be legible and understandable in under 2 seconds.
      - The joke must land even for viewers with only basic mythology knowledge.
- The caption body must add a second beat, not explain the joke.
- Every candidate should clearly target one outcome: share, save, comment, or follow.
- Prefer share/send outcomes because DM sends are the strongest signal for discovery.
- Every candidate must feel specific to the scene, not swappable onto any image.

  Diversity requirement:
      Generate meaningfully different candidates using different comedic mechanisms such as:
      - absurd contrast
      - painful relatability
      - deadpan
      - hyper-specific modern reference
      - elegant melancholy
      - savage observational humor

  Reject weak copy:
      - generic influencer phrasing
      - overexplaining
      - jokes that need too much setup
      - slang that feels forced
      - captions that could fit almost any image

  Style notes:
      - Olympus meets modern internet behavior.
      - Eternal drama, but understandable on first read.
      - Keep the language clean, specific, and conversational.
      - Prefer clarity over cleverness if forced to choose.
      - Keep it sharp enough to screenshot, share, or save.

  Example directions:
      - “Athena watching you make the same mistake twice.”
      - “Oracle said don’t text him back.”
      - “Poseidon taking one bad beach review personally.”
      - “The prophecy was actually just calendar anxiety.”
      - “Apollo posting one gym selfie and calling it destiny.”
  """
)

CONTENT_PILLARS = {
    "relatable_modern_pain": "Relatable modern pain through myth",
    "petty_god_behavior": "Petty god behavior",
    "motivational_one_liners": "Motivational one-liners",
    "relationship_memes": "Relationship memes",
    "oracle_office_humor": "Oracle / prophecy / fate office humor",
}

COMEDIC_MECHANISMS = {
    "absurd_contrast": "Absurd contrast between epic myth and ordinary modern behavior",
    "painful_relatability": "Painful relatability rooted in recognizable everyday problems",
    "deadpan": "Dry, understated delivery",
    "hyper_specific_modern_reference": "Hyper-specific modern reference used sparingly and clearly",
    "elegant_melancholy": "Beautiful, restrained melancholy with a clean joke turn",
    "savage_observational_humor": "Sharp observational humor about recognizable behavior",
}

TARGET_OUTCOMES = {"share", "save", "comment", "follow"}

SHARE_CTA_PATTERNS = (
    "Send this to the friend who",
    "Send this to someone who",
    "Show this to the friend who",
    "Tag the friend who",
    "Save this for the next time",
)

GENERIC_INFLUENCER_PHRASES = (
    "link in bio",
    "drop a comment",
    "tag someone",
    "main character energy",
    "for the girlies",
    "soft launch",
)

FORCED_SLANG_PHRASES = (
    "it's giving",
    "she ate",
    "no cap",
    "slay",
    "bffr",
)

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
    payload = {
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

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidates.append(text[first_brace:last_brace + 1])

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
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


def _normalize_candidate(candidate: dict, fallback_style: str) -> dict:
    return {
        "style_label": _clean_line(candidate.get("style_label") or fallback_style or "mythic_irony", max_len=40),
        "overlay_text": _clean_line(candidate.get("overlay_text") or candidate.get("caption_hook") or "", max_len=90),
        "caption_hook": _clean_line(candidate.get("caption_hook") or candidate.get("overlay_text") or "", max_len=110),
        "post_body": _clean_line(candidate.get("post_body") or "", max_len=320),
        "share_cta": _clean_line(candidate.get("share_cta") or "", max_len=120),
        "first_comment": _clean_line(candidate.get("first_comment") or "", max_len=180),
        "hashtags": _normalize_hashtags(candidate.get("hashtags")),
        "content_pillar": _clean_line(candidate.get("content_pillar") or "", max_len=40),
        "comedic_mechanism": _clean_line(candidate.get("comedic_mechanism") or "", max_len=50),
        "target_outcome": _clean_line(candidate.get("target_outcome") or "", max_len=12).lower(),
        "scene_anchor": _clean_line(candidate.get("scene_anchor") or "", max_len=80),
    }


def _normalize_hook_variant(variant: dict, fallback_style: str) -> dict:
    return {
        "hook_style": _clean_line(variant.get("hook_style") or fallback_style, max_len=40),
        "overlay_text": _clean_line(variant.get("overlay_text") or "", max_len=90),
        "caption_hook": _clean_line(variant.get("caption_hook") or "", max_len=110),
        "share_cta": _clean_line(variant.get("share_cta") or "", max_len=120),
        "score_reason": _clean_line(variant.get("score_reason") or "", max_len=180),
    }


def _score_hook_variant(variant: dict, base_content: dict | None = None) -> float:
    overlay = _clean_line(variant.get("overlay_text") or "", max_len=90)
    hook = _clean_line(variant.get("caption_hook") or "", max_len=110)
    cta = _clean_line(variant.get("share_cta") or "", max_len=120)
    combined = " ".join(part for part in [overlay, hook, cta] if part).lower()
    score = 0.0

    overlay_words = overlay.split()
    hook_words = hook.split()
    if 3 <= len(overlay_words) <= 8:
        score += 3.0
    elif overlay_words:
        score += 1.0
    if 4 <= len(hook_words) <= 12:
        score += 2.0
    if any(pattern.lower() in combined for pattern in SHARE_CTA_PATTERNS):
        score += 4.0
    if any(word in combined for word in ("friend", "someone", "group chat", "send", "tag")):
        score += 2.0
    if "?" in overlay or "?" in hook:
        score += 0.75

    myth_terms = (
        "zeus", "hera", "athena", "apollo", "artemis", "aphrodite", "ares", "poseidon",
        "hades", "persephone", "hermes", "oracle", "prophecy", "fate", "olympus",
        "mortal", "god", "goddess", "nymph", "titan", "medusa", "icarus"
    )
    if any(term in combined for term in myth_terms):
        score += 1.5

    scene_anchor = ""
    if base_content:
        scene_anchor = _clean_line(base_content.get("scene_anchor") or "", max_len=80)
    if scene_anchor:
        anchor_tokens = [token for token in scene_anchor.lower().split() if len(token) > 2]
        if anchor_tokens and any(token in combined for token in anchor_tokens):
            score += 1.25

    if len(overlay_words) > 9:
        score -= 3.0
    if len(hook_words) > 12:
        score -= 2.0
    if any(phrase in combined for phrase in GENERIC_INFLUENCER_PHRASES):
        score -= 4.0
    if any(phrase in combined for phrase in FORCED_SLANG_PHRASES):
        score -= 3.0
    return score


def _select_best_hook_variant(variants: list[dict], base_content: dict | None = None) -> dict:
    scored = []
    for index, variant in enumerate(variants, start=1):
        normalized = _normalize_hook_variant(variant, fallback_style=f"hook_variant_{index}")
        normalized["hook_score"] = _score_hook_variant(normalized, base_content)
        scored.append(normalized)
    if not scored:
        raise ValueError("Hook variant generation returned no usable variants.")
    return max(scored, key=lambda item: item["hook_score"])


def _candidate_rejection_reasons(candidate: dict) -> list[str]:
    reasons: list[str] = []
    overlay = _clean_line(candidate.get("overlay_text") or "", max_len=90)
    hook = _clean_line(candidate.get("caption_hook") or "", max_len=110)
    body = _clean_line(candidate.get("post_body") or "", max_len=320)
    combined = " ".join(part for part in [overlay, hook, body] if part).strip()
    combined_lower = combined.lower()
    target_outcome = _clean_line(candidate.get("target_outcome") or "", max_len=12).lower()
    pillar = _clean_line(candidate.get("content_pillar") or "", max_len=40)
    mechanism = _clean_line(candidate.get("comedic_mechanism") or "", max_len=50)
    scene_anchor = _clean_line(candidate.get("scene_anchor") or "", max_len=80)

    if not overlay:
        reasons.append("missing_overlay_text")
    if not hook:
        reasons.append("missing_caption_hook")
    if not body:
        reasons.append("missing_post_body")
    if not scene_anchor:
        reasons.append("missing_scene_anchor")
    if target_outcome not in TARGET_OUTCOMES:
        reasons.append("invalid_target_outcome")
    if pillar and pillar not in CONTENT_PILLARS:
        reasons.append("invalid_content_pillar")
    if mechanism and mechanism not in COMEDIC_MECHANISMS:
        reasons.append("invalid_comedic_mechanism")
    if len(hook.split()) > 12:
        reasons.append("hook_too_long")
    if len(overlay.split()) > 9:
        reasons.append("overlay_too_long")
    if len(body.split()) > 40:
        reasons.append("body_overexplains")
    if not any(ch in body for ch in ".!?"):
        reasons.append("body_lacks_second_beat")
    if any(phrase in combined_lower for phrase in GENERIC_INFLUENCER_PHRASES):
        reasons.append("generic_influencer_phrasing")
    if any(phrase in combined_lower for phrase in FORCED_SLANG_PHRASES):
        reasons.append("forced_slang")
    if "explain" in combined_lower or "this is about" in combined_lower or "basically" in combined_lower:
        reasons.append("overexplaining")
    myth_terms = (
        "zeus", "hera", "athena", "apollo", "artemis", "aphrodite", "ares", "poseidon",
        "hades", "persephone", "hermes", "oracle", "prophecy", "fate", "olympus",
        "mortal", "god", "goddess", "nymph", "titan", "medusa", "icarus"
    )
    if not any(term in combined_lower for term in myth_terms):
        reasons.append("not_myth_specific")
    if scene_anchor:
        anchor_tokens = [token for token in scene_anchor.lower().split() if len(token) > 2]
        if anchor_tokens and not any(token in combined_lower for token in anchor_tokens):
            reasons.append("scene_anchor_not_used")
    return reasons


def _filter_candidates(candidates: list[dict]) -> list[dict]:
    approved: list[dict] = []
    fallback: list[dict] = []
    for candidate in candidates:
        reasons = _candidate_rejection_reasons(candidate)
        candidate_with_meta = {
            **candidate,
            "rejection_reasons": reasons,
        }
        fallback.append(candidate_with_meta)
        if not reasons:
            approved.append(candidate_with_meta)
    return approved or fallback


def _compose_instagram_caption(content: dict) -> str:
    parts = [
        _clean_line(content.get("caption_hook", ""), max_len=110),
        _clean_line(content.get("post_body", ""), max_len=320),
        _clean_line(content.get("share_cta", ""), max_len=120),
    ]
    body = "\n\n".join(part for part in parts if part)
    hashtags = " ".join(_normalize_hashtags(content.get("hashtags", [])))
    if hashtags:
        body = f"{body}\n\n{hashtags}" if body else hashtags
    return body.strip()

def gen_theme(messages: list | None = None, model: str | None = None) -> str:
    system = BASE_SYSTEM + (
        "Propose a compelling mythic/fantasy theme that is based in Greek mythology "
        "and a character that exists in that period. Return only the theme text."
    )
    user = "Propose the theme now. Return only the theme text."
    return chat_step(messages, system, user, model)

def gen_visual_concept(messages: list, model: str | None = None) -> str:

    system = BASE_SYSTEM + "Generate only the Visual Concept. No commentary; return only the Visual Concept text."
    user = "Based on the theme above, write the Visual Concept. Return only the Visual Concept text."
    return chat_step(messages, system, user, model)

def gen_character_context(messages: list, model: str | None = None) -> str:
    """Generate the Character Context as a single string, using prior theme and visual concept."""
    system = BASE_SYSTEM + "Generate only the Character Context. No commentary; return only the Character Context text."
    user = (
        "Using the theme and Visual Concept above, write the Character Context. "
        "Return only the Character Context text."
    )
    return chat_step(messages, system, user, model)

def gen_caption(messages: list, model: str | None = None) -> str:
  
  system = BASE_SYSTEM + BASE_CAPTION
  user = (
      "Using the theme, Visual Concept, and Character Context above, write a concise meme caption. "
      "Use the caption template and examples in order to write the ideal caption based on the image"
      "Return only the caption text. The caption should be humorous and follow modern day memes and trends but also in line with the image"
  )
  return chat_step(messages, system, user, model)


def gen_caption_candidates(messages: list, model: str | None = None) -> list[dict]:
    system = BASE_SYSTEM + BASE_CAPTION + """
You are optimizing for Instagram engagement while staying tasteful and specific to the scene.
Return valid JSON only. No markdown fences and no commentary.
"""
    user = """
Using the theme, Visual Concept, and Character Context above, generate exactly 6 caption candidates.

Return JSON with this shape:
    {
      "candidates": [
        {
          "style_label": "short_snake_case_style_name",
          "content_pillar": "one of: relatable_modern_pain, petty_god_behavior, motivational_one_liners, relationship_memes, oracle_office_humor",
          "comedic_mechanism": "one of: absurd_contrast, painful_relatability, deadpan, hyper_specific_modern_reference, elegant_melancholy, savage_observational_humor",
          "target_outcome": "share | save | comment | follow",
          "scene_anchor": "specific visual detail from the scene that makes this caption feel image-specific",
          "overlay_text": "Very short on-image text, 3 to 9 words max.",
          "caption_hook": "Strong first-line hook for the post caption, 4 to 12 words.",
          "post_body": "One or two short sentences that deepen the joke without overexplaining it.",
          "share_cta": "A short natural call to action that motivates sending/saving/commenting without sounding desperate.",
          "hashtags": ["#example1", "#example2"],
          "first_comment": "Optional short first comment that continues the bit."
    }
  ]
}

Constraints:
- Each candidate must use a different content pillar or comedic mechanism.
- Use each comedic mechanism at most once.
- Spread the target outcomes across the set instead of repeating the same one six times.
- The scene_anchor must point to a concrete detail from the image concept.
- Overlay text must be punchy and readable on the image.
- Caption hooks should feel scroll-stopping, specific, and understandable immediately.
- Post body should add context or a second beat, not repeat the hook.
- Add a natural action prompt, usually send-focused, such as "Send this to the friend who..." when it fits the joke.
- Avoid needy engagement bait. The call to action must feel like part of the bit.
- Hashtags should be niche and relevant, 5 to 10 total.
- Keep everything Instagram-safe and avoid generic influencer phrasing.
- Do not use forced slang, filler, or captions that could fit any image.
"""
    raw = chat_step(messages, system, user, model)
    payload = _extract_json_payload(raw)
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Caption candidate generation did not return a non-empty candidates list.")
    normalized = []
    for index, candidate in enumerate(candidates, start=1):
        if isinstance(candidate, dict):
            normalized.append(_normalize_candidate(candidate, fallback_style=f"candidate_{index}"))
    if not normalized:
        raise ValueError("Caption candidate generation returned malformed candidates.")
    return _filter_candidates(normalized[:6])


def select_best_content(messages: list, candidates: list[dict], model: str | None = None) -> dict:
    system = BASE_SYSTEM + """
You are selecting and refining the strongest Instagram content option for engagement.
Prioritize hook strength, clarity, instant comprehension, DM send potential, shareability, visual match, and restraint.
Return valid JSON only. No markdown fences and no commentary.
"""
    candidate_block = json.dumps({"candidates": candidates}, ensure_ascii=True, indent=2)
    user = f"""
Choose the single best candidate for engagement from the JSON below and lightly refine it.

{candidate_block}

Return JSON with this shape:
{{
  "style_label": "chosen_style",
  "content_pillar": "chosen pillar key",
  "comedic_mechanism": "chosen mechanism key",
  "target_outcome": "share | save | comment | follow",
  "scene_anchor": "specific visual detail carried through from the chosen candidate",
  "overlay_text": "final short on-image text",
  "caption_hook": "final first-line hook",
  "post_body": "final supporting body copy",
  "share_cta": "final natural send/save/comment call to action",
  "hashtags": ["#tag1", "#tag2"],
  "first_comment": "optional short first comment",
  "selection_reason": "brief plain-English reason"
}}

Constraints:
- Overlay text must stay concise and visually readable.
- The first line should be the strongest hook and understandable in under 2 seconds.
- The post body should add a second beat, not restate the first line.
- The joke should work for someone with only basic mythology knowledge.
- Strongly prefer candidates that a viewer would send to a specific friend.
- If two candidates are close, choose the one with higher send potential.
- Choose a candidate that feels specific enough to share or save, not merely clever.
- Include a CTA that motivates action without saying "please like" or feeling spammy.
- Keep hashtags relevant and not spammy.
- Reject anything generic, overexplained, or swappable onto a different image.
"""
    raw = chat_step(messages, system, user, model)
    payload = _extract_json_payload(raw)
    selected = _normalize_candidate(payload, fallback_style="selected")
    selected["selection_reason"] = _clean_line(payload.get("selection_reason") or "", max_len=180)
    selected["share_cta"] = _clean_line(payload.get("share_cta") or "", max_len=120)
    selected["rejection_reasons"] = _candidate_rejection_reasons(selected)
    selected["instagram_caption"] = _compose_instagram_caption(selected)
    return selected


def gen_hook_variants(messages: list, selected: dict, model: str | None = None) -> list[dict]:
    system = BASE_SYSTEM + BASE_CAPTION + """
You are creating first-frame hook variants for an Instagram Reel.
Optimize for DM sends, watch completion, clarity, and instant comprehension.
Return valid JSON only. No markdown fences and no commentary.
"""
    selected_block = json.dumps(selected, ensure_ascii=True, indent=2)
    user = f"""
Using the selected content package below, create exactly 5 alternative hook variants.

{selected_block}

Return JSON with this shape:
{{
  "hooks": [
    {{
      "hook_style": "short_snake_case_style",
      "overlay_text": "3 to 8 words, readable in under 2 seconds",
      "caption_hook": "4 to 12 words, strong first line",
      "share_cta": "natural CTA, usually send-focused, tied to the joke",
      "score_reason": "brief reason this hook should improve sends or watch time"
    }}
  ]
}}

Constraints:
- Each hook should make a viewer think of a specific friend, situation, or group chat.
- Keep the overlay short enough for a static Reel first frame.
- Keep the mythology reference obvious to a casual viewer.
- Do not use generic engagement bait like "like and follow" or "drop a comment".
- Do not use forced slang.
- The CTA must sound like part of the joke, not marketing copy.
"""
    raw = chat_step(messages, system, user, model)
    payload = _extract_json_payload(raw)
    hooks = payload.get("hooks")
    if not isinstance(hooks, list) or not hooks:
        raise ValueError("Hook variant generation did not return a non-empty hooks list.")
    return [
        _normalize_hook_variant(hook, fallback_style=f"hook_variant_{index}")
        for index, hook in enumerate(hooks[:5], start=1)
        if isinstance(hook, dict)
    ]


def generate_content_package(model: str | None = None) -> dict:
    messages: list = []
    theme = gen_theme(messages, model=model)
    visual = gen_visual_concept(messages, model=model)
    character = gen_character_context(messages, model=model)
    candidates = gen_caption_candidates(messages, model=model)
    selected = select_best_content(messages, candidates, model=model)
    hook_generation_error = ""
    try:
        hook_variants = gen_hook_variants(messages, selected, model=model)
    except Exception as exc:
        hook_generation_error = _clean_line(str(exc), max_len=180)
        hook_variants = [
            {
                "hook_style": "selected_caption_fallback",
                "overlay_text": selected["overlay_text"],
                "caption_hook": selected["caption_hook"],
                "share_cta": selected.get("share_cta", ""),
                "score_reason": "Used selected caption because hook variant generation failed.",
            }
        ]
    selected_hook = _select_best_hook_variant(hook_variants, selected)
    selected["overlay_text"] = selected_hook["overlay_text"] or selected["overlay_text"]
    selected["caption_hook"] = selected_hook["caption_hook"] or selected["caption_hook"]
    selected["share_cta"] = selected_hook["share_cta"] or selected.get("share_cta", "")
    selected["hook_style"] = selected_hook["hook_style"]
    selected["hook_score"] = selected_hook["hook_score"]
    selected["hook_score_reason"] = selected_hook["score_reason"]
    selected["instagram_caption"] = _compose_instagram_caption(selected)

    return {
        "theme": theme,
        "visual_concept": visual,
        "character_context": character,
        "overlay_text": selected["overlay_text"] or selected["caption_hook"],
        "caption_hook": selected["caption_hook"],
        "post_body": selected["post_body"],
        "share_cta": selected.get("share_cta", ""),
        "hashtags": selected["hashtags"],
        "first_comment": selected["first_comment"],
        "hook_style": selected.get("hook_style", ""),
        "hook_score": selected.get("hook_score", 0.0),
        "hook_score_reason": selected.get("hook_score_reason", ""),
        "hook_generation_error": hook_generation_error,
        "style_label": selected["style_label"],
        "content_pillar": selected["content_pillar"],
        "comedic_mechanism": selected["comedic_mechanism"],
        "target_outcome": selected["target_outcome"],
        "scene_anchor": selected["scene_anchor"],
        "selection_reason": selected.get("selection_reason", ""),
        "rejection_reasons": selected.get("rejection_reasons", []),
        "instagram_caption": selected["instagram_caption"],
        "candidates": candidates,
        "hook_variants": hook_variants,
    }

def generate_all(model: str | None = None) -> tuple[str, str, str, str]:
    """
    Orchestrate the 4-step conversation:
      1) Theme 
      2) Visual Concept
      3) Character Context
      4) Caption

    Returns a tuple: (theme, visual_concept, character_context, caption)
    """
    package = generate_content_package(model=model)
    return (
        package["theme"],
        package["visual_concept"],
        package["character_context"],
        package["overlay_text"],
    )

def generate_image_prompt(theme, visual_concept, character_context, caption=None):
    rules = (
        "Make sure all critical content is Instagram-safe. Keep key subjects inside the centered safe zone, "
        "with at least 15% padding on the left and right, 12% padding on the top, and 18% padding on the bottom. "
        "Do not place faces, hands, or important props near the edges. "
        "Do not render any text, captions, letters, words, watermarks, logos, UI, signs, labels, subtitles, or typography in the image."
    )

    style_era = (
        """
            Late 1990s to early 2000s console graphics — transition from PlayStation 1 to Xbox and PlayStation 2 aesthetics. 
            Low-poly but detailed geometry, early real-time lighting, and smoother rendering."
        """
    )

    geometry = (
        """
            Moderate polygon counts with recognizable anatomy and structure, 
            simple but defined silhouettes, 
            low-res normal detail, clean UV layouts, 
            minimal vertex wobble.
        """
    )

    textures = (
        """
            Higher-resolution textures (128x128 to 256x256 px), bilinear filtering for smoother surfaces, 
            subtle pixelation retained for authenticity, 
            less dithering, baked lighting and ambient occlusion in textures
        """
    )

    rendering = (
        """
          Affine texture mapping (warped textures), 
          No perspective correction, 
          16-bit color depth with dithering, 
          Vertex jitter and aliasing, 
          No hardware z-buffer (polygon overlap flicker), 
          Limited texture resolution (64×64 px), 
          Gouraud shading, 
          Fog masking for draw distance, 
          Texture seams and popping geometry, 
          Flat ambient lighting, 
          320×240 render resolution, 
          True to PS1 rendering limitations,
          Gouraud and early Phong shading mix, early hardware lighting and shadow approximation, 
          partial z-buffer correction, stable perspective mapping, light fog for atmosphere.
        """
    )

    lighting = (
        """
          Soft ambient lighting with subtle contrast, early dynamic light sources (e.g., sunlight, reflections), 
          gentle specular highlights and environmental color tinting.
        """
    )

    color_palette = (
        """
          24-bit color depth, balanced saturation, 
          realistic but stylized tones, 
          limited banding, 
          slight CRT bloom or warmth.
        """
    )

    effects = (
        """
          Early particle systems for dust and light rays, 
          smooth transparency, 
          texture mipmapping, 
          atmospheric fog for depth, no harsh pixel stepping.
        """
    )

    resolution = (
        """
          Rendered at 640x480 or 720p equivalent with mild CRT bloom and film grain for authenticity.","overall_mood": 
          "Retro-futuristic adventure with nostalgic charm — evokes the technical quirks and warmth of early 3D console visuals.
        """
    )

    visual_style = {
        "style_era": {style_era},
        "geometry": {geometry},
        "textures": {textures},
        "rendering": {rendering},
        "lighting": {lighting},
        "color_palette": {color_palette},
        "effects": {effects},
        "resolution": {resolution}
        }
    
    instagram_reels_specs = {
        "render_resolution": "1024x1536 portrait source",
        "safe_area": (
            "Keep all important visual action and faces inside a centered 4:5 safe area so nothing important "
            "is cropped in the Instagram app preview, feed crop, or reel cover."
        ),
        "composition": (
            "Use a portrait composition with the main subject slightly larger in the middle, but never touching the side edges. "
            "Leave comfortable negative space on both sides and near the top so code-rendered meme text can be added later."
        ),
        "text_policy": (
            "Generate clean artwork only. The system will add the final overlay text after image generation, "
            "so the image itself must contain no readable or fake text."
        ),
    }


    prompt = f"""
    Create an image:

    rules: {rules}

    Theme: {theme}

    Visual Concept: {textwrap.fill(visual_concept, width=90)}
    Character Context: {textwrap.fill(character_context, width=90)}

    Visual Style: {visual_style}

    instagram_reels_specs: {instagram_reels_specs}

    Final framing requirement:
    The result must feel intentionally composed for Instagram mobile viewing.
    Nothing important should be cropped if the app trims the outer edges.
    Leave clean negative space for a later code-rendered text overlay, but do not draw the overlay text yourself.
    """

    return textwrap.dedent(prompt).strip()

def create_prompt():

  start_t=time.perf_counter()

  theme, visual, character, caption = generate_all()

  prompt = generate_image_prompt(theme,visual,character,caption)

  end_t=time.perf_counter()
  print(f"total runtime: {end_t-start_t:.2f}s")

  return prompt

def main():
    print("test create prompt")
    #create_prompt()

if __name__ == "__main__":
    main()
    
