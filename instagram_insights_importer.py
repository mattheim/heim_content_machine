from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Iterable

import requests

from performance_feedback import PERFORMANCE_METRIC_FIELDS, update_performance_record


DEFAULT_CONTENT_DIR = Path(__file__).resolve().parent / "posted_content_data"
DEFAULT_GRAPH_URL = "https://graph.facebook.com/v23.0"
DEFAULT_MEDIA_FIELDS = (
    "id",
    "caption",
    "media_type",
    "media_product_type",
    "media_url",
    "permalink",
    "thumbnail_url",
    "timestamp",
    "username",
)
DEFAULT_INSIGHT_METRICS = (
    "views",
    "reach",
    "likes",
    "comments",
    "shares",
    "saved",
    "total_interactions",
)
METRIC_ALIASES = {
    "plays": "views",
    "saved": "saves",
    "saves": "saves",
}


class InstagramInsightsError(RuntimeError):
    pass


@dataclass(frozen=True)
class ImportResult:
    path: Path
    media_id: str | None
    status: str
    metrics: dict[str, Any]
    message: str = ""


@dataclass(frozen=True)
class MediaSyncResult:
    path: Path
    media_id: str
    status: str
    message: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_number(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _slug(text: Any, fallback: str = "instagram_post", max_len: int = 48) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", str(text or "")).strip("_")
    value = value[:max_len].strip("_")
    return value or fallback


def _metric_value(metric: dict[str, Any]) -> Any:
    if "values" in metric and metric["values"]:
        return metric["values"][-1].get("value")
    return metric.get("value")


def parse_insights_payload(payload: dict) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized: dict[str, Any] = {}
    raw: dict[str, Any] = {}

    for metric in payload.get("data", []):
        if not isinstance(metric, dict):
            continue
        name = metric.get("name")
        if not name:
            continue
        value = _metric_value(metric)
        raw[str(name)] = value
        field = METRIC_ALIASES.get(str(name), str(name))
        if field in PERFORMANCE_METRIC_FIELDS:
            normalized[field] = value

    return normalized, raw


def _graph_get_json(url: str, params: dict[str, Any], timeout: int) -> dict:
    try:
        response = requests.get(url, params=params, timeout=timeout)
    except requests.RequestException as exc:
        host = url.split("/", 3)[2] if "://" in url else url
        raise InstagramInsightsError(f"Request failed before Meta responded. Check DNS/network access for {host}.") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise InstagramInsightsError(f"Instagram returned non-JSON response with status {response.status_code}") from exc

    if response.status_code >= 400 or "error" in payload:
        error = payload.get("error") or {}
        message = error.get("message") or payload
        raise InstagramInsightsError(str(message))
    return payload


def fetch_media_insights(
    media_id: str,
    access_token: str,
    metrics: Iterable[str] = DEFAULT_INSIGHT_METRICS,
    graph_url: str = DEFAULT_GRAPH_URL,
    timeout: int = 30,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    metric_list = [metric for metric in metrics if metric]
    if not metric_list:
        return {}, {}, []

    url = f"{graph_url.rstrip('/')}/{media_id}/insights"
    params = {"metric": ",".join(metric_list), "access_token": access_token}

    try:
        payload = _graph_get_json(url, params=params, timeout=timeout)
        normalized, raw = parse_insights_payload(payload)
        return normalized, raw, []
    except InstagramInsightsError:
        normalized: dict[str, Any] = {}
        raw: dict[str, Any] = {}
        failed: list[str] = []
        for metric in metric_list:
            try:
                payload = _graph_get_json(url, {"metric": metric, "access_token": access_token}, timeout=timeout)
            except InstagramInsightsError as exc:
                failed.append(f"{metric}: {exc}")
                continue
            parsed, parsed_raw = parse_insights_payload(payload)
            normalized.update(parsed)
            raw.update(parsed_raw)
        return normalized, raw, failed


def fetch_instagram_media(
    ig_user_id: str,
    access_token: str,
    graph_url: str = DEFAULT_GRAPH_URL,
    fields: Iterable[str] = DEFAULT_MEDIA_FIELDS,
    limit: int | None = None,
    page_size: int = 50,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    if not ig_user_id:
        raise InstagramInsightsError("Missing IG user ID. Set IG_USER_ID or INSTAGRAM_BUSINESS_ACCOUNT_ID.")

    collected: list[dict[str, Any]] = []
    after: str | None = None
    url = f"{graph_url.rstrip('/')}/{ig_user_id}/media"

    while limit is None or len(collected) < limit:
        remaining = None if limit is None else limit - len(collected)
        request_limit = page_size if remaining is None else min(page_size, remaining)
        params: dict[str, Any] = {
            "fields": ",".join(field for field in fields if field),
            "limit": request_limit,
            "access_token": access_token,
        }
        if after:
            params["after"] = after

        payload = _graph_get_json(url, params=params, timeout=timeout)
        rows = payload.get("data") or []
        if not rows:
            break
        collected.extend(row for row in rows if isinstance(row, dict))

        after = ((payload.get("paging") or {}).get("cursors") or {}).get("after")
        if not after:
            break

    return collected


def content_files(content_dir: Path | str) -> list[Path]:
    return sorted(Path(content_dir).glob("*.json"))


def media_index(content_dir: Path | str) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in content_files(content_dir):
        try:
            payload = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        media_id = media_id_for_payload(payload)
        if media_id:
            index[media_id] = path
    return index


def media_id_for_payload(payload: dict) -> str | None:
    post_info = payload.get("instagram_post_info") or {}
    media_id = post_info.get("id") or post_info.get("media_id")
    return str(media_id) if media_id else None


def media_timestamp_for_filename(media: dict[str, Any]) -> str:
    timestamp = str(media.get("timestamp") or "")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return parsed.strftime("%Y%m%d_%H%M%S")
    except ValueError:
        return _utc_now().replace("-", "").replace(":", "").replace("T", "_").replace("Z", "")[:15]


def media_record_path(content_dir: Path | str, media: dict[str, Any]) -> Path:
    caption = str(media.get("caption") or media.get("permalink") or media.get("id") or "")
    filename = f"{media_timestamp_for_filename(media)}_{_slug(caption, fallback=str(media.get('id') or 'instagram_post'))}.json"
    return Path(content_dir) / filename


def first_caption_line(caption: Any) -> str | None:
    lines = [line.strip() for line in str(caption or "").splitlines() if line.strip()]
    return lines[0] if lines else None


def build_imported_media_payload(media: dict[str, Any]) -> dict[str, Any]:
    timestamp = media.get("timestamp")
    caption = media.get("caption")
    return {
        "source": "instagram_import",
        "generated_at": timestamp,
        "overlay_text": None,
        "caption_hook": first_caption_line(caption),
        "post_body": caption,
        "caption": caption,
        "instagram_post_info": dict(media),
        "performance": {
            "posted_at": timestamp,
            "updated_at": _utc_now(),
        },
        "instagram_synced_at": _utc_now(),
    }


def merge_instagram_media_payload(existing: dict, media: dict[str, Any]) -> dict:
    updated = dict(existing)
    post_info = dict(existing.get("instagram_post_info") or {})
    post_info.update(media)
    updated["instagram_post_info"] = post_info
    if not updated.get("caption") and media.get("caption"):
        updated["caption"] = media.get("caption")
    if not updated.get("caption_hook"):
        updated["caption_hook"] = first_caption_line(media.get("caption"))
    performance = dict(updated.get("performance") or {})
    performance.setdefault("posted_at", media.get("timestamp"))
    updated["performance"] = performance
    updated["instagram_synced_at"] = _utc_now()
    return updated


def sync_instagram_media_records(
    content_dir: Path | str = DEFAULT_CONTENT_DIR,
    ig_user_id: str | None = None,
    access_token: str | None = None,
    graph_url: str = DEFAULT_GRAPH_URL,
    limit: int | None = None,
    dry_run: bool = False,
    timeout: int = 30,
) -> list[MediaSyncResult]:
    if not access_token:
        raise InstagramInsightsError("Missing Instagram access token. Set ACCESS_TOKEN or IG_ACCESS_TOKEN.")
    if not ig_user_id:
        raise InstagramInsightsError("Missing IG user ID. Set IG_USER_ID or INSTAGRAM_BUSINESS_ACCOUNT_ID.")

    base = Path(content_dir)
    if not dry_run:
        base.mkdir(parents=True, exist_ok=True)

    existing = media_index(base)
    media_rows = fetch_instagram_media(
        ig_user_id=ig_user_id,
        access_token=access_token,
        graph_url=graph_url,
        limit=limit,
        timeout=timeout,
    )

    results: list[MediaSyncResult] = []
    for media in media_rows:
        media_id = str(media.get("id") or "")
        if not media_id:
            continue

        if media_id in existing:
            path = existing[media_id]
            if not dry_run:
                payload = _read_json(path)
                _write_json(path, merge_instagram_media_payload(payload, media))
            results.append(MediaSyncResult(path=path, media_id=media_id, status="updated" if not dry_run else "dry_run", message="existing record"))
            continue

        path = media_record_path(base, media)
        counter = 2
        while path.exists() or path in existing.values():
            path = path.with_name(f"{path.stem}_{counter}{path.suffix}")
            counter += 1
        if not dry_run:
            _write_json(path, build_imported_media_payload(media))
        results.append(MediaSyncResult(path=path, media_id=media_id, status="created" if not dry_run else "dry_run", message="new imported record"))

    return results


def has_performance_metrics(payload: dict) -> bool:
    performance = payload.get("performance") or {}
    return any(_safe_number(performance.get(field)) > 0 for field in PERFORMANCE_METRIC_FIELDS)


def build_performance_updates(payload: dict, insights: dict[str, Any]) -> dict[str, Any]:
    performance = payload.get("performance") or {}
    updates = dict(insights)
    updates.setdefault("duration", performance.get("duration") or payload.get("duration"))
    updates.setdefault("posted_at", performance.get("posted_at") or (payload.get("instagram_post_info") or {}).get("timestamp"))
    updates.setdefault("hook_style", payload.get("hook_style") or performance.get("hook_style"))
    updates.setdefault("content_pillar", payload.get("content_pillar") or performance.get("content_pillar"))
    updates.setdefault("comedic_mechanism", payload.get("comedic_mechanism") or performance.get("comedic_mechanism"))
    return updates


def update_payload_with_insights(payload: dict, insights: dict[str, Any], raw_insights: dict[str, Any]) -> dict:
    updated = dict(payload)
    updated["performance"] = update_performance_record(
        payload.get("performance"),
        build_performance_updates(payload, insights),
    )
    updated["instagram_insights"] = {
        "imported_at": _utc_now(),
        "raw_metrics": raw_insights,
    }
    return updated


def import_instagram_insights(
    content_dir: Path | str = DEFAULT_CONTENT_DIR,
    access_token: str | None = None,
    metrics: Iterable[str] = DEFAULT_INSIGHT_METRICS,
    graph_url: str = DEFAULT_GRAPH_URL,
    dry_run: bool = False,
    force: bool = False,
    limit: int | None = None,
    recent: bool = False,
    timeout: int = 30,
) -> list[ImportResult]:
    if not access_token:
        raise InstagramInsightsError("Missing Instagram access token. Set ACCESS_TOKEN or IG_ACCESS_TOKEN.")

    results: list[ImportResult] = []
    processed = 0

    files = content_files(content_dir)
    if recent:
        files = list(reversed(files))

    for path in files:
        if limit is not None and processed >= limit:
            break

        try:
            payload = _read_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            results.append(ImportResult(path=path, media_id=None, status="error", metrics={}, message=str(exc)))
            continue

        media_id = media_id_for_payload(payload)
        if not media_id:
            results.append(ImportResult(path=path, media_id=None, status="skipped", metrics={}, message="missing instagram_post_info.id"))
            continue
        if has_performance_metrics(payload) and not force:
            results.append(ImportResult(path=path, media_id=media_id, status="skipped", metrics={}, message="metrics already present"))
            continue

        processed += 1
        insights, raw_insights, failed = fetch_media_insights(
            media_id=media_id,
            access_token=access_token,
            metrics=metrics,
            graph_url=graph_url,
            timeout=timeout,
        )
        if not insights:
            message = "no supported insights returned"
            if failed:
                message += f"; failed metrics: {', '.join(failed)}"
            results.append(ImportResult(path=path, media_id=media_id, status="error", metrics={}, message=message))
            continue

        if not dry_run:
            updated = update_payload_with_insights(payload, insights, raw_insights)
            _write_json(path, updated)

        message = ""
        if failed:
            message = f"unsupported metrics skipped: {', '.join(failed)}"
        results.append(ImportResult(path=path, media_id=media_id, status="updated" if not dry_run else "dry_run", metrics=insights, message=message))

    return results


def _metric_arg(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def print_results(results: list[ImportResult]) -> None:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1

    print("Instagram insights import")
    print(", ".join(f"{status}={count}" for status, count in sorted(counts.items())) or "no records found")
    for result in results:
        if result.status not in {"updated", "dry_run", "error"}:
            continue
        metrics = ", ".join(f"{key}={value}" for key, value in sorted(result.metrics.items())) or "-"
        detail = f" ({result.message})" if result.message else ""
        print(f"{result.status}: {result.path.name} media_id={result.media_id} metrics={metrics}{detail}")


def print_media_sync_results(results: list[MediaSyncResult]) -> None:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1

    print("Instagram media sync")
    print(", ".join(f"{status}={count}" for status, count in sorted(counts.items())) or "no media found")
    for result in results[:10]:
        print(f"{result.status}: {result.path.name} media_id={result.media_id} ({result.message})")
    if len(results) > 10:
        print(f"... {len(results) - 10} more")


def main() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Import Instagram Graph API insights into saved post content data records.")
    parser.add_argument("--content-dir", default=str(DEFAULT_CONTENT_DIR), help="Directory containing posted content data JSON files.")
    parser.add_argument("--graph-url", default=os.getenv("GRAPH_URL", DEFAULT_GRAPH_URL), help="Instagram Graph API base URL.")
    parser.add_argument("--metrics", default=",".join(DEFAULT_INSIGHT_METRICS), help="Comma-separated insight metrics to request.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of eligible posts to fetch.")
    parser.add_argument("--recent", action="store_true", help="Start with the newest saved content records.")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print metrics without writing JSON files.")
    parser.add_argument("--force", action="store_true", help="Refresh posts that already have performance metrics.")
    parser.add_argument("--sync-media", action="store_true", help="First import/update media records from the Instagram account.")
    parser.add_argument("--only-sync-media", action="store_true", help="Only import/update media records, without fetching insights.")
    args = parser.parse_args()

    token = os.getenv("ACCESS_TOKEN") or os.getenv("IG_ACCESS_TOKEN")
    if args.sync_media or args.only_sync_media:
        sync_results = sync_instagram_media_records(
            content_dir=args.content_dir,
            ig_user_id=os.getenv("IG_USER_ID") or os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID"),
            access_token=token,
            graph_url=args.graph_url,
            limit=args.limit,
            dry_run=args.dry_run,
            timeout=args.timeout,
        )
        print_media_sync_results(sync_results)
        if args.only_sync_media:
            return

    results = import_instagram_insights(
        content_dir=args.content_dir,
        access_token=token,
        metrics=_metric_arg(args.metrics),
        graph_url=args.graph_url,
        dry_run=args.dry_run,
        force=args.force,
        limit=args.limit,
        recent=args.recent,
        timeout=args.timeout,
    )
    print_results(results)


if __name__ == "__main__":
    main()
