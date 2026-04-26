from __future__ import annotations

from datetime import datetime
from typing import Any


PERFORMANCE_METRIC_FIELDS = (
    "views",
    "likes",
    "comments",
    "shares",
    "saves",
    "reach",
    "watch_time",
    "follows",
)


def _safe_number(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def empty_performance_metrics() -> dict:
    metrics = {field: None for field in PERFORMANCE_METRIC_FIELDS}
    metrics.update(
        {
            "posted_at": None,
            "duration": None,
            "hook_style": None,
            "content_pillar": None,
            "comedic_mechanism": None,
            "share_rate": None,
            "save_rate": None,
            "like_rate": None,
            "comment_rate": None,
            "completion_proxy": None,
            "engagement_score": None,
            "updated_at": None,
        }
    )
    return metrics


def calculate_performance_rates(metrics: dict) -> dict:
    reach = _safe_number(metrics.get("reach"))
    duration = _safe_number(metrics.get("duration"))
    watch_time = _safe_number(metrics.get("watch_time"))

    rates = {
        "share_rate": None,
        "save_rate": None,
        "like_rate": None,
        "comment_rate": None,
        "completion_proxy": None,
        "engagement_score": None,
    }
    if reach > 0:
        rates["share_rate"] = _safe_number(metrics.get("shares")) / reach
        rates["save_rate"] = _safe_number(metrics.get("saves")) / reach
        rates["like_rate"] = _safe_number(metrics.get("likes")) / reach
        rates["comment_rate"] = _safe_number(metrics.get("comments")) / reach
    if duration > 0:
        rates["completion_proxy"] = watch_time / duration

    share_rate = rates["share_rate"] or 0.0
    save_rate = rates["save_rate"] or 0.0
    like_rate = rates["like_rate"] or 0.0
    comment_rate = rates["comment_rate"] or 0.0
    completion_proxy = rates["completion_proxy"] or 0.0
    rates["engagement_score"] = (
        share_rate * 5.0
        + save_rate * 3.0
        + comment_rate * 2.0
        + like_rate
        + completion_proxy * 0.5
    )
    return rates


def build_performance_record(content: dict, duration: float, posted_at: str | None = None) -> dict:
    metrics = empty_performance_metrics()
    metrics.update(
        {
            "posted_at": posted_at,
            "duration": duration,
            "hook_style": content.get("hook_style"),
            "content_pillar": content.get("content_pillar"),
            "comedic_mechanism": content.get("comedic_mechanism"),
            "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
    )
    metrics.update(calculate_performance_rates(metrics))
    return metrics


def update_performance_record(existing: dict | None, updates: dict) -> dict:
    metrics = empty_performance_metrics()
    if existing:
        metrics.update(existing)
    for field in PERFORMANCE_METRIC_FIELDS + ("posted_at", "duration", "hook_style", "content_pillar", "comedic_mechanism"):
        if field in updates:
            metrics[field] = updates[field]
    metrics.update(calculate_performance_rates(metrics))
    metrics["updated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return metrics
