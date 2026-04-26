from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from prompt_gen import (  # noqa: E402
    gen_caption_candidates,
    gen_character_context,
    gen_theme,
    gen_visual_concept,
    select_best_content,
)


def run_caption_preview(model: str | None = None, runs: int = 1) -> None:
    for index in range(1, runs + 1):
        messages: list[dict] = []

        print(f"\n{'=' * 80}")
        print(f"CAPTION PREVIEW RUN {index}")
        print(f"{'=' * 80}")

        theme = gen_theme(messages, model=model)
        visual = gen_visual_concept(messages, model=model)
        character = gen_character_context(messages, model=model)
        candidates = gen_caption_candidates(messages, model=model)
        selected = select_best_content(messages, candidates, model=model)

        print("\nTHEME")
        print(theme)

        print("\nVISUAL CONCEPT")
        print(visual)

        print("\nCHARACTER CONTEXT")
        print(character)

        print("\nCANDIDATES")
        for candidate_number, candidate in enumerate(candidates, start=1):
            print(f"\n[{candidate_number}] {candidate['style_label']}")
            print(f"Overlay: {candidate['overlay_text']}")
            print(f"Hook: {candidate['caption_hook']}")
            print(f"Body: {candidate['post_body']}")
            print(f"Hashtags: {' '.join(candidate['hashtags'])}")
            print(f"First comment: {candidate['first_comment']}")

        print("\nSELECTED")
        print(json.dumps(selected, indent=2))

        print("\nFINAL INSTAGRAM CAPTION")
        print(selected["instagram_caption"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the caption generation pipeline and print candidate captions to the console."
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional model override passed through to the prompt generation functions.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of times to run the caption generation flow.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_caption_preview(model=args.model, runs=max(1, args.runs))


if __name__ == "__main__":
    main()
