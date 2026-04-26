from __future__ import annotations

from types import SimpleNamespace

import insta_post


def test_create_video_media_from_file_uses_resumable_upload(monkeypatch, tmp_path):
    video_path = tmp_path / "reel.mp4"
    video_path.write_bytes(b"fake mp4 bytes")

    monkeypatch.setattr(insta_post, "ACCESS_TOKEN", "token")
    monkeypatch.setattr(insta_post, "IG_USER_ID", "ig-user")
    monkeypatch.setattr(
        insta_post,
        "validate_instagram_reel",
        lambda path: insta_post.VideoProbe(
            path=path,
            width=1080,
            height=1920,
            duration=20.0,
            video_codec="h264",
            audio_codec="aac",
            pixel_format="yuv420p",
            frame_rate=30.0,
            file_size=video_path.stat().st_size,
            bit_rate=700_000,
        ),
    )

    post_calls = []

    def fake_post(url, data=None, headers=None, timeout=None, **kwargs):
        post_calls.append(
            {
                "url": url,
                "data": data,
                "headers": headers,
                "timeout": timeout,
                "body": kwargs.get("data"),
            }
        )
        if url.endswith("/ig-user/media"):
            return SimpleNamespace(status_code=200, json=lambda: {"id": "container-id", "uri": "https://upload.example"})
        if url == "https://upload.example":
            assert headers["Authorization"] == "OAuth token"
            assert headers["Content-Type"] == "video/mp4"
            assert headers["file_size"] == str(video_path.stat().st_size)
            assert headers["offset"] == "0"
            return SimpleNamespace(status_code=200, json=lambda: {"success": True})
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(insta_post.requests, "post", fake_post)

    media_id = insta_post.create_video_media_from_file(str(video_path), "caption")

    assert media_id == "container-id"
    assert post_calls[0]["data"]["upload_type"] == "resumable"
    assert post_calls[0]["data"]["media_type"] == "REELS"
    assert post_calls[1]["url"] == "https://upload.example"


def test_check_media_status_times_out(monkeypatch):
    now = {"value": 0}

    def fake_monotonic():
        now["value"] += 11
        return now["value"]

    monkeypatch.setattr(insta_post.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(insta_post.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(insta_post, "VIDEO_STATUS_TIMEOUT_SECONDS", 20)
    monkeypatch.setattr(insta_post, "VIDEO_STATUS_POLL_SECONDS", 1)
    monkeypatch.setattr(insta_post, "ACCESS_TOKEN", "token")
    monkeypatch.setattr(
        insta_post,
        "_graph_get",
        lambda _url, params=None: {"id": "container-id", "status_code": "IN_PROGRESS", "status": "still processing"},
    )

    try:
        insta_post.check_media_status("container-id")
    except insta_post.InstagramUploadError as exc:
        assert "Timed out" in str(exc)
    else:
        raise AssertionError("expected timeout")


def test_post_local_video_falls_back_to_ngrok_after_resumable_failure(monkeypatch, tmp_path):
    video_path = tmp_path / "reel.mp4"
    video_path.write_bytes(b"fake mp4 bytes")

    monkeypatch.setattr(insta_post, "VIDEO_UPLOAD_METHOD", "resumable")
    monkeypatch.setattr(insta_post, "VIDEO_UPLOAD_FALLBACK_TO_NGROK", True)
    monkeypatch.setattr(insta_post, "VIDEO_UPLOAD_RETRIES", 1)
    monkeypatch.setattr(insta_post, "post_local_video_resumable", lambda *_args: (_ for _ in ()).throw(RuntimeError("2207076")))
    monkeypatch.setattr(insta_post, "post_local_video_via_ngrok", lambda *_args: {"permalink": "https://instagram.example/p/1"})

    assert insta_post.post_local_video(str(video_path), "caption") == {"permalink": "https://instagram.example/p/1"}
