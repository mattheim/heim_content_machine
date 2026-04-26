import requests
import os
import threading
import http.server
import socketserver
import mimetypes
import time
import shutil
import re
import tempfile
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from PIL import Image
from dotenv import load_dotenv; load_dotenv()
from pyngrok import conf, ngrok

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_NGROK_PATH = PROJECT_ROOT / "bin" / "ngrok"
DEFAULT_NGROK_CONFIG_PATH = PROJECT_ROOT / "ngrok.yml"
DEFAULT_TMP_DIR = PROJECT_ROOT / "tmp"

def _resolve_ngrok_path() -> str:
    configured = os.getenv("NGROK_PATH") or os.getenv("ngrok_path")
    candidate = Path(configured).expanduser() if configured else DEFAULT_NGROK_PATH
    parent = candidate.parent

    try:
        parent.mkdir(parents=True, exist_ok=True)
        return str(candidate)
    except PermissionError:
        DEFAULT_NGROK_PATH.parent.mkdir(parents=True, exist_ok=True)
        return str(DEFAULT_NGROK_PATH)


# Use a repo-local ngrok binary by default so the project stays self-contained.
DEFAULT_TMP_DIR.mkdir(parents=True, exist_ok=True)
os.environ["TMPDIR"] = str(DEFAULT_TMP_DIR)
tempfile.tempdir = str(DEFAULT_TMP_DIR)
_pyngrok_config = conf.get_default()
_pyngrok_config.ngrok_path = _resolve_ngrok_path()
_pyngrok_config.config_path = str(DEFAULT_NGROK_CONFIG_PATH)

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    range_request = None

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self):
        # Ensure proper caching headers for Instagram
        self.send_header("Cache-Control", "public, max-age=0")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def guess_type(self, path):
        # Force correct MIME type for common image formats
        mime_type, _ = mimetypes.guess_type(path)
        if mime_type:
            return mime_type
        return "application/octet-stream"

    def send_head(self):
        self.range_request = None
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()

        ctype = self.guess_type(path)
        try:
            file_obj = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        file_size = os.fstat(file_obj.fileno()).st_size
        range_header = self.headers.get("Range")
        if not range_header:
            self.send_response(200)
            self.send_header("Content-type", ctype)
            self.send_header("Content-Length", str(file_size))
            self.end_headers()
            return file_obj

        match = re.match(r"bytes=(\d*)-(\d*)$", range_header.strip())
        if not match:
            file_obj.close()
            self.send_error(400, "Invalid Range header")
            return None

        start_text, end_text = match.groups()
        if not start_text and not end_text:
            file_obj.close()
            self.send_error(400, "Invalid Range header")
            return None

        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else file_size - 1
        else:
            suffix_length = int(end_text)
            start = max(0, file_size - suffix_length)
            end = file_size - 1

        if start >= file_size or end < start:
            file_obj.close()
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{file_size}")
            self.end_headers()
            return None

        end = min(end, file_size - 1)
        content_length = end - start + 1
        file_obj.seek(start)
        self.range_request = (start, end)

        self.send_response(206)
        self.send_header("Content-type", ctype)
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Content-Length", str(content_length))
        self.end_headers()
        return file_obj

    def copyfile(self, source, outputfile):
        if self.range_request is None:
            super().copyfile(source, outputfile)
            return

        start, end = self.range_request
        remaining = end - start + 1
        while remaining > 0:
            chunk = source.read(min(64 * 1024, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)

def _make_handler(directory):
    class DirectoryHandler(CustomHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

    return DirectoryHandler

class ReusableThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

# === CONFIG ===
# Pull sensitive values from environment
IG_USER_ID = (os.getenv("IG_USER_ID") or os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID") or "").strip()
ACCESS_TOKEN = (os.getenv("ACCESS_TOKEN") or os.getenv("IG_ACCESS_TOKEN") or "").strip()
VIDEO_PUBLISH_DELAY_SECONDS = int(os.getenv("VIDEO_PUBLISH_DELAY_SECONDS", "15"))
VIDEO_PUBLISH_RETRIES = int(os.getenv("VIDEO_PUBLISH_RETRIES", "3"))
VIDEO_PUBLISH_RETRY_DELAY_SECONDS = int(os.getenv("VIDEO_PUBLISH_RETRY_DELAY_SECONDS", "10"))
PUBLIC_FILE_CHECK_RETRIES = int(os.getenv("PUBLIC_FILE_CHECK_RETRIES", "6"))
PUBLIC_FILE_CHECK_DELAY_SECONDS = int(os.getenv("PUBLIC_FILE_CHECK_DELAY_SECONDS", "5"))
VIDEO_STATUS_TIMEOUT_SECONDS = int(os.getenv("VIDEO_STATUS_TIMEOUT_SECONDS", "900"))
VIDEO_STATUS_POLL_SECONDS = int(os.getenv("VIDEO_STATUS_POLL_SECONDS", "10"))
VIDEO_UPLOAD_RETRIES = int(os.getenv("VIDEO_UPLOAD_RETRIES", "3"))
VIDEO_UPLOAD_RETRY_BASE_SECONDS = int(os.getenv("VIDEO_UPLOAD_RETRY_BASE_SECONDS", "30"))
VIDEO_UPLOAD_METHOD = os.getenv("VIDEO_UPLOAD_METHOD", "resumable").strip().lower()
VIDEO_UPLOAD_FALLBACK_TO_NGROK = os.getenv("VIDEO_UPLOAD_FALLBACK_TO_NGROK", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}

GRAPH_URL = "https://graph.facebook.com/v23.0"


@dataclass
class VideoProbe:
    path: str
    width: int
    height: int
    duration: float
    video_codec: str
    audio_codec: str
    pixel_format: str
    frame_rate: float
    file_size: int
    bit_rate: int


class InstagramUploadError(RuntimeError):
    """Raised when Meta rejects or cannot process a video upload."""

    def __init__(self, message: str, response: dict | None = None):
        super().__init__(message)
        self.response = response or {}


def _parse_fraction(value: str) -> float:
    if not value or value == "0/0":
        return 0.0
    if "/" not in value:
        return float(value)
    numerator, denominator = value.split("/", 1)
    denominator_value = float(denominator)
    if denominator_value == 0:
        return 0.0
    return float(numerator) / denominator_value


def probe_video(file_path: str) -> VideoProbe:
    """Return normalized ffprobe metadata for the rendered Reel."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"No file found at: {file_path}")

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is required to validate videos before Instagram upload.")

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        file_path,
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)

    if not video_stream:
        raise RuntimeError(f"Video has no video stream: {file_path}")
    if not audio_stream:
        raise RuntimeError(f"Video has no audio stream: {file_path}")

    format_info = data.get("format", {})
    return VideoProbe(
        path=file_path,
        width=int(video_stream.get("width") or 0),
        height=int(video_stream.get("height") or 0),
        duration=float(format_info.get("duration") or video_stream.get("duration") or 0),
        video_codec=(video_stream.get("codec_name") or "").lower(),
        audio_codec=(audio_stream.get("codec_name") or "").lower(),
        pixel_format=(video_stream.get("pix_fmt") or "").lower(),
        frame_rate=_parse_fraction(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or "0/0"),
        file_size=int(format_info.get("size") or os.path.getsize(file_path)),
        bit_rate=int(format_info.get("bit_rate") or 0),
    )


def validate_instagram_reel(file_path: str) -> VideoProbe:
    """Fail fast on common Meta rejection causes before creating an upload container."""
    probe = probe_video(file_path)
    errors = []

    if probe.video_codec != "h264":
        errors.append(f"video codec must be h264, got {probe.video_codec or 'unknown'}")
    if probe.audio_codec != "aac":
        errors.append(f"audio codec must be aac, got {probe.audio_codec or 'unknown'}")
    if probe.pixel_format != "yuv420p":
        errors.append(f"pixel format must be yuv420p, got {probe.pixel_format or 'unknown'}")
    if probe.width < 540 or probe.height < 960:
        errors.append(f"resolution is too small for Reels: {probe.width}x{probe.height}")
    if abs((probe.width / probe.height) - (9 / 16)) > 0.02:
        errors.append(f"aspect ratio must be near 9:16, got {probe.width}x{probe.height}")
    if not 3 <= probe.duration <= 900:
        errors.append(f"duration must be between 3 and 900 seconds, got {probe.duration:.2f}")
    if probe.frame_rate <= 0 or probe.frame_rate > 60:
        errors.append(f"frame rate must be >0 and <=60, got {probe.frame_rate:.2f}")
    if probe.bit_rate > 25_000_000:
        errors.append(f"bit rate is above 25 Mbps, got {probe.bit_rate}")

    if errors:
        raise RuntimeError("Instagram Reel validation failed: " + "; ".join(errors))

    print(
        "Validated Reel:",
        f"{probe.width}x{probe.height}",
        f"{probe.duration:.2f}s",
        probe.video_codec,
        probe.audio_codec,
        probe.pixel_format,
        f"{probe.frame_rate:.2f}fps",
        f"{probe.file_size} bytes",
    )
    return probe


def _raise_for_graph_error(resp: dict, action: str) -> None:
    if "error" in resp:
        raise InstagramUploadError(f"{action} failed: {resp}", resp)


def _graph_post(path_or_url: str, payload: dict | None = None, *, files=None, headers=None) -> dict:
    url = path_or_url if path_or_url.startswith("http") else f"{GRAPH_URL}/{path_or_url.lstrip('/')}"
    response = requests.post(url, data=payload, files=files, headers=headers, timeout=300)
    try:
        resp = response.json()
    except ValueError as exc:
        raise InstagramUploadError(f"Graph API returned non-JSON response for POST {url}: {response.text[:500]}") from exc
    if response.status_code >= 400:
        raise InstagramUploadError(f"Graph API POST {url} returned HTTP {response.status_code}: {resp}", resp)
    return resp


def _graph_get(path_or_url: str, params: dict | None = None) -> dict:
    url = path_or_url if path_or_url.startswith("http") else f"{GRAPH_URL}/{path_or_url.lstrip('/')}"
    response = requests.get(url, params=params, timeout=120)
    try:
        resp = response.json()
    except ValueError as exc:
        raise InstagramUploadError(f"Graph API returned non-JSON response for GET {url}: {response.text[:500]}") from exc
    if response.status_code >= 400:
        raise InstagramUploadError(f"Graph API GET {url} returned HTTP {response.status_code}: {resp}", resp)
    return resp

def _public_file_url(public_url: str, filename: str) -> str:
    return f"{public_url.rstrip('/')}/{quote(filename)}"

def _verify_public_video_url(file_url: str) -> None:
    """Wait until the public URL serves the MP4 and supports byte-range reads."""
    last_error = None

    for attempt in range(1, PUBLIC_FILE_CHECK_RETRIES + 1):
        try:
            head_response = requests.head(file_url, timeout=30, allow_redirects=True)
            content_type = (head_response.headers.get("Content-Type") or "").lower()
            print(
                "HEAD status:",
                head_response.status_code,
                "Content-Type:",
                head_response.headers.get("Content-Type"),
                "Content-Length:",
                head_response.headers.get("Content-Length"),
                "Accept-Ranges:",
                head_response.headers.get("Accept-Ranges"),
            )

            range_response = requests.get(
                file_url,
                headers={"Range": "bytes=0-1023"},
                timeout=30,
                allow_redirects=True,
            )
            print(
                "RANGE status:",
                range_response.status_code,
                "Content-Range:",
                range_response.headers.get("Content-Range"),
                "Returned bytes:",
                len(range_response.content),
            )

            head_ok = head_response.status_code == 200 and "video/mp4" in content_type
            range_ok = range_response.status_code == 206 and len(range_response.content) > 0
            if head_ok and range_ok:
                return

            last_error = (
                f"HEAD {head_response.status_code} {head_response.headers.get('Content-Type')}; "
                f"RANGE {range_response.status_code} {range_response.headers.get('Content-Range')}"
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            print(f"Public video URL check attempt {attempt} failed: {exc}")

        if attempt < PUBLIC_FILE_CHECK_RETRIES and PUBLIC_FILE_CHECK_DELAY_SECONDS > 0:
            print(
                f"Waiting {PUBLIC_FILE_CHECK_DELAY_SECONDS}s for public video URL "
                f"(attempt {attempt}/{PUBLIC_FILE_CHECK_RETRIES})..."
            )
            time.sleep(PUBLIC_FILE_CHECK_DELAY_SECONDS)

    raise RuntimeError(f"Public video URL is not ready for Instagram: {file_url} ({last_error})")

def create_media(image_url: str, caption: str) -> str:
    """Upload image to Instagram (create media container)."""
    url = f"{GRAPH_URL}/{IG_USER_ID}/media"
    payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN
    }
    resp = requests.post(url, data=payload).json()
    if "id" not in resp:
        raise Exception(f"Error creating media: {resp}")
    return resp["id"]

def publish_media(media_id: str) -> str:
    """Publish media container to Instagram."""
    url = f"{GRAPH_URL}/{IG_USER_ID}/media_publish"
    payload = {
        "creation_id": media_id,
        "access_token": ACCESS_TOKEN
    }
    resp = requests.post(url, data=payload).json()
    if "id" not in resp:
        raise Exception(f"Error publishing media: {resp}")
    return resp["id"]

def publish_media_with_retry(media_id: str) -> str:
    """Publish media container with a short settle delay and retries for transient Meta failures."""
    last_error = None

    for attempt in range(1, VIDEO_PUBLISH_RETRIES + 1):
        if attempt == 1 and VIDEO_PUBLISH_DELAY_SECONDS > 0:
            print(f"Waiting {VIDEO_PUBLISH_DELAY_SECONDS}s before publishing video...")
            time.sleep(VIDEO_PUBLISH_DELAY_SECONDS)
        elif attempt > 1 and VIDEO_PUBLISH_RETRY_DELAY_SECONDS > 0:
            print(
                f"Retrying video publish in {VIDEO_PUBLISH_RETRY_DELAY_SECONDS}s "
                f"(attempt {attempt}/{VIDEO_PUBLISH_RETRIES})..."
            )
            time.sleep(VIDEO_PUBLISH_RETRY_DELAY_SECONDS)

        try:
            return publish_media(media_id)
        except Exception as exc:
            last_error = exc
            print(f"Video publish attempt {attempt} failed: {exc}")

    raise last_error

def create_video_media(video_url: str, caption: str) -> str:
    """Upload video to Instagram (create media container)."""
    url = f"{GRAPH_URL}/{IG_USER_ID}/media"
    payload = {
        "media_type": "REELS",   # instead of "VIDEO"
        "video_url": video_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN
    }
    resp = _graph_post(url, payload)
    if "id" not in resp:
        raise Exception(f"Error creating video media: {resp}")
    return resp["id"]

def create_resumable_video_media(caption: str) -> tuple[str, str]:
    """Create a Reel container that accepts direct binary upload to Meta."""
    url = f"{GRAPH_URL}/{IG_USER_ID}/media"
    payload = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "access_token": ACCESS_TOKEN,
    }
    resp = _graph_post(url, payload)
    _raise_for_graph_error(resp, "Creating resumable video media")
    container_id = resp.get("id")
    upload_uri = resp.get("uri")
    if not container_id or not upload_uri:
        raise InstagramUploadError(f"Resumable upload did not return id and uri: {resp}", resp)
    return container_id, upload_uri

def upload_video_bytes(upload_uri: str, file_path: str) -> dict:
    """Upload MP4 bytes directly to Meta's resumable upload endpoint."""
    file_size = os.path.getsize(file_path)
    headers = {
        "Authorization": f"OAuth {ACCESS_TOKEN}",
        "Content-Type": "video/mp4",
        "file_size": str(file_size),
        "offset": "0",
    }
    with open(file_path, "rb") as file_obj:
        response = requests.post(upload_uri, headers=headers, data=file_obj, timeout=600)

    try:
        resp = response.json()
    except ValueError as exc:
        raise InstagramUploadError(
            f"Meta upload endpoint returned non-JSON response: HTTP {response.status_code} {response.text[:500]}"
        ) from exc
    if response.status_code >= 400:
        raise InstagramUploadError(f"Meta upload endpoint returned HTTP {response.status_code}: {resp}", resp)
    _raise_for_graph_error(resp, "Uploading video bytes")
    return resp

def create_video_media_from_file(file_path: str, caption: str) -> str:
    """Create a Reel container via direct resumable upload."""
    validate_instagram_reel(file_path)
    media_id, upload_uri = create_resumable_video_media(caption)
    print(f"Resumable video media container created: {media_id}")
    upload_resp = upload_video_bytes(upload_uri, file_path)
    print(f"Video bytes uploaded to Meta: {upload_resp}")
    return media_id

def check_media_status(container_id: str) -> dict:
    """Poll the status of a video upload container until it's finished."""
    url = f"{GRAPH_URL}/{container_id}"
    params = {
        "fields": "id,status,status_code",
        "access_token": ACCESS_TOKEN
    }
    started = time.monotonic()
    while True:
        resp = _graph_get(url, params=params)
        status = resp.get("status_code")
        print(f"Video processing status: {status} | detail: {resp.get('status')}")
        if status == "FINISHED":
            return resp
        elif status in ("ERROR", "FAILED"):
            raise InstagramUploadError(f"Video processing failed: {resp}", resp)
        if time.monotonic() - started > VIDEO_STATUS_TIMEOUT_SECONDS:
            raise InstagramUploadError(
                f"Timed out after {VIDEO_STATUS_TIMEOUT_SECONDS}s waiting for video processing: {resp}",
                resp,
            )
        time.sleep(VIDEO_STATUS_POLL_SECONDS)

def get_post_info(media_id: str) -> dict:
    """Fetch permalink + details of a published post."""
    url = f"{GRAPH_URL}/{media_id}"
    params = {
        "fields": "id,media_type,media_url,caption,permalink",
        "access_token": ACCESS_TOKEN
    }
    resp = requests.get(url, params=params).json()
    return resp

def post_to_instagram(image_url: str, caption: str):
    """Full workflow: create, publish, verify."""
    print(f"Uploading {image_url} with caption: {caption}")
    media_id = create_media(image_url, caption)
    print(f"Media container created: {media_id}")

    publish_id = publish_media(media_id)
    print(f"Published successfully, IG Media ID: {publish_id}")

    info = get_post_info(publish_id)
    print(f"Post URL: {info.get('permalink')}")
    return info, {"status": "success", "image_url": image_url, "caption": caption}

def post_local_image_via_ngrok(file_path, caption):
    """
    Serves a local file temporarily via HTTPS (ngrok), posts to Instagram, and shuts down.
    
    Args:
        file_path (str): Path to the local image file.
        caption (str): Instagram caption.
    """
    # Validate file
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"No file found at: {file_path}")

    # Extract directory and file name
    directory, filename = os.path.split(file_path)

    # Step 1: Start local HTTP server
    handler_cls = _make_handler(directory)
    httpd = ReusableThreadingTCPServer(("", 0), handler_cls)  # auto-pick free port
    port = httpd.server_address[1]

    def start_server():
        httpd.serve_forever()

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    print(f"Local server started at http://localhost:{port}")

    # Step 2: Expose with ngrok
    public_url = ngrok.connect(port, "http").public_url
    print(f"Public ngrok URL: {public_url}")

    # Step 3: Create public file URL
    file_url = _public_file_url(public_url, filename)
    print(f"Public file accessible at: {file_url}")

    try:
        # Step 4: Verify Instagram can fetch it
        r = requests.head(file_url)
        print("HEAD status:", r.status_code, "Content-Type:", r.headers.get("Content-Type"),
              "Content-Length:", r.headers.get("Content-Length"))

        # Step 5: Post to Instagram
        post_info = post_to_instagram(file_url, caption)

        time.sleep(5)
        print("Post result:", post_info)

    finally:
        # Step 6: Shutdown server & ngrok
        httpd.shutdown()
        httpd.server_close()
        ngrok.disconnect(public_url)
        ngrok.kill()
        print("Server and ngrok tunnel closed.")

def post_local_video_via_ngrok(file_path, caption):
    """
    Serves a local .mp4 via HTTPS (ngrok), posts to Instagram, waits for processing, and shuts down.
    """
    # Validate file
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"No file found at: {file_path}")

    # Extract directory + filename
    directory, filename = os.path.split(file_path)

    # Step 1: Start local HTTP server
    handler_cls = _make_handler(directory)
    httpd = ReusableThreadingTCPServer(("", 0), handler_cls)  # auto-pick free port
    port = httpd.server_address[1]

    def start_server():
        httpd.serve_forever()

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    print(f"Local server started at http://localhost:{port}")

    # Step 2: Expose with ngrok
    public_url = ngrok.connect(port, "http").public_url
    print(f"Public ngrok URL: {public_url}")

    # Step 3: Create public file URL
    file_url = _public_file_url(public_url, filename)
    print(f"Public file accessible at: {file_url}")

    try:
        # Step 4: Verify the public URL before handing it to Meta.
        _verify_public_video_url(file_url)

        # Step 5: Create video media container
        media_id = create_video_media(file_url, caption)
        print(f"Video media container created: {media_id}")

        # Step 6: Poll status until video is processed
        status_info = check_media_status(media_id)
        print(f"Video processing complete: {status_info}")

        # Step 7: Publish video
        publish_id = publish_media_with_retry(media_id)
        print(f"Published successfully, IG Media ID: {publish_id}")

        info = get_post_info(publish_id)
        print(f"Post URL: {info.get('permalink')}")
        return info

    finally:
        # Step 8: Clean up
        httpd.shutdown()
        httpd.server_close()
        ngrok.disconnect(public_url)
        ngrok.kill()
        print("Server and ngrok tunnel closed.")

def post_local_video_resumable(file_path: str, caption: str):
    """Post a local MP4 using Meta's direct resumable upload flow."""
    media_id = create_video_media_from_file(file_path, caption)
    status_info = check_media_status(media_id)
    print(f"Video processing complete: {status_info}")

    publish_id = publish_media_with_retry(media_id)
    print(f"Published successfully, IG Media ID: {publish_id}")

    info = get_post_info(publish_id)
    print(f"Post URL: {info.get('permalink')}")
    return info

def _is_transient_upload_error(exc: Exception) -> bool:
    text = str(exc).lower()
    transient_markers = (
        "timeout",
        "timed out",
        "temporarily",
        "try again",
        "rate limit",
        "too many calls",
        "http 500",
        "http 502",
        "http 503",
        "http 504",
        "2207076",
        "2207077",
    )
    return any(marker in text for marker in transient_markers)

def post_local_video(file_path: str, caption: str):
    """
    Post a local MP4 with a durable primary upload path and an ngrok fallback.

    VIDEO_UPLOAD_METHOD:
      - resumable: direct Meta upload, preferred for cron reliability
      - ngrok: legacy public-URL ingest
    """
    last_error = None
    methods = [VIDEO_UPLOAD_METHOD]
    if VIDEO_UPLOAD_METHOD != "ngrok" and VIDEO_UPLOAD_FALLBACK_TO_NGROK:
        methods.append("ngrok")

    for method in methods:
        attempts = VIDEO_UPLOAD_RETRIES if method == "resumable" else 1
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                delay = VIDEO_UPLOAD_RETRY_BASE_SECONDS * (2 ** (attempt - 2))
                print(f"Retrying {method} video upload in {delay}s (attempt {attempt}/{attempts})...")
                time.sleep(delay)

            try:
                if method == "ngrok":
                    return post_local_video_via_ngrok(file_path, caption)
                if method == "resumable":
                    return post_local_video_resumable(file_path, caption)
                raise ValueError(f"Unsupported VIDEO_UPLOAD_METHOD={method!r}")
            except Exception as exc:
                last_error = exc
                print(f"{method} video upload attempt {attempt} failed: {exc}")
                if method == "resumable" and not _is_transient_upload_error(exc):
                    break

    raise last_error

# === Example usage ===
if __name__ == "__main__":
    print("running main")
    #test_image = "images/hades_at_the_function.png" 
    #test_caption = "here we gooo"
    #test_video = "videos/20251111_193203_Hephaestus_rage_activated__no.mp4"

    #post_local_image_via_ngrok(test_image, test_caption)
    #post_local_video_via_ngrok(test_video, test_caption)

    #post_info = post_to_instagram(test_image, test_caption)
    #print(post_info)
