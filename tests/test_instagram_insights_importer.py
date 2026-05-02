from __future__ import annotations

import json
from types import SimpleNamespace

import instagram_insights_importer as importer


def _write_record(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_parse_insights_payload_normalizes_instagram_metric_names():
    payload = {
        "data": [
            {"name": "plays", "values": [{"value": 125}]},
            {"name": "reach", "values": [{"value": 80}]},
            {"name": "saved", "values": [{"value": 7}]},
            {"name": "shares", "values": [{"value": 9}]},
        ]
    }

    normalized, raw = importer.parse_insights_payload(payload)

    assert normalized["views"] == 125
    assert normalized["reach"] == 80
    assert normalized["saves"] == 7
    assert normalized["shares"] == 9
    assert raw["plays"] == 125


def test_import_instagram_insights_updates_content_json(monkeypatch, tmp_path):
    record = tmp_path / "post.json"
    _write_record(
        record,
        {
            "duration": 12.0,
            "hook_style": "deadpan",
            "content_pillar": "oracle_office_humor",
            "comedic_mechanism": "status_drop",
            "instagram_post_info": {"id": "media-1"},
            "performance": {"duration": 12.0},
        },
    )

    def fake_get(url, params=None, timeout=None):
        assert url == "https://graph.example/media-1/insights"
        assert params["access_token"] == "token"
        assert params["metric"] == "plays,reach,shares,saved,total_interactions"
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "data": [
                    {"name": "plays", "values": [{"value": 100}]},
                    {"name": "reach", "values": [{"value": 50}]},
                    {"name": "shares", "values": [{"value": 5}]},
                    {"name": "saved", "values": [{"value": 3}]},
                    {"name": "total_interactions", "values": [{"value": 12}]},
                ]
            },
        )

    monkeypatch.setattr(importer.requests, "get", fake_get)

    results = importer.import_instagram_insights(
        content_dir=tmp_path,
        access_token="token",
        metrics=("plays", "reach", "shares", "saved", "total_interactions"),
        graph_url="https://graph.example",
    )
    updated = json.loads(record.read_text(encoding="utf-8"))

    assert results[0].status == "updated"
    assert updated["performance"]["views"] == 100
    assert updated["performance"]["reach"] == 50
    assert updated["performance"]["shares"] == 5
    assert updated["performance"]["saves"] == 3
    assert updated["performance"]["total_interactions"] == 12
    assert updated["performance"]["share_rate"] == 0.1
    assert updated["instagram_insights"]["raw_metrics"]["plays"] == 100


def test_import_instagram_insights_skips_existing_metrics_without_force(monkeypatch, tmp_path):
    record = tmp_path / "post.json"
    _write_record(
        record,
        {
            "instagram_post_info": {"id": "media-1"},
            "performance": {"views": 42},
        },
    )

    def fail_get(*_args, **_kwargs):
        raise AssertionError("request should not be made")

    monkeypatch.setattr(importer.requests, "get", fail_get)

    results = importer.import_instagram_insights(content_dir=tmp_path, access_token="token")

    assert results[0].status == "skipped"
    assert results[0].message == "metrics already present"


def test_import_instagram_insights_can_start_with_recent_files(monkeypatch, tmp_path):
    older = tmp_path / "20260501_120000_old.json"
    newer = tmp_path / "20260502_120000_new.json"
    _write_record(older, {"instagram_post_info": {"id": "old-media"}, "performance": {}})
    _write_record(newer, {"instagram_post_info": {"id": "new-media"}, "performance": {}})

    seen_media_ids = []

    def fake_fetch(media_id, **_kwargs):
        seen_media_ids.append(media_id)
        return {"views": 10}, {"views": 10}, []

    monkeypatch.setattr(importer, "fetch_media_insights", fake_fetch)

    results = importer.import_instagram_insights(
        content_dir=tmp_path,
        access_token="token",
        recent=True,
        limit=1,
        dry_run=True,
    )

    assert seen_media_ids == ["new-media"]
    assert results[0].path == newer
    assert results[0].status == "dry_run"


def test_fetch_instagram_media_paginates(monkeypatch):
    calls = []

    def fake_get(_url, params=None, timeout=None):
        calls.append(dict(params))
        if "after" not in params:
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [{"id": "media-1"}],
                    "paging": {"cursors": {"after": "cursor-1"}},
                },
            )
        return SimpleNamespace(status_code=200, json=lambda: {"data": [{"id": "media-2"}]})

    monkeypatch.setattr(importer.requests, "get", fake_get)

    media = importer.fetch_instagram_media(
        ig_user_id="ig-user",
        access_token="token",
        graph_url="https://graph.example",
        limit=2,
    )

    assert [row["id"] for row in media] == ["media-1", "media-2"]
    assert calls[0]["limit"] == 2
    assert calls[1]["after"] == "cursor-1"


def test_sync_instagram_media_records_creates_missing_records(monkeypatch, tmp_path):
    monkeypatch.setattr(
        importer,
        "fetch_instagram_media",
        lambda **_kwargs: [
            {
                "id": "media-1",
                "caption": "Olympus HR has opened another case.\nSend help.",
                "media_type": "VIDEO",
                "permalink": "https://instagram.example/p/1",
                "timestamp": "2026-05-02T12:00:00+0000",
            }
        ],
    )

    results = importer.sync_instagram_media_records(
        content_dir=tmp_path,
        ig_user_id="ig-user",
        access_token="token",
    )

    assert results[0].status == "created"
    payload = json.loads(results[0].path.read_text(encoding="utf-8"))
    assert payload["source"] == "instagram_import"
    assert payload["caption_hook"] == "Olympus HR has opened another case."
    assert payload["instagram_post_info"]["id"] == "media-1"


def test_sync_instagram_media_records_updates_existing_record(monkeypatch, tmp_path):
    record = tmp_path / "existing.json"
    _write_record(
        record,
        {
            "caption_hook": "Original hook",
            "instagram_post_info": {"id": "media-1"},
            "performance": {},
        },
    )
    monkeypatch.setattr(
        importer,
        "fetch_instagram_media",
        lambda **_kwargs: [
            {
                "id": "media-1",
                "caption": "Updated caption",
                "media_type": "VIDEO",
                "permalink": "https://instagram.example/p/1",
                "timestamp": "2026-05-02T12:00:00+0000",
            }
        ],
    )

    results = importer.sync_instagram_media_records(
        content_dir=tmp_path,
        ig_user_id="ig-user",
        access_token="token",
    )
    payload = json.loads(record.read_text(encoding="utf-8"))

    assert results[0].status == "updated"
    assert payload["caption_hook"] == "Original hook"
    assert payload["instagram_post_info"]["permalink"] == "https://instagram.example/p/1"


def test_fetch_media_insights_falls_back_to_individual_metrics(monkeypatch):
    calls = []

    def fake_get(_url, params=None, timeout=None):
        calls.append(params["metric"])
        if "," in params["metric"]:
            return SimpleNamespace(status_code=400, json=lambda: {"error": {"message": "metric not supported"}})
        if params["metric"] == "unsupported":
            return SimpleNamespace(status_code=400, json=lambda: {"error": {"message": "metric not supported"}})
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"data": [{"name": params["metric"], "values": [{"value": 10}]}]},
        )

    monkeypatch.setattr(importer.requests, "get", fake_get)

    metrics, raw, failed = importer.fetch_media_insights(
        media_id="media-1",
        access_token="token",
        metrics=("reach", "unsupported"),
        graph_url="https://graph.example",
    )

    assert calls == ["reach,unsupported", "reach", "unsupported"]
    assert metrics["reach"] == 10
    assert raw["reach"] == 10
    assert failed == ["unsupported: metric not supported"]
