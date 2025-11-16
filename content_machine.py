from __future__ import annotations
import os
import re
import time
from datetime import datetime
from dotenv import load_dotenv; load_dotenv()
from utils.santize import sanitize_filename
from image_generator import openai_generate_image
from prompt_gen import generate_all, generate_image_prompt
from updateAudio import find_chorus_clip
from utils.findmusic import find_music
from makeVideo import make_video_with_music
from insta_post import post_local_video_via_ngrok

# Prefer environment override; default to local ./audio
music_folder = os.getenv("MUSIC_DIRECTORY", "audio")

def run_machine():
	music_dir = music_folder
      
	start_t=time.perf_counter()
	print("start")
	print("loading...")
	
	# 1) Generate prompt 
	print("start prompt gen")
	theme, visual, character, caption = generate_all()
	print("next...")
	image_prompt = generate_image_prompt(theme, visual, character, caption)
	print("end prompt gen")

	# 2) Build dated filename with caption
	ts = datetime.now().strftime("%Y%m%d_%H%M%S")
	name_part = sanitize_filename(caption)
	out_dir = "images"
	os.makedirs(out_dir, exist_ok=True)
	image_out_path = os.path.join(out_dir, f"{ts}_{name_part}.png")

	print("start image gen")
	# 3) Generate the image (portrait size for reels workflow)
	saved_path = openai_generate_image(prompt=image_prompt, out_path=image_out_path, size="1024x1536")
	print("end image gen")
      
	# 4) generate the music to pair with the image
	print("start music editing process")
	track = find_music(music_dir)
	print("track =", repr(track))
	# Defensive check to surface path issues early
	if not os.path.isfile(track):
		print(f"Selected track does not exist: {repr(track)}", flush=True)
		print("Tip: verify the path, extension case, and that the file is fully downloaded (not a cloud placeholder).", flush=True)
		return
  
	track_file_path = track
	# Build audio output path under ./audio using input track's basename
	out_dir_audio = "audio"
	os.makedirs(out_dir_audio, exist_ok=True)
	base_name = os.path.splitext(os.path.basename(track_file_path))[0]
	audio_out_path = os.path.join(out_dir_audio, f"reel_clip_edit_{base_name}.wav")
	clip_duration=20.0
	skip_end_buffer=5.0

	best_start, tempo, best_score, final_out_path = find_chorus_clip(
		track_file_path,
		audio_out_path,
		clip_duration,
		skip_end_buffer,
		debug=True
	)
      
	# Derive base name of image (without extension) for video output
	final_str = os.path.splitext(os.path.basename(saved_path))[0]

	# Ensure videos output directory exists and compose final paths correctly
	out_dir_video = "videos"
	os.makedirs(out_dir_video, exist_ok=True)
	make_video_with_music(
        image_path=saved_path,
        audio_path=final_out_path,
        output_path=os.path.join(out_dir_video, f"{final_str}.mp4"),
        duration=20
    )

	caption = caption
	local_video = os.path.join(out_dir_video, f"{final_str}.mp4")

	post_local_video_via_ngrok(local_video, caption)

	end_t=time.perf_counter()
	print(f"total runtime: {end_t-start_t:.2f}s")

	# Basic visibility in logs
	'''
	print("Theme:", theme)
	print("Caption:", caption)
	print("visual:", visual)
	print("character", character)
	print("image prompt (safe)", image_prompt[:500])
	print("Saved image:", saved_path)
	'''
	return print("process finished")


if __name__ == "__main__":
    run_machine()
