import librosa
import numpy as np
import soundfile as sf


def load_audio(file_path):
    """Load stereo audio, return stereo and mono versions."""
    y_full, sr = librosa.load(file_path, sr=None, mono=False)  # keep stereo
    y_analysis = librosa.to_mono(y_full)                       # make mono copy for analysis
    return y_full, y_analysis, sr


def detect_beats(y, sr):
    """Detect tempo and beat timings."""
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    return tempo, beat_times


def compute_repetition(y, sr):
    """Compute repetition strength via chroma + recurrence matrix."""
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    R = librosa.segment.recurrence_matrix(chroma, mode='affinity', sym=True)
    rep_strength = np.sum(R, axis=1)
    return rep_strength


def compute_loudness_and_spectral(y, sr):
    """Compute RMS (loudness) and spectral centroid (brightness)."""
    S = np.abs(librosa.stft(y))
    rms = librosa.feature.rms(S=S)[0]
    centroid = librosa.feature.spectral_centroid(S=S, sr=sr)[0]
    return rms, centroid


def score_segments(
    y, sr, beat_times, rep_strength, rms, centroid,
    clip_duration=20.0, skip_end_buffer=5.0, debug=False
):
    """
    Score each bar-aligned segment (4/4 assumption) and return the best start time + score.
    Includes safeguards to avoid outros.
    """
    best_score = -np.inf
    best_start = 0

    # Align to bars (4/4 → every 4th beat)
    bar_times = beat_times[::4]

    # Track duration
    duration = librosa.get_duration(y=y, sr=sr)
    max_start = duration - clip_duration - skip_end_buffer
    outro_cutoff = duration * 0.8  # avoid last 20%

    for t in bar_times:
        if t > max_start:
            continue
        if t > outro_cutoff:
            continue
        if t < 20:  # skip intro
            continue

        start_time = t
        end_time = start_time + clip_duration

        # Convert to frame indices
        start_frame = librosa.time_to_frames(start_time, sr=sr)
        end_frame = librosa.time_to_frames(end_time, sr=sr)

        # Features in window
        rep = np.mean(rep_strength[start_frame:end_frame])
        loud = np.mean(rms[start_frame:end_frame])
        bright = np.mean(centroid[start_frame:end_frame])

        # Weighted score
        score = rep * 0.5 + loud * 0.3 + bright * 0.2

        # Penalty for late sections
        position_penalty = (start_time / duration) * 0.2
        score -= position_penalty

        # Bonus for mid-song region
        if duration * 0.25 <= start_time <= duration * 0.75:
            score *= 1.1

        if debug:
            print(f"[Candidate] t={start_time:.2f}s | rep={rep:.4f} loud={loud:.4f} "
                  f"bright={bright:.4f} penalty={position_penalty:.4f} -> score={score:.4f}")

        if score > best_score:
            best_score = score
            best_start = start_time

    if debug:
        print(f"\n[Winner] Start={best_start:.2f}s | Score={best_score:.4f}\n")

    return best_start, best_score


def extract_and_save_clip(y_full, sr, start_time, clip_duration, out_path):
    """Extract from stereo audio and save to file, preserving channels."""
    start_sample = int(start_time * sr)
    end_sample = int((start_time + clip_duration) * sr)

    if y_full.ndim == 2:  # stereo
        clip = y_full[:, start_sample:end_sample]
        sf.write(out_path, clip.T, sr, subtype="PCM_16")
    else:  # mono fallback
        clip = y_full[start_sample:end_sample]
        sf.write(out_path, clip, sr, subtype="PCM_16")

    return clip


# ------------------------------
# Main Pipeline
# ------------------------------

def find_chorus_clip(file_path, out_path, clip_duration=20.0, skip_end_buffer=5.0, debug=False):
    """Pipeline: analyze in mono, cut/export in stereo."""
    # 1. Load once
    y_full, y_analysis, sr = load_audio(file_path)

    # 2. Beats
    tempo, beat_times = detect_beats(y_analysis, sr)

    # 3. Features
    rep_strength = compute_repetition(y_analysis, sr)
    rms, centroid = compute_loudness_and_spectral(y_analysis, sr)

    # 4. Scoring
    best_start, best_score = score_segments(
        y=y_analysis,
        sr=sr,
        beat_times=beat_times,
        rep_strength=rep_strength,
        rms=rms,
        centroid=centroid,
        clip_duration=clip_duration,
        skip_end_buffer=skip_end_buffer,
        debug=debug
    )

    # 5. Extract & save (stereo)
    extract_and_save_clip(y_full, sr, best_start, clip_duration, out_path)

    return best_start, tempo, best_score, out_path

# ------------------------------
# Main Entrypoint
# ------------------------------

def main():
    file_path = "test"
    out_path = "test"
    clip_duration = 20.0
    skip_end_buffer = 5.0

    # Run pipeline
    best_start, tempo, best_score, out_path = find_chorus_clip(
        file_path=file_path,
        out_path=out_path,
        clip_duration=clip_duration,
        skip_end_buffer=skip_end_buffer,
        debug=True
    )

    # Handle tempo
    if isinstance(tempo, (np.ndarray, list)):
        tempo_val = float(tempo[0]) if len(tempo) > 0 else 0.0
    else:
        tempo_val = float(tempo)

    print("\n--- Results ---")
    print(f"Tempo Estimate: {tempo_val:.2f} BPM")
    print(f"Best Start Time: {best_start:.2f} sec")
    print(f"Score: {best_score:.4f}")
    print(f"Clip saved to: {out_path}")

if __name__ == "__main__":
    main()
