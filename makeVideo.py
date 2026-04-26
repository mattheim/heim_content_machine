import os
import shutil
import subprocess
import tempfile
import numpy as np
from PIL import Image

REEL_SIZE = (1080, 1920)
REEL_FPS = 30

def _build_reel_frame(image_path, canvas_size=REEL_SIZE):
    """Fit the generated image onto a 9:16 canvas without cropping text."""
    canvas_width, canvas_height = canvas_size

    with Image.open(image_path) as source:
        image = source.convert("RGB")
        src_width, src_height = image.size
        scale = min(canvas_width / src_width, canvas_height / src_height)
        resized_size = (
            max(2, int(round(src_width * scale))),
            max(2, int(round(src_height * scale))),
        )
        image = image.resize(resized_size, Image.LANCZOS)

        canvas = Image.new("RGB", canvas_size, (0, 0, 0))
        x = (canvas_width - resized_size[0]) // 2
        y = (canvas_height - resized_size[1]) // 2
        canvas.paste(image, (x, y))
        return np.array(canvas)

def make_video_with_music(image_path, audio_path, output_path, duration=12):
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg is required to render reels but was not found on PATH.")

    image_frame = _build_reel_frame(image_path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_image:
        temp_image_path = temp_image.name

    try:
        Image.fromarray(image_frame).save(temp_image_path, format="PNG")
        command = [
            ffmpeg_path,
            "-y",
            "-loop",
            "1",
            "-framerate",
            str(REEL_FPS),
            "-i",
            temp_image_path,
            "-i",
            audio_path,
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-profile:v",
            "main",
            "-level",
            "4.0",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(REEL_FPS),
            "-vf",
            "scale=1080:1920:flags=lanczos,format=yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            "-shortest",
            output_path,
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "ffmpeg failed while rendering the Instagram reel.\n"
            f"stderr: {exc.stderr}"
        ) from exc
    finally:
        if os.path.exists(temp_image_path):
            os.remove(temp_image_path)

if __name__ == "__main__":

    print ("running example usage")
    # Example usage
    
    #make_video_with_music(
    #    image_path="images/hades_at_the_function.png", 
    #    audio_path="audio/OT_testclip.mp3", 
    #    output_path="videos/final_video.mp4", 
    #    duration=12  # length of video in seconds
    #)
