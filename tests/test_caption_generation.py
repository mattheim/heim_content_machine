from __future__ import annotations

import prompt_gen
from prompt_pipeline.captions import generator as caption_generator
from performance_feedback import build_performance_record, update_performance_record


def test_extract_json_payload_reads_json_from_code_fence():
    raw = """```json
    {
      "candidates": [
        {
          "style_label": "dramatic_prophecy",
          "overlay_text": "The oracle sent receipts"
        }
      ]
    }
    ```"""

    payload = prompt_gen._extract_json_payload(raw)

    assert payload["candidates"][0]["style_label"] == "dramatic_prophecy"


def test_extract_json_payload_reads_prefaced_json_response():
    raw = """Here are the 6 caption candidates:

    {
      "candidates": [
        {
          "style_label": "friend_send",
          "caption_archetype": "friend_send",
          "archetype_reason": "Send this to anyone who has tried to fix a clockwork owl.",
          "content_pillar": "relatable_modern_pain",
          "comedic_mechanism": "painful_relatability",
          "target_outcome": "share",
          "scene_anchor": "clockwork owl",
          "overlay_text": "Athena saw the repair bill",
          "caption_hook": "Athena saw the repair bill.",
          "post_body": "Wisdom still does not cover parts and labor.",
          "share_cta": "Send this to the friend who fixes one thing and breaks three.",
          "hashtags": ["#athena", "#greekmyth"],
          "first_comment": "The owl needs a union."
        }
      ]
    }

    Hope these help."""

    payload = prompt_gen._extract_json_payload(raw)

    assert payload["candidates"][0]["scene_anchor"] == "clockwork owl"


def test_extract_json_payload_recovers_trailing_commas():
    raw = """
    {
      "candidates": [
        {
          "style_label": "oracle_warning",
        }
      ],
    }
    """

    payload = prompt_gen._extract_json_payload(raw)

    assert payload["candidates"][0]["style_label"] == "oracle_warning"


def test_normalize_candidate_cleans_lengths_and_hashtags():
    normalized = prompt_gen._normalize_candidate(
        {
            "style_label": "  divine_chaos  ",
            "caption_archetype": " petty_god ",
            "archetype_reason": " Athena is judging a mortal habit. ",
            "content_pillar": " petty_god_behavior ",
            "comedic_mechanism": " deadpan ",
            "target_outcome": " SHARE ",
            "scene_anchor": " browser tabs ",
            "overlay_text": ' "Athena saw your browser tabs" ',
            "caption_hook": " Athena saw your browser tabs again. ",
            "post_body": "  She is not mad, just deeply disappointed.  ",
            "share_cta": " Send this to the friend who keeps doing this. ",
            "hashtags": ["GreekMyth", "#Athena!!", " wisdom "],
            "first_comment": "  Olympus has notes. ",
        },
        fallback_style="fallback_style",
    )

    assert normalized["style_label"] == "divine_chaos"
    assert normalized["caption_archetype"] == "petty_god"
    assert normalized["archetype_reason"] == "Athena is judging a mortal habit."
    assert normalized["overlay_text"] == "Athena saw your browser tabs"
    assert normalized["caption_hook"] == "Athena saw your browser tabs again."
    assert normalized["post_body"] == "She is not mad, just deeply disappointed."
    assert normalized["share_cta"] == "Send this to the friend who keeps doing this."
    assert normalized["hashtags"] == ["#greekmyth", "#athena", "#wisdom"]
    assert normalized["first_comment"] == "Olympus has notes."
    assert normalized["content_pillar"] == "petty_god_behavior"
    assert normalized["comedic_mechanism"] == "deadpan"
    assert normalized["target_outcome"] == "share"
    assert normalized["scene_anchor"] == "browser tabs"


def test_generate_content_package_returns_expected_fields(monkeypatch):
    monkeypatch.setattr(prompt_gen, "gen_theme", lambda messages, model=None: "Ares discovers group chats")
    monkeypatch.setattr(
        prompt_gen,
        "gen_visual_concept",
        lambda messages, model=None: "A low-poly war god glaring at glowing scroll notifications.",
    )
    monkeypatch.setattr(
        prompt_gen,
        "gen_character_context",
        lambda messages, model=None: "Ares is offended that mortals keep leaving him on read.",
    )
    monkeypatch.setattr(
        prompt_gen,
        "gen_caption_candidates",
        lambda messages, model=None: [
            {
                "style_label": "petty_god",
                "caption_archetype": "friend_send",
                "archetype_reason": "This is built for sending to a group chat chaos friend.",
                "content_pillar": "petty_god_behavior",
                "comedic_mechanism": "painful_relatability",
                "target_outcome": "share",
                "scene_anchor": "group chat",
                "overlay_text": "Left on read by mortals",
                "caption_hook": "Ares when the group chat goes silent.",
                "post_body": "He brought chaos and still got ghosted.",
                "share_cta": "Send this to the friend who starts chaos then disappears.",
                "hashtags": ["#GreekMyth", "#Ares", "#MythMeme"],
                "first_comment": "Olympus has seen enough.",
            }
        ],
    )
    monkeypatch.setattr(
        prompt_gen,
        "select_best_content",
        lambda messages, candidates, model=None: {
            **candidates[0],
            "selection_reason": "Best hook strength.",
            "rejection_reasons": [],
            "instagram_caption": (
                "Ares when the group chat goes silent.\n\n"
                "He brought chaos and still got ghosted.\n\n"
                "Send this to the friend who starts chaos then disappears.\n\n"
                "#greekmyth #ares #mythmeme"
            ),
        },
    )
    monkeypatch.setattr(
        prompt_gen,
        "gen_hook_variants",
        lambda messages, selected, model=None: [
            {
                "hook_style": "group_chat_send",
                "overlay_text": "Olympus saw the group chat",
                "caption_hook": "Ares when the group chat goes silent.",
                "share_cta": "Send this to the friend who starts chaos then disappears.",
                "score_reason": "Specific friend-sharing setup.",
            }
        ],
    )

    package = prompt_gen.generate_content_package()

    assert package["theme"] == "Ares discovers group chats"
    assert package["overlay_text"] == "Olympus saw the group chat"
    assert package["caption_hook"] == "Ares when the group chat goes silent."
    assert package["instagram_caption"].startswith("Ares when the group chat goes silent.")
    assert package["hashtags"] == ["#GreekMyth", "#Ares", "#MythMeme"]
    assert package["content_pillar"] == "petty_god_behavior"
    assert package["comedic_mechanism"] == "painful_relatability"
    assert package["target_outcome"] == "share"
    assert package["scene_anchor"] == "group chat"
    assert package["caption_archetype"] == "friend_send"
    assert package["archetype_reason"] == "This is built for sending to a group chat chaos friend."
    assert package["hook_style"] == "group_chat_send"
    assert package["share_cta"] == "Send this to the friend who starts chaos then disappears."
    assert package["caption_scores"]["overall"] > 0
    assert package["judge_notes"]
    assert len(package["candidates"]) == 1
    assert len(package["hook_variants"]) == 1


def test_gen_caption_candidates_normalizes_model_response(monkeypatch):
    raw_json = """
    {
      "candidates": [
        {
          "style_label": " petty_god ",
          "caption_archetype": "petty_god",
          "archetype_reason": "Zeus overreacts to one attractive mortal.",
          "content_pillar": "petty_god_behavior",
          "comedic_mechanism": "savage_observational_humor",
          "target_outcome": "share",
          "scene_anchor": "attractive mortal",
          "overlay_text": " Zeus saw one attractive mortal ",
          "caption_hook": "Zeus exercising zero restraint.",
          "post_body": "Olympus HR is exhausted.",
          "hashtags": ["GreekMyth", "#Zeus"],
          "first_comment": "Thunder pending."
        }
      ]
    }
    """

    monkeypatch.setattr(caption_generator, "chat_step", lambda messages, system, user, model=None: raw_json)

    candidates = prompt_gen.gen_caption_candidates(messages=[])

    assert len(candidates) == 1
    assert candidates[0]["style_label"] == "petty_god"
    assert candidates[0]["caption_archetype"] == "petty_god"
    assert candidates[0]["archetype_reason"] == "Zeus overreacts to one attractive mortal."
    assert candidates[0]["overlay_text"] == "Zeus saw one attractive mortal"
    assert candidates[0]["hashtags"] == ["#greekmyth", "#zeus"]
    assert candidates[0]["target_outcome"] == "share"
    assert candidates[0]["rejection_reasons"] == []
    assert candidates[0]["caption_scores"]["overall"] > 0
    assert candidates[0]["judge_notes"]


def test_caption_judge_scores_field_specific_strengths():
    strong = prompt_gen._judge_caption_candidate(
        {
            "style_label": "oracle_send",
            "caption_archetype": "oracle_warning",
            "archetype_reason": "The joke turns on ignoring the warning.",
            "content_pillar": "oracle_office_humor",
            "comedic_mechanism": "deadpan",
            "target_outcome": "share",
            "scene_anchor": "oracle printer",
            "overlay_text": "Oracle jammed the printer",
            "caption_hook": "The oracle jammed the printer again.",
            "post_body": "Fate still wants that report by noon.",
            "share_cta": "Send this to the friend who treats warnings like suggestions.",
            "hashtags": ["#oracle", "#greekmyth"],
            "first_comment": "The fates need toner.",
        }
    )
    weak = prompt_gen._judge_caption_candidate(
        {
            "style_label": "generic",
            "caption_archetype": "friend_send",
            "archetype_reason": "",
            "content_pillar": "petty_god_behavior",
            "comedic_mechanism": "deadpan",
            "target_outcome": "comment",
            "scene_anchor": "",
            "overlay_text": "Main character energy only forever",
            "caption_hook": "Main character energy only forever and ever.",
            "post_body": "This is about mythology and basically the joke is that gods are dramatic.",
            "share_cta": "Drop a comment and link in bio.",
            "hashtags": ["#greekmyth"],
            "first_comment": "",
        }
    )

    assert strong["caption_scores"]["overall"] > weak["caption_scores"]["overall"]
    assert strong["caption_scores"]["two_second_clarity"] >= 4
    assert strong["caption_scores"]["visual_specificity"] >= 4
    assert strong["caption_scores"]["sendability"] >= 4
    assert strong["caption_scores"]["archetype_fit"] >= 4
    assert weak["caption_scores"]["cta_naturalness"] < strong["caption_scores"]["cta_naturalness"]


def test_normalize_candidate_defaults_unknown_archetype():
    normalized = prompt_gen._normalize_candidate(
        {
            "style_label": "unknown_format",
            "caption_archetype": "mystery_box",
            "overlay_text": "Hermes saw the memo",
            "caption_hook": "Hermes saw the memo first.",
            "post_body": "Now fate has a paper trail.",
            "hashtags": ["#hermes"],
        },
        fallback_style="fallback_style",
    )

    assert normalized["caption_archetype"] == "friend_send"


def test_select_best_content_builds_instagram_caption(monkeypatch):
    selection_json = """
    {
      "style_label": "oracle_dunk",
      "caption_archetype": "oracle_warning",
      "archetype_reason": "The warning was clear and ignored.",
      "content_pillar": "oracle_office_humor",
      "comedic_mechanism": "deadpan",
      "target_outcome": "save",
      "scene_anchor": "prophecy",
      "overlay_text": "The prophecy was very clear",
      "caption_hook": "The prophecy was very clear.",
      "post_body": "You still chose chaos anyway.",
      "share_cta": "Send this to the friend who treats warnings like suggestions.",
      "hashtags": ["#oracle", "GreekMyth"],
      "first_comment": "Fate loves being ignored.",
      "selection_reason": "Strongest mix of clarity and humor."
    }
    """

    monkeypatch.setattr(caption_generator, "chat_step", lambda messages, system, user, model=None: selection_json)

    selected = prompt_gen.select_best_content(
        messages=[],
        candidates=[
            {
                "style_label": "backup",
                "content_pillar": "oracle_office_humor",
                "comedic_mechanism": "deadpan",
                "target_outcome": "comment",
                "scene_anchor": "backup",
                "overlay_text": "backup text",
                "caption_hook": "backup hook",
                "post_body": "backup body",
                "hashtags": ["#backup"],
                "first_comment": "backup comment",
            }
        ],
    )

    assert selected["style_label"] == "oracle_dunk"
    assert selected["caption_archetype"] == "oracle_warning"
    assert selected["archetype_reason"] == "The warning was clear and ignored."
    assert selected["selection_reason"] == "Strongest mix of clarity and humor."
    assert selected["target_outcome"] == "save"
    assert selected["share_cta"] == "Send this to the friend who treats warnings like suggestions."
    assert selected["instagram_caption"] == (
        "The prophecy was very clear.\n\n"
        "You still chose chaos anyway.\n\n"
        "Send this to the friend who treats warnings like suggestions.\n\n"
        "#oracle #greekmyth"
    )


def test_candidate_rejection_reasons_flags_weak_copy():
    reasons = prompt_gen._candidate_rejection_reasons(
        {
            "style_label": "generic",
            "content_pillar": "petty_god_behavior",
            "comedic_mechanism": "deadpan",
            "target_outcome": "share",
            "scene_anchor": "",
            "overlay_text": "Main character energy only",
            "caption_hook": "POV: main character energy only",
            "post_body": "This is about how gods are dramatic and basically that is the whole joke link in bio",
            "hashtags": ["#greekmyth"],
            "first_comment": "",
        }
    )

    assert "missing_scene_anchor" in reasons
    assert "generic_influencer_phrasing" in reasons
    assert "overexplaining" in reasons
    assert "not_myth_specific" not in reasons


def test_filter_candidates_prefers_approved_candidates():
    approved = {
        "style_label": "oracle_dunk",
        "content_pillar": "oracle_office_humor",
        "comedic_mechanism": "deadpan",
        "target_outcome": "save",
        "scene_anchor": "oracle printer",
        "overlay_text": "Oracle jammed the printer",
        "caption_hook": "The oracle jammed the printer.",
        "post_body": "Fate still wants that report by noon.",
        "hashtags": ["#oracle", "#greekmyth"],
        "first_comment": "The fates need toner.",
    }
    rejected = {
        "style_label": "generic",
        "content_pillar": "petty_god_behavior",
        "comedic_mechanism": "deadpan",
        "target_outcome": "share",
        "scene_anchor": "",
        "overlay_text": "Main character energy only",
        "caption_hook": "POV: main character energy only",
        "post_body": "This is about how gods are dramatic and basically that is the whole joke link in bio",
        "hashtags": ["#greekmyth"],
        "first_comment": "",
    }

    filtered = prompt_gen._filter_candidates([approved, rejected])

    assert len(filtered) == 1
    assert filtered[0]["style_label"] == "oracle_dunk"
    assert filtered[0]["rejection_reasons"] == []
    assert filtered[0]["caption_scores"]["overall"] > 0


def test_compose_instagram_caption_formats_body_and_hashtags():
    caption = prompt_gen._compose_instagram_caption(
        {
            "caption_hook": "Hermes saw the typo first.",
            "post_body": "Now the prophecy needs a revision.",
            "share_cta": "Send this to the friend who proofreads fate.",
            "hashtags": ["GreekMyth", "#Hermes", "oracle"],
        }
    )

    assert caption == (
        "Hermes saw the typo first.\n\n"
        "Now the prophecy needs a revision.\n\n"
        "Send this to the friend who proofreads fate.\n\n"
        "#greekmyth #hermes #oracle"
    )


def test_select_best_hook_variant_scores_send_focused_hooks():
    base_content = {"scene_anchor": "group chat"}
    selected = prompt_gen._select_best_hook_variant(
        [
            {
                "hook_style": "generic",
                "overlay_text": "Ares is annoyed again",
                "caption_hook": "Ares is annoyed again.",
                "share_cta": "",
            },
            {
                "hook_style": "send_friend",
                "overlay_text": "Olympus saw the group chat",
                "caption_hook": "Ares when the group chat goes silent.",
                "share_cta": "Send this to the friend who starts chaos then disappears.",
            },
        ],
        base_content,
    )

    assert selected["hook_style"] == "send_friend"
    assert selected["hook_score"] > 0


def test_gen_hook_variants_normalizes_model_response(monkeypatch):
    raw_json = """
    {
      "hooks": [
        {
          "hook_style": " send_friend ",
          "overlay_text": " Olympus saw the group chat ",
          "caption_hook": "Ares when the group chat goes silent.",
          "share_cta": "Send this to the friend who starts chaos then disappears.",
          "score_reason": "High send potential."
        }
      ]
    }
    """

    monkeypatch.setattr(caption_generator, "chat_step", lambda messages, system, user, model=None: raw_json)

    hooks = prompt_gen.gen_hook_variants(messages=[], selected={"caption_hook": "backup"})

    assert hooks[0]["hook_style"] == "send_friend"
    assert hooks[0]["overlay_text"] == "Olympus saw the group chat"


def test_performance_record_calculates_normalized_rates():
    record = build_performance_record(
        {
            "hook_style": "send_friend",
            "content_pillar": "petty_god_behavior",
            "comedic_mechanism": "deadpan",
        },
        duration=12,
    )
    updated = update_performance_record(
        record,
        {
            "reach": 1000,
            "shares": 50,
            "saves": 30,
            "likes": 120,
            "comments": 10,
            "watch_time": 9,
        },
    )

    assert updated["share_rate"] == 0.05
    assert updated["save_rate"] == 0.03
    assert updated["like_rate"] == 0.12
    assert updated["comment_rate"] == 0.01
    assert updated["completion_proxy"] == 0.75
    assert updated["hook_style"] == "send_friend"
