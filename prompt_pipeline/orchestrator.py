from prompt_pipeline.captions.generator import (
    _select_best_hook_variant,
    gen_caption_candidates,
    gen_hook_variants,
    select_best_content,
)
from prompt_pipeline.captions.scoring import _judge_caption_candidate
from prompt_pipeline.content.generator import gen_character_context, gen_theme, gen_visual_concept
from prompt_pipeline.parsing import _clean_line


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
    selected = _judge_caption_candidate(selected)
    selected["instagram_caption"] = selected.get("instagram_caption") or ""
    from prompt_pipeline.captions.normalize import _compose_instagram_caption
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
        "caption_archetype": selected.get("caption_archetype", ""),
        "archetype_reason": selected.get("archetype_reason", ""),
        "hook_style": selected.get("hook_style", ""),
        "hook_score": selected.get("hook_score", 0.0),
        "hook_score_reason": selected.get("hook_score_reason", ""),
        "caption_scores": selected.get("caption_scores", {}),
        "judge_notes": selected.get("judge_notes", ""),
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
    package = generate_content_package(model=model)
    return (
        package["theme"],
        package["visual_concept"],
        package["character_context"],
        package["overlay_text"],
    )
