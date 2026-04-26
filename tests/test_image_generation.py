from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import image_generator


def test_openai_generate_image_writes_png_bytes(monkeypatch, tmp_path):
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9sZ8nK0AAAAASUVORK5CYII="
    )
    encoded_image = base64.b64encode(png_bytes).decode("ascii")

    class FakeImages:
        def generate(self, **kwargs):
            assert kwargs["model"] == "gpt-image-1"
            assert kwargs["prompt"] == "test prompt"
            assert kwargs["size"] == "1024x1536"
            return SimpleNamespace(data=[SimpleNamespace(b64_json=encoded_image)])

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.images = FakeImages()

    monkeypatch.setattr(image_generator, "OpenAI", FakeClient)

    out_path = tmp_path / "images" / "generated.png"
    saved_path = image_generator.openai_generate_image(
        prompt="test prompt",
        out_path=str(out_path),
        size="1024x1536",
    )

    assert saved_path == str(out_path)
    assert out_path.exists()
    assert out_path.read_bytes() == png_bytes


def test_reformat_to_1080x1920_pad_creates_vertical_output(tmp_path):
    source_path = tmp_path / "source.png"
    output_path = tmp_path / "reformatted.png"

    Image.new("RGB", (1200, 800), color=(255, 0, 0)).save(source_path)

    saved_path = image_generator.reformat_to_1080x1920(
        in_path=str(source_path),
        out_path=str(output_path),
        method="pad",
        background_color=(0, 0, 0),
    )

    assert saved_path == str(output_path)
    with Image.open(output_path) as image:
        assert image.size == (1080, 1920)


def test_generate_image_prompt_includes_caption_and_safe_area():
    generated_prompt = __import__("prompt_gen").generate_image_prompt(
        theme="Athena discovers debugging",
        visual_concept="A glowing temple console filled with scroll-like terminal output.",
        character_context="Athena is calm while everyone else panics over one missing semicolon.",
        caption="When wisdom reviews your stack trace",
    )

    assert "Athena discovers debugging" in generated_prompt
    assert "When wisdom reviews your stack trace" in generated_prompt
    assert "Instagram mobile viewing" in generated_prompt
