import os

music_folder = os.environ["MUSIC_DIRECTORY"]

def find_music(directory: str = "audio") -> str:
    """Return the path to a random .wav file from a directory.

    Args:
        directory: Folder to search (non-recursive). Defaults to "audio".

    Returns:
        String path to the randomly selected .wav file.

    Raises:
        FileNotFoundError: If the directory doesn't exist or no .wav files found.
    """

    from pathlib import Path
    import random

    base = Path(directory)
    if not base.is_dir():
        raise FileNotFoundError(f"Directory not found or not a folder: {directory}")

    candidates = [p for p in base.glob("*.wav") if p.is_file()]
    if not candidates:
        raise FileNotFoundError(f"No .wav files found in {base.resolve()}")

    return str(random.choice(candidates))

def main():
	dir = music_folder
	track = find_music(dir)
	print("track = ", track)
     
if __name__ == "__main__":
	main()
