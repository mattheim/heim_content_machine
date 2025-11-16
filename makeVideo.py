from moviepy import ImageClip, AudioFileClip

def make_video_with_music(image_path, audio_path, output_path, duration=20):
    # Load image and set duration
    image = ImageClip(image_path).with_duration(duration)

    # Load audio and clip to duration
    audio = AudioFileClip(audio_path).subclipped(0, duration)

    # Set audio to video
    video = image.with_audio(audio)

    # Write output video
    video.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=24)

if __name__ == "__main__":

    print ("running example usage")
    # Example usage
    
    #make_video_with_music(
    #    image_path="images/hades_at_the_function.png", 
    #    audio_path="audio/OT_testclip.mp3", 
    #    output_path="videos/final_video.mp4", 
    #    duration=20  # length of video in seconds
    #)
