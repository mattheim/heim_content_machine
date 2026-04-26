from __future__ import annotations
import os
import base64
import openai  
from PIL import Image
from openai import OpenAI
from prompt_gen import create_prompt
from dotenv import load_dotenv; load_dotenv()

API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
ORG_ID = os.environ.get("OPENAI_ORG_ID", "").strip()

def openai_generate_image(prompt: str, out_path: str, size: str = "auto") -> str:
    """Generate an image and save it to out_path."""
    client = OpenAI(api_key=API_KEY, organization=ORG_ID) if ORG_ID else OpenAI(api_key=API_KEY)
    try:
        result = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
        )
    except openai.PermissionDeniedError as e:
        raise SystemExit(
            "Permission denied for model gpt-image-1. Verify your organization: "
            f"Details: {e}"
        )
    except openai.BadRequestError as e:
        msg = str(e)
        # Surface safety/moderation blocks clearly
        if any(k in msg.lower() for k in ("moderation", "safety", "moderation_blocked")):
            raise SystemExit(
                "Image request blocked by safety/moderation. "
                "Try adding safe-for-work constraints (e.g., 'safe for work, non-sexual, no nudity, modest attire') "
                "or revise the prompt.\n"
                f"Details: {e}"
            )
        else:
            raise SystemExit(
                "Bad request to Images API. Check size (1024x1024, 1024x1536, 1536x1024, or auto) and prompt.\n"
                f"Details: {e}"
            )
    image_base64 = result.data[0].b64_json
    image_bytes = base64.b64decode(image_base64)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(image_bytes)
    return out_path

def reformat_to_1080x1920(
    in_path: str,
    out_path: str | None = None,
    method: str = "pad",  # "crop", "pad", or "stretch"
    background_color: tuple[int, int, int] = (0, 0, 0),
) -> str:
    """
    Reformat an image file to 1080x1920 for vertical reels.

    - crop: center-crops to 2:3 aspect, then resizes.
    - pad: resizes to fit within 1080x1920 and pads with background_color.
    - stretch: directly resizes to 1080x1920 (non-uniform scaling).
    """
    target_w, target_h = 1080, 1920
    target_ar = target_w / target_h  # 2/3 ≈ 0.6667

    img = Image.open(in_path).convert("RGB")
    w, h = img.size
    current_ar = w / h if h else target_ar

    # Prepare output path
    if out_path is None:
        root, ext = os.path.splitext(in_path)
        out_path = f"{root}_1080x1920{ext or '.png'}"

    if method == "stretch":
        out_img = img.resize((target_w, target_h), Image.LANCZOS)
        out_img.save(out_path)
        return out_path

    if method == "pad":
        # Scale to fit within target while preserving aspect
        scale = min(target_w / w, target_h / h)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        resized = img.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new("RGB", (target_w, target_h), color=background_color)
        left = (target_w - new_w) // 2
        top = (target_h - new_h) // 2
        canvas.paste(resized, (left, top))
        canvas.save(out_path)
        return out_path

    # Default: crop
    if abs(current_ar - target_ar) < 1e-3:
        # Already ~2:3; just resize to exact target
        cropped = img
    elif current_ar > target_ar:
        # Too wide -> crop width
        new_w = int(round(h * target_ar))
        new_w = max(1, min(new_w, w))
        left = (w - new_w) // 2
        right = left + new_w
        cropped = img.crop((left, 0, right, h))
    else:
        # Too tall -> crop height
        new_h = int(round(w / target_ar))
        new_h = max(1, min(new_h, h))
        top = (h - new_h) // 2
        bottom = top + new_h
        cropped = img.crop((0, top, w, bottom))

    out_img = cropped.resize((target_w, target_h), Image.LANCZOS)
    out_img.save(out_path)
    return out_path

def generate_image():
    
    prompt = create_prompt()

    out_path = "images/vertical_fix_3.png"
    size = "1024x1536"

    path = openai_generate_image(prompt=prompt, out_path=out_path, size=size)
    print(f"Saved: {path}")
    return path

def main():
    generate_image()

if __name__ == "__main__":
    main()
