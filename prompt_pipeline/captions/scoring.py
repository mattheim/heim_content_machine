from prompt_pipeline.captions.archetypes import CAPTION_ARCHETYPES
from prompt_pipeline.parsing import _clean_line


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

MYTH_TERMS = (
    "zeus", "hera", "athena", "apollo", "artemis", "aphrodite", "ares", "poseidon",
    "hades", "persephone", "hermes", "oracle", "prophecy", "fate", "olympus",
    "mortal", "god", "goddess", "nymph", "titan", "medusa", "icarus"
)

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


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(5.0, value)), 2)


def _contains_myth_reference(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in MYTH_TERMS)


def _scene_anchor_tokens(scene_anchor: str) -> list[str]:
    return [
        token.strip(".,!?;:()[]{}\"'").lower()
        for token in scene_anchor.split()
        if len(token.strip(".,!?;:()[]{}\"'")) > 2
    ]


def _score_archetype_fit(candidate: dict, combined_lower: str, cta_lower: str) -> float:
    archetype = candidate.get("caption_archetype")
    if archetype not in CAPTION_ARCHETYPES:
        return 1.0

    score = 2.0
    if archetype == "friend_send":
        if any(word in cta_lower for word in ("send", "friend", "someone", "group chat")):
            score += 2.5
        if candidate.get("target_outcome") == "share":
            score += 0.5
    elif archetype == "oracle_warning":
        if any(word in combined_lower for word in ("oracle", "prophecy", "fate", "warning", "warned")):
            score += 2.5
        if any(word in combined_lower for word in ("ignored", "still", "anyway", "chose")):
            score += 0.5
    elif archetype == "petty_god":
        if any(word in combined_lower for word in ("personally", "petty", "offended", "rage", "zero restraint", "dramatic")):
            score += 1.5
        if any(word in combined_lower for word in ("zeus", "hera", "poseidon", "ares", "apollo", "athena", "god", "goddess")):
            score += 1.5
    elif archetype == "modern_pain":
        if any(word in combined_lower for word in ("calendar", "email", "browser", "text", "meeting", "deadline", "anxiety", "notifications")):
            score += 2.0
        if _contains_myth_reference(combined_lower):
            score += 1.0
    elif archetype == "relationship_myth":
        if any(word in combined_lower for word in ("text", "back", "ex", "date", "relationship", "crush", "jealous", "left on read", "looking back")):
            score += 2.5
        if any(word in combined_lower for word in ("aphrodite", "hera", "orpheus", "eurydice", "persephone")):
            score += 0.5
    elif archetype == "office_olympus":
        if any(word in combined_lower for word in ("hr", "meeting", "report", "printer", "calendar", "office", "memo", "deadline")):
            score += 2.5
        if any(word in combined_lower for word in ("olympus", "oracle", "fate", "gods")):
            score += 0.5
    return _clamp_score(score)


def _score_caption_candidate(candidate: dict) -> dict:
    overlay = _clean_line(candidate.get("overlay_text") or "", max_len=90)
    hook = _clean_line(candidate.get("caption_hook") or "", max_len=110)
    body = _clean_line(candidate.get("post_body") or "", max_len=320)
    cta = _clean_line(candidate.get("share_cta") or "", max_len=120)
    scene_anchor = _clean_line(candidate.get("scene_anchor") or "", max_len=80)
    combined = " ".join(part for part in [overlay, hook, body, cta] if part)
    combined_lower = combined.lower()

    overlay_words = overlay.split()
    hook_words = hook.split()
    body_words = body.split()
    cta_lower = cta.lower()
    anchor_tokens = _scene_anchor_tokens(scene_anchor)

    two_second_clarity = 0.0
    if 3 <= len(overlay_words) <= 8:
        two_second_clarity += 3.0
    elif 1 <= len(overlay_words) <= 10:
        two_second_clarity += 1.5
    if 4 <= len(hook_words) <= 12:
        two_second_clarity += 1.25
    if _contains_myth_reference(" ".join([overlay, hook])):
        two_second_clarity += 0.75
    if len(overlay_words) > 9 or len(hook_words) > 14:
        two_second_clarity -= 1.5

    visual_specificity = 0.0
    if scene_anchor:
        visual_specificity += 2.0
    if anchor_tokens and any(token in combined_lower for token in anchor_tokens):
        visual_specificity += 2.25
    if _contains_myth_reference(combined):
        visual_specificity += 0.75

    sendability = 0.0
    if any(pattern.lower() in cta_lower for pattern in SHARE_CTA_PATTERNS):
        sendability += 3.0
    if any(word in " ".join([hook, body, cta]).lower() for word in ("friend", "someone", "group chat", "send", "save")):
        sendability += 1.5
    if candidate.get("target_outcome") in {"share", "save"}:
        sendability += 0.5
    if any(phrase in combined_lower for phrase in GENERIC_INFLUENCER_PHRASES):
        sendability -= 2.0

    myth_accessibility = 0.0
    if _contains_myth_reference(combined):
        myth_accessibility += 3.5
    if any(term in combined_lower for term in ("olympus", "oracle", "prophecy", "fate", "god", "goddess")):
        myth_accessibility += 1.0
    if len([word for word in combined.split() if len(word) > 12]) > 3:
        myth_accessibility -= 0.75

    second_beat_strength = 0.0
    if 5 <= len(body_words) <= 24:
        second_beat_strength += 2.0
    elif body_words:
        second_beat_strength += 0.75
    if any(ch in body for ch in ".!?"):
        second_beat_strength += 0.75
    if body and hook and body.lower() not in hook.lower() and hook.lower() not in body.lower():
        second_beat_strength += 1.5
    if any(word in body.lower() for word in ("still", "anyway", "meanwhile", "because", "now", "again")):
        second_beat_strength += 0.75
    if "this is about" in body.lower() or "basically" in body.lower() or len(body_words) > 40:
        second_beat_strength -= 2.0

    cta_naturalness = 0.0
    if cta:
        cta_naturalness += 1.5
    if any(pattern.lower() in cta_lower for pattern in SHARE_CTA_PATTERNS):
        cta_naturalness += 1.5
    if any(token in cta_lower for token in anchor_tokens):
        cta_naturalness += 0.75
    if _contains_myth_reference(cta) or any(word in cta_lower for word in ("friend", "someone", "group chat")):
        cta_naturalness += 0.75
    if any(phrase in cta_lower for phrase in ("please like", "like and follow", "drop a comment", "link in bio")):
        cta_naturalness -= 2.5

    archetype_fit = _score_archetype_fit(candidate, combined_lower, cta_lower)

    scores = {
        "two_second_clarity": _clamp_score(two_second_clarity),
        "visual_specificity": _clamp_score(visual_specificity),
        "sendability": _clamp_score(sendability),
        "myth_accessibility": _clamp_score(myth_accessibility),
        "second_beat_strength": _clamp_score(second_beat_strength),
        "cta_naturalness": _clamp_score(cta_naturalness),
        "archetype_fit": archetype_fit,
    }
    scores["overall"] = round(
        (
            scores["two_second_clarity"] * 1.3
            + scores["visual_specificity"] * 1.2
            + scores["sendability"] * 1.35
            + scores["myth_accessibility"]
            + scores["second_beat_strength"] * 1.15
            + scores["cta_naturalness"]
            + scores["archetype_fit"] * 0.8
        )
        / 7.8,
        2,
    )
    return scores


def _caption_judge_notes(candidate: dict, scores: dict) -> str:
    weak = [name for name, value in scores.items() if name != "overall" and value < 2.5]
    strong = [name for name, value in scores.items() if name != "overall" and value >= 4.0]
    if weak:
        return _clean_line(f"Needs work on {', '.join(weak[:2])}.", max_len=180)
    if strong:
        return _clean_line(f"Strongest on {', '.join(strong[:2])}.", max_len=180)
    return "Balanced caption with no major scoring gaps."


def _judge_caption_candidate(candidate: dict) -> dict:
    scores = _score_caption_candidate(candidate)
    return {
        **candidate,
        "caption_scores": scores,
        "judge_notes": _caption_judge_notes(candidate, scores),
    }


def judge_caption_candidates(candidates: list[dict]) -> list[dict]:
    return [_judge_caption_candidate(candidate) for candidate in candidates]


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

    if _contains_myth_reference(combined):
        score += 1.5

    scene_anchor = ""
    if base_content:
        scene_anchor = _clean_line(base_content.get("scene_anchor") or "", max_len=80)
    if scene_anchor:
        anchor_tokens = _scene_anchor_tokens(scene_anchor)
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
    if not _contains_myth_reference(combined_lower):
        reasons.append("not_myth_specific")
    if scene_anchor:
        anchor_tokens = _scene_anchor_tokens(scene_anchor)
        if anchor_tokens and not any(token in combined_lower for token in anchor_tokens):
            reasons.append("scene_anchor_not_used")
    return reasons


def _filter_candidates(candidates: list[dict]) -> list[dict]:
    approved: list[dict] = []
    fallback: list[dict] = []
    for candidate in candidates:
        reasons = _candidate_rejection_reasons(candidate)
        judged = _judge_caption_candidate(candidate)
        candidate_with_meta = {
            **judged,
            "rejection_reasons": reasons,
        }
        fallback.append(candidate_with_meta)
        if not reasons:
            approved.append(candidate_with_meta)
    ranked = approved or fallback
    return sorted(
        ranked,
        key=lambda item: item.get("caption_scores", {}).get("overall", 0.0),
        reverse=True,
    )
