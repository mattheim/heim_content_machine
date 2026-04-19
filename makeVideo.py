import numpy as np
from PIL import Image
from moviepy import ImageClip, AudioFileClip

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

def make_video_with_music(image_path, audio_path, output_path, duration=20):
    # Build a reel-friendly 9:16 frame and keep it on screen for the full duration.
    image_frame = _build_reel_frame(image_path)
    image = ImageClip(image_frame).with_duration(duration)

    # Load audio and clip to duration
    audio = AudioFileClip(audio_path).subclipped(0, duration)

    # Set audio to video
    video = image.with_audio(audio)

    # Export with Instagram-safe defaults: 9:16, 30 FPS, yuv420p, faststart MP4.
    video.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=REEL_FPS,
        audio_bitrate="128k",
        ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
    )

    audio.close()
    video.close()
    image.close()

if __name__ == "__main__":

    print ("running example usage")
    # Example usage
    
    #make_video_with_music(
    #    image_path="images/hades_at_the_function.png", 
    #    audio_path="audio/OT_testclip.mp3", 
    #    output_path="videos/final_video.mp4", 
    #    duration=20  # length of video in seconds
    #)
