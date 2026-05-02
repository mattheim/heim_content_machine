from __future__ import annotations

from scripts.analyze_post_performance import calculate_view_reach_stats, top_performing_records, underperforming_records


def test_calculate_view_reach_stats_uses_measured_records_only():
    records = [
        {"performance": {"views": 100, "reach": 80}},
        {"performance": {"views": 50, "reach": 40}},
        {"performance": {"views": None, "reach": None}},
    ]

    stats = calculate_view_reach_stats(records)

    assert stats["total_posts"] == 3
    assert stats["measured_posts"] == 2
    assert stats["missing_posts"] == 1
    assert stats["avg_views"] == 75
    assert stats["avg_reach"] == 60
    assert stats["median_views"] == 75


def test_underperforming_records_flags_below_average_views_or_reach():
    records = [
        {"filename": "winner.json", "performance": {"views": 120, "reach": 100}},
        {"filename": "low_views.json", "performance": {"views": 40, "reach": 100}},
        {"filename": "low_reach.json", "performance": {"views": 120, "reach": 30}},
        {"filename": "missing.json", "performance": {"views": None, "reach": None}},
    ]

    underperformers = underperforming_records(records, view_threshold=80, reach_threshold=70)

    assert [record["filename"] for record in underperformers] == ["low_views.json", "low_reach.json"]
    assert underperformers[0]["views_delta"] == -40
    assert underperformers[1]["reach_delta"] == -40


def test_top_performing_records_prioritizes_views_then_engagement_signals():
    records = [
        {"filename": "mid.json", "performance": {"views": 100, "reach": 80, "shares": 2, "saves": 0}},
        {"filename": "top.json", "performance": {"views": 150, "reach": 100, "shares": 1, "saves": 1}},
        {"filename": "tie_winner.json", "performance": {"views": 150, "reach": 100, "shares": 3, "saves": 0}},
        {"filename": "missing.json", "performance": {"views": None, "reach": None}},
    ]

    performers = top_performing_records(records)

    assert [record["filename"] for record in performers] == ["tie_winner.json", "top.json", "mid.json"]
    assert performers[0]["share_rate"] == 0.03
