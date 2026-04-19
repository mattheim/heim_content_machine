import requests
import os
import threading
import http.server
import socketserver
import mimetypes
import time
import shutil
import re
from PIL import Image
from dotenv import load_dotenv; load_dotenv()
from pyngrok import conf, ngrok

# Configure ngrok path via environment if provided
_ngrok_path = os.getenv("NGROK_PATH") or os.getenv("ngrok_path")
if _ngrok_path:
    conf.get_default().ngrok_path = _ngrok_path

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

GRAPH_URL = "https://graph.facebook.com/v23.0"

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
    resp = requests.post(url, data=payload).json()
    if "id" not in resp:
        raise Exception(f"Error creating video media: {resp}")
    return resp["id"]

def check_media_status(container_id: str) -> dict:
    """Poll the status of a video upload container until it's finished."""
    url = f"{GRAPH_URL}/{container_id}"
    params = {
        "fields": "status_code",
        "access_token": ACCESS_TOKEN
    }
    while True:
        resp = requests.get(url, params=params).json()
        status = resp.get("status_code")
        print(f"Video processing status: {status}")
        if status == "FINISHED":
            return resp
        elif status in ("ERROR", "FAILED"):
            raise Exception(f"Video processing failed: {resp}")
        time.sleep(5)

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
    file_url = f"{public_url}/{filename}"
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
    file_url = f"{public_url}/{filename}"
    print(f"Public file accessible at: {file_url}")

    try:
        # Step 4: Verify HEAD request
        r = requests.head(file_url, timeout=30)
        print(
            "HEAD status:",
            r.status_code,
            "Content-Type:",
            r.headers.get("Content-Type"),
            "Content-Length:",
            r.headers.get("Content-Length"),
            "Accept-Ranges:",
            r.headers.get("Accept-Ranges"),
        )

        # Verify the server supports byte ranges, which many video fetchers rely on.
        range_response = requests.get(
            file_url,
            headers={"Range": "bytes=0-1023"},
            timeout=30,
        )
        print(
            "RANGE status:",
            range_response.status_code,
            "Content-Range:",
            range_response.headers.get("Content-Range"),
            "Returned bytes:",
            len(range_response.content),
        )

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
