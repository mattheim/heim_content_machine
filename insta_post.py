import requests
import os
import threading
import http.server
import socketserver
import mimetypes
import time
from PIL import Image
from dotenv import load_dotenv; load_dotenv()
from pyngrok import conf, ngrok

# Configure ngrok path via environment if provided
_ngrok_path = os.getenv("NGROK_PATH") or os.getenv("ngrok_path")
if _ngrok_path:
    conf.get_default().ngrok_path = _ngrok_path

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Ensure proper caching headers for Instagram
        self.send_header("Cache-Control", "public, max-age=0")
        super().end_headers()

    def guess_type(self, path):
        # Force correct MIME type for common image formats
        mime_type, _ = mimetypes.guess_type(path)
        if mime_type:
            return mime_type
        return "application/octet-stream"

# === CONFIG ===
# Pull sensitive values from environment
IG_USER_ID = (os.getenv("IG_USER_ID") or os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID") or "").strip()
ACCESS_TOKEN = (os.getenv("ACCESS_TOKEN") or os.getenv("IG_ACCESS_TOKEN") or "").strip()

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
    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    class CustomHandler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            # Ensure cache headers so Instagram can fetch reliably
            self.send_header("Cache-Control", "public, max-age=0")
            super().end_headers()

        def guess_type(self, path):
            # Force correct MIME type for images
            mime_type, _ = mimetypes.guess_type(path)
            if mime_type:
                return mime_type
            return "application/octet-stream"

    # Validate file
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"No file found at: {file_path}")

    # Extract directory and file name
    directory, filename = os.path.split(file_path)

    # Step 1: Start local HTTP server
    os.chdir(directory)
    httpd = ReusableTCPServer(("", 0), CustomHandler)  # auto-pick free port
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
    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    # Validate file
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"No file found at: {file_path}")

    # Extract directory + filename
    directory, filename = os.path.split(file_path)

    # Step 1: Start local HTTP server
    os.chdir(directory)
    httpd = ReusableTCPServer(("", 0), CustomHandler)  # auto-pick free port
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
        r = requests.head(file_url)
        print("HEAD status:", r.status_code, "Content-Type:", r.headers.get("Content-Type"))

        # Step 5: Create video media container
        media_id = create_video_media(file_url, caption)
        print(f"Video media container created: {media_id}")

        # Step 6: Poll status until video is processed
        check_media_status(media_id)

        # Step 7: Publish video
        publish_id = publish_media(media_id)
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
