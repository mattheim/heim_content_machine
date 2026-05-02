import json

from prompt_pipeline.captions.archetypes import CAPTION_ARCHETYPES
from prompt_pipeline.captions.normalize import (
    _compose_instagram_caption,
    _normalize_candidate,
    _normalize_hook_variant,
)
from prompt_pipeline.captions.prompts import BASE_CAPTION
from prompt_pipeline.captions.scoring import (
    _candidate_rejection_reasons,
    _filter_candidates,
    _judge_caption_candidate,
    _score_hook_variant,
    judge_caption_candidates,
)
from prompt_pipeline.content.prompts import BASE_SYSTEM
from prompt_pipeline.parsing import _clean_line, _extract_json_payload
from prompt_pipeline.providers import chat_step


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
    archetype_block = json.dumps(CAPTION_ARCHETYPES, ensure_ascii=True, indent=2)
    user = f"""
Using the theme, Visual Concept, and Character Context above, generate exactly 6 caption candidates.

Use these caption archetypes exactly once each across the 6 candidates:
{archetype_block}

Return JSON with this shape:
    {{
      "candidates": [
        {{
          "style_label": "short_snake_case_style_name",
          "caption_archetype": "one of: friend_send, oracle_warning, petty_god, modern_pain, relationship_myth, office_olympus",
          "archetype_reason": "brief reason this format fits the scene and caption",
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
    }}
  ]
}}

Constraints:
- Use each caption_archetype exactly once.
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
Use caption_scores as guidance: favor high two_second_clarity, visual_specificity, sendability, myth_accessibility, second_beat_strength, cta_naturalness, and archetype_fit.
Return valid JSON only. No markdown fences and no commentary.
"""
    judged_candidates = judge_caption_candidates(candidates)
    judged_candidates = sorted(
        judged_candidates,
        key=lambda item: item.get("caption_scores", {}).get("overall", 0.0),
        reverse=True,
    )
    candidate_block = json.dumps({"candidates": judged_candidates}, ensure_ascii=True, indent=2)
    user = f"""
Choose the single best candidate for engagement from the JSON below and lightly refine it.

{candidate_block}

Return JSON with this shape:
{{
  "style_label": "chosen_style",
  "caption_archetype": "chosen archetype key",
  "archetype_reason": "brief reason this format fits the scene and should drive engagement",
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
- Preserve the chosen candidate's caption_archetype unless refinement makes another archetype clearly more accurate.
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
    selected = _judge_caption_candidate(selected)
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


def _select_best_hook_variant(variants: list[dict], base_content: dict | None = None) -> dict:
    scored = []
    for index, variant in enumerate(variants, start=1):
        normalized = _normalize_hook_variant(variant, fallback_style=f"hook_variant_{index}")
        normalized["hook_score"] = _score_hook_variant(normalized, base_content)
        scored.append(normalized)
    if not scored:
        raise ValueError("Hook variant generation returned no usable variants.")
    return max(scored, key=lambda item: item["hook_score"])
