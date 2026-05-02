from __future__ import annotations

import json

from performance_report import group_records, load_content_records, summarize_records


def _write_record(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_content_records_reads_metadata_and_recalculates_rates(tmp_path):
    _write_record(
        tmp_path / "20260502_120000_test.json",
        {
            "generated_at": "20260502_120000",
            "overlay_text": "Olympus HR is exhausted",
            "caption_hook": "Olympus HR is exhausted.",
            "caption_archetype": "office_olympus",
            "hook_style": "office_hook",
            "content_pillar": "oracle_office_humor",
            "comedic_mechanism": "deadpan",
            "target_outcome": "share",
            "instagram_post_info": {"permalink": "https://instagram.example/p/1"},
            "performance": {
                "views": 100,
                "reach": 80,
                "likes": 10,
                "comments": 2,
                "shares": 8,
                "saves": 4,
                "watch_time": 9,
                "duration": 12,
            },
        },
    )

    records = load_content_records(tmp_path)

    assert len(records) == 1
    assert records[0]["caption_archetype"] == "office_olympus"
    assert records[0]["instagram_permalink"] == "https://instagram.example/p/1"
    assert records[0]["performance"]["share_rate"] == 0.1
    assert records[0]["performance"]["save_rate"] == 0.05


def test_summarize_records_counts_measured_and_missing_posts(tmp_path):
    _write_record(
        tmp_path / "20260502_120000_measured.json",
        {
            "caption_archetype": "friend_send",
            "performance": {
                "views": 50,
                "reach": 40,
                "shares": 4,
                "saves": 2,
                "likes": 5,
                "comments": 1,
            },
        },
    )
    _write_record(
        tmp_path / "20260502_130000_missing.json",
        {
            "caption_archetype": "oracle_warning",
            "performance": {
                "views": None,
                "reach": None,
                "shares": None,
                "saves": None,
            },
        },
    )

    summary = summarize_records(load_content_records(tmp_path))

    assert summary["total_posts"] == 2
    assert summary["measured_posts"] == 1
    assert summary["missing_metric_posts"] == 1
    assert summary["totals"]["views"] == 50
    assert summary["rates"]["share_rate"] == 0.1


def test_group_records_sorts_by_engagement_score(tmp_path):
    _write_record(
        tmp_path / "20260502_120000_friend.json",
        {
            "caption_archetype": "friend_send",
            "performance": {
                "views": 100,
                "reach": 100,
                "shares": 20,
                "saves": 10,
                "likes": 15,
                "comments": 4,
            },
        },
    )
    _write_record(
        tmp_path / "20260502_130000_oracle.json",
        {
            "caption_archetype": "oracle_warning",
            "performance": {
                "views": 200,
                "reach": 200,
                "shares": 1,
                "saves": 1,
                "likes": 5,
                "comments": 0,
            },
        },
    )

    groups = group_records(load_content_records(tmp_path), "caption_archetype")

    assert groups[0]["group"] == "friend_send"
    assert groups[0]["rates"]["engagement_score"] > groups[1]["rates"]["engagement_score"]
