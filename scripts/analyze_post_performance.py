from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from performance_report import DEFAULT_CONTENT_DIR, load_content_records  # noqa: E402


def _safe_number(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_number(value: Any) -> str:
    number = _safe_number(value)
    if number == int(number):
        return str(int(number))
    return f"{number:.2f}"


def _truncate(value: Any, max_len: int = 48) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def measured_records(records: list[dict]) -> list[dict]:
    return [
        record
        for record in records
        if _safe_number((record.get("performance") or {}).get("views")) > 0
        or _safe_number((record.get("performance") or {}).get("reach")) > 0
    ]


def calculate_view_reach_stats(records: list[dict]) -> dict:
    measured = measured_records(records)
    views = [_safe_number((record.get("performance") or {}).get("views")) for record in measured]
    reach = [_safe_number((record.get("performance") or {}).get("reach")) for record in measured]

    if not measured:
        return {
            "total_posts": len(records),
            "measured_posts": 0,
            "missing_posts": len(records),
            "avg_views": 0.0,
            "median_views": 0.0,
            "avg_reach": 0.0,
            "median_reach": 0.0,
            "max_views": 0.0,
            "max_reach": 0.0,
        }

    return {
        "total_posts": len(records),
        "measured_posts": len(measured),
        "missing_posts": len(records) - len(measured),
        "avg_views": statistics.fmean(views),
        "median_views": statistics.median(views),
        "avg_reach": statistics.fmean(reach),
        "median_reach": statistics.median(reach),
        "max_views": max(views),
        "max_reach": max(reach),
    }


def underperforming_records(records: list[dict], view_threshold: float, reach_threshold: float) -> list[dict]:
    underperformers = []
    for record in measured_records(records):
        performance = record.get("performance") or {}
        views = _safe_number(performance.get("views"))
        reach = _safe_number(performance.get("reach"))
        if views < view_threshold or reach < reach_threshold:
            underperformers.append(
                {
                    **record,
                    "views": views,
                    "reach": reach,
                    "views_delta": views - view_threshold,
                    "reach_delta": reach - reach_threshold,
                }
            )

    return sorted(underperformers, key=lambda record: (record["views"], record["reach"]))


def top_performing_records(records: list[dict]) -> list[dict]:
    performers = []
    for record in measured_records(records):
        performance = record.get("performance") or {}
        views = _safe_number(performance.get("views"))
        reach = _safe_number(performance.get("reach"))
        shares = _safe_number(performance.get("shares"))
        saves = _safe_number(performance.get("saves"))
        likes = _safe_number(performance.get("likes"))
        comments = _safe_number(performance.get("comments"))
        share_rate = shares / reach if reach > 0 else 0.0
        save_rate = saves / reach if reach > 0 else 0.0
        engagement_score = _safe_number(performance.get("engagement_score"))
        if engagement_score == 0.0 and reach > 0:
            engagement_score = share_rate * 5.0 + save_rate * 3.0 + (comments / reach) * 2.0 + (likes / reach)
        performers.append(
            {
                **record,
                "views": views,
                "reach": reach,
                "shares": shares,
                "saves": saves,
                "likes": likes,
                "comments": comments,
                "share_rate": share_rate,
                "save_rate": save_rate,
                "engagement_score": engagement_score,
            }
        )

    return sorted(
        performers,
        key=lambda record: (
            record["views"],
            record["reach"],
            record["shares"],
            record["saves"],
            record["engagement_score"],
        ),
        reverse=True,
    )


def content_signal(record: dict) -> str:
    parts = [
        record.get("caption_archetype"),
        record.get("hook_style"),
        record.get("content_pillar"),
        record.get("comedic_mechanism"),
    ]
    return ", ".join(str(part) for part in parts if part) or "-"


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    if not rows:
        print("No rows to show.")
        return

    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))


def print_average_report(records: list[dict], underperformer_limit: int, top_limit: int, threshold_multiplier: float) -> None:
    stats = calculate_view_reach_stats(records)
    view_threshold = stats["avg_views"] * threshold_multiplier
    reach_threshold = stats["avg_reach"] * threshold_multiplier
    underperformers = underperforming_records(records, view_threshold, reach_threshold)

    print("Average views/reach report")
    print(
        "Posts: "
        f"{stats['total_posts']} total, "
        f"{stats['measured_posts']} with metrics, "
        f"{stats['missing_posts']} missing metrics"
    )
    print(
        "Views: "
        f"avg={_format_number(stats['avg_views'])}, "
        f"median={_format_number(stats['median_views'])}, "
        f"max={_format_number(stats['max_views'])}"
    )
    print(
        "Reach: "
        f"avg={_format_number(stats['avg_reach'])}, "
        f"median={_format_number(stats['median_reach'])}, "
        f"max={_format_number(stats['max_reach'])}"
    )
    print(
        "Underperforming threshold: "
        f"views<{_format_number(view_threshold)} or reach<{_format_number(reach_threshold)} "
        f"({threshold_multiplier:.2f}x average)"
    )
    print(f"Underperformers: {len(underperformers)}")

    top_posts = top_performing_records(records)
    top_rows = []
    for record in top_posts[:top_limit]:
        top_rows.append(
            [
                str(record.get("generated_at") or "-"),
                _format_number(record["views"]),
                _format_number(record["reach"]),
                _format_number(record["shares"]),
                _format_number(record["saves"]),
                f"{record['share_rate'] * 100:.2f}%",
                _format_number(record["engagement_score"]),
                _truncate(record.get("caption_hook") or record.get("overlay_text") or record.get("filename")),
                content_signal(record),
                str(record.get("filename") or "-"),
            ]
        )

    print("\nTop performers")
    print_table(
        ["generated", "views", "reach", "shares", "saves", "share_rate", "score", "caption/overlay", "signals", "file"],
        top_rows,
    )

    rows = []
    for record in underperformers[:underperformer_limit]:
        rows.append(
            [
                str(record.get("generated_at") or "-"),
                _format_number(record["views"]),
                _format_number(record["reach"]),
                _format_number(record["views_delta"]),
                _format_number(record["reach_delta"]),
                _truncate(record.get("caption_hook") or record.get("overlay_text") or record.get("filename")),
                str(record.get("filename") or "-"),
            ]
        )

    print("\nLowest performers")
    print_table(["generated", "views", "reach", "view_delta", "reach_delta", "caption/overlay", "file"], rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate average views/reach from posted content data.")
    parser.add_argument("--content-dir", default=str(DEFAULT_CONTENT_DIR), help="Directory containing posted content data JSON files.")
    parser.add_argument("--limit", type=int, default=15, help="Number of underperforming posts to print.")
    parser.add_argument("--top-limit", type=int, default=10, help="Number of top-performing posts to print.")
    parser.add_argument(
        "--threshold-multiplier",
        type=float,
        default=1.0,
        help="Flag posts below this multiple of average views or reach. Use 0.75 for a looser cutoff.",
    )
    args = parser.parse_args()

    records = load_content_records(args.content_dir)
    if not records:
        print(f"No posted content data found in {args.content_dir}")
        return

    print_average_report(
        records,
        underperformer_limit=max(1, args.limit),
        top_limit=max(1, args.top_limit),
        threshold_multiplier=max(0.0, args.threshold_multiplier),
    )


if __name__ == "__main__":
    main()
