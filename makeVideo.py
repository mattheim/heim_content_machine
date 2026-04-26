import os
import shutil
import subprocess
import tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont

REEL_SIZE = (1080, 1920)
REEL_FPS = 30
OVERLAY_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
)

def _load_overlay_font(size):
    for font_path in OVERLAY_FONT_CANDIDATES:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size=size)
    return ImageFont.load_default()


def _text_size(draw, text, font, stroke_width=0):
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _wrap_overlay_text(draw, text, font, max_width):
    words = str(text).split()
    if not words:
        return []

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _text_size(draw, candidate, font)[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_overlay_text(draw, text, canvas_width, max_lines=3):
    max_width = int(canvas_width * 0.84)
    for font_size in range(92, 43, -4):
        font = _load_overlay_font(font_size)
        lines = _wrap_overlay_text(draw, text, font, max_width)
        if len(lines) <= max_lines and all(_text_size(draw, line, font)[0] <= max_width for line in lines):
            return font, lines

    font = _load_overlay_font(44)
    lines = _wrap_overlay_text(draw, text, font, max_width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and _text_size(draw, f"{lines[-1]}...", font)[0] > max_width:
            lines[-1] = lines[-1].rsplit(" ", 1)[0] if " " in lines[-1] else lines[-1][:-1]
        lines[-1] = f"{lines[-1].rstrip()}..."
    return font, lines


def _render_overlay_text(image, overlay_text):
    cleaned = " ".join(str(overlay_text or "").split())
    if not cleaned:
        return image

    canvas = image.convert("RGBA")
    text_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(text_layer)
    font, lines = _fit_overlay_text(draw, cleaned, canvas.width)
    if not lines:
        return image

    stroke_width = max(3, font.size // 14) if hasattr(font, "size") else 4
    line_gap = max(8, int((getattr(font, "size", 56)) * 0.18))
    line_heights = [_text_size(draw, line, font, stroke_width=stroke_width)[1] for line in lines]
    y = int(canvas.height * 0.075)

    # Subtle shadow/outline preserves readability without asking the image model to draw text.
    for line, line_height in zip(lines, line_heights):
        line_width = _text_size(draw, line, font, stroke_width=stroke_width)[0]
        x = (canvas.width - line_width) // 2
        draw.text(
            (x + 3, y + 3),
            line,
            font=font,
            fill=(0, 0, 0, 190),
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 190),
        )
        draw.text(
            (x, y),
            line,
            font=font,
            fill=(255, 255, 255, 255),
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 245),
        )
        y += line_height + line_gap

    return Image.alpha_composite(canvas, text_layer).convert("RGB")


def _build_reel_frame(image_path, canvas_size=REEL_SIZE, overlay_text=None):
    """Fit the generated image onto a 9:16 canvas and add code-rendered meme text."""
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
        canvas = _render_overlay_text(canvas, overlay_text)
        return np.array(canvas)

def make_video_with_music(image_path, audio_path, output_path, duration=12, overlay_text=None):
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg is required to render reels but was not found on PATH.")

    image_frame = _build_reel_frame(image_path, overlay_text=overlay_text)
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
