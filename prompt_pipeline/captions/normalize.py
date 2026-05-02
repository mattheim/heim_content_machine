from prompt_pipeline.captions.archetypes import CAPTION_ARCHETYPES
from prompt_pipeline.parsing import _clean_line, _normalize_hashtags


def _normalize_candidate(candidate: dict, fallback_style: str) -> dict:
    archetype = _clean_line(candidate.get("caption_archetype") or "", max_len=40)
    if archetype not in CAPTION_ARCHETYPES:
        archetype = "friend_send"
    return {
        "style_label": _clean_line(candidate.get("style_label") or fallback_style or "mythic_irony", max_len=40),
        "caption_archetype": archetype,
        "archetype_reason": _clean_line(candidate.get("archetype_reason") or "", max_len=180),
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
