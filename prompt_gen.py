import os
import json
import textwrap
import requests
from pathlib import Path

PROMPT_PROVIDER = os.environ.get("PROMPT_PROVIDER", "strategos").strip().lower()
STRATEGOS_BASE_URL = os.environ.get("STRATEGOS_BASE_URL", "http://localhost:38007").rstrip("/")
STRATEGOS_TIMEOUT_MS = int(os.environ.get("STRATEGOS_TIMEOUT_MS", "300000"))
DEFAULT_PROJECT_PATH = str(Path(__file__).resolve().parent)

BASE_SYSTEM = (
    """
        You are an expert prompt engineer specializing in image generation. 
        You always create highly detailed, cinematic prompts optimized for Image generation.
        Your core focus is greek mythology and you should always generate content that lives within that theme
        Greek mythology is eternal drama dressed in gold and marble — gods acting like mortals, mortals acting like fools, and fate laughing in the background.
        This meme tone treats ancient myths like modern tea, mixing cosmic grandeur with the dry humor of someone who’s seen too many prophecies go wrong.

    """
)

BASE_CAPTION = (
  """
  Think:
        Olympus meets Twitter.
        Eternal tragedy, but make it relatable.
        “Divine dysfunction” rendered as everyday pettiness.

        Caption Archetypes:
        Divine Irony (Gods Acting Petty)
        
        examples:
        “Zeus after seeing one (1) attractive mortal.”
        “Poseidon when someone builds a sandcastle.”
        “Athena watching you make the same mistake twice.”

        Use when you want to mock divine pride, jealousy, or hypocrisy. Tone = ancient side-eye.

        Mortal Chaos (Relatable Tragedy)
        examples:
        “Me ignoring every omen because I’m in love.”
        “Oracle said ‘don’t open the box’ — me: ...”
        “I too have flown too close to the sun (emotionally).”

        Use when the art depicts mortals in over their heads — hubris, heartbreak, or poetic collapse. Tone = self-aware doom.

        Ethereal Humor (Soft Melancholy + Sass)

        examples:
        “Eros texting ‘u up’ from Mount Olympus.”
        “Hypnos watching you pull another all-nighter.”
        “Hades when Persephone says she’s ‘just visiting’.”

        Use when you want dreamlike beauty with a wink — divine stillness meets modern loneliness. Tone = sad but stunning.
  Use the following templates and examples to generate a caption
    caption_templates = {
    {
        "template": "[Deity/Concept] be like: \"[modern phrase]\"",
        "example": "Fates be like: \"it’s already written \""
    },
    {
        "template": "[Statement of defiance or detachment]",
        "example": "No, I will not descend to the mortal plane."
    },
    {
        "template": "[Modern slang applied to ancient archetype]",
        "example": "He’s giving tragic hero energy."
    },
    {
        "template": "[Myth meets therapy]",
        "example": "Trying to heal but the chorus keeps narrating."
    },
    {
        "template": "[Existential one-liner]",
        "example": "Born dramatic. Cursed accordingly."
    }
  }

  tone_principles = (
      "Never too long. Gods don’t explain themselves.",
      "Mix high and low language. (“Eternal torment” + “bestie”).",
      "One joke per line. If it could be a tweet from Apollo, it’s perfect.",
      "Every caption should sound like it could be carved on marble or tweeted during a thunderstorm."
  )

  example_captions = (
      "Zeus be like: \"we were on a break.\"",
      "Aphrodite watching mortals call it \"situationships.\"",
      "Hades reading self-help books again.",
      "Me: *seeks peace* / Fate: \"that’s not your arc.\"",
      "Hermes when the delivery says \"out for revenge.\"",
      "Just saw my reflection and ruined my day — very Narcissus-coded.",
      "Eternal punishment but make it aesthetic.",
      "Persephone in spring: \"new season, same trauma.\"",
      "When the prophecy said \"don’t look back\" but you’re dramatic.",
      "Prometheus watching humans invent crypto.",
      "My love language is defying divine orders.",
      "Oracle typing \"lmao\" after every prediction.",
      "Poseidon when someone says \"I’m more of a pool person.\"",
      "Hypnos: \"bro go to sleep, it’s been three epochs.\"",
      "Athena when mortals ignore good advice (again)."
  )
  """
)

def _resolve_project_path() -> str:
    return os.environ.get("STRATEGOS_PROJECT_PATH") or DEFAULT_PROJECT_PATH

def _resolve_provider() -> str:
    provider = os.environ.get("PROMPT_PROVIDER", PROMPT_PROVIDER).strip().lower()
    if provider not in {"strategos", "ollama"}:
        raise ValueError(
            f"Unsupported PROMPT_PROVIDER={provider!r}. Expected 'strategos' or 'ollama'."
        )
    return provider

def _resolve_model(model: str | None) -> str:
    return model or os.environ.get("OLLAMA_MODEL") or "deepseek-r1:8b"

def _build_strategos_prompt(messages: list[dict], system_content: str, user_content: str) -> str:
    prompt_sections = [
        "You are generating one step of a social-media content pipeline.",
        "Follow the system instruction exactly and return only the requested output.",
        "",
        "SYSTEM INSTRUCTION:",
        system_content.strip(),
    ]
    if messages:
        prompt_sections.extend(["", "PRIOR CONVERSATION:"])
        for message in messages:
            role = str(message.get("role", "user")).upper()
            content = str(message.get("content", "")).strip()
            prompt_sections.append(f"{role}: {content}")
    prompt_sections.extend([
        "",
        "CURRENT USER REQUEST:",
        user_content.strip(),
        "",
        "Return only the requested text with no prefacing commentary.",
    ])
    return "\n".join(prompt_sections)

def _run_strategos_prompt(prompt: str) -> str:
    payload = {
        "projectPath": _resolve_project_path(),
        "prompt": prompt,
        "mode": "headless",
        "timeout": STRATEGOS_TIMEOUT_MS,
        "outputFormat": "json",
    }
    response = requests.post(
        f"{STRATEGOS_BASE_URL}/api/integration/workflow-execute",
        json=payload,
        timeout=max(10, (STRATEGOS_TIMEOUT_MS // 1000) + 15),
    )
    response.raise_for_status()
    body = response.json()
    result = body.get("result") or {}
    raw_content = (
        result.get("result")
        or result.get("output")
        or body.get("output")
        or ""
    )
    content = str(raw_content).strip()
    if not content:
        raise ValueError(
            "Strategos returned an empty response. "
            f"Top-level keys: {sorted(body.keys())}; result keys: {sorted(result.keys()) if isinstance(result, dict) else 'n/a'}"
        )
    return content

def _run_ollama_prompt(messages: list[dict], model: str | None = None) -> str:
    try:
        from ollama import chat
    except ImportError as exc:
        raise ImportError(
            "Ollama support requires the 'ollama' Python package. "
            "Install it with `pip install ollama` or switch PROMPT_PROVIDER to strategos."
        ) from exc

    response = chat(model=_resolve_model(model), messages=messages)
    content = response.message.content.strip()
    if not content:
        raise ValueError("Ollama returned an empty response.")
    return content

def chat_step(messages: list, system_content: str, user_content: str, model: str | None = None) -> str:
    messages.append({"role": "system", "content": system_content})
    messages.append({"role": "user", "content": user_content})
    provider = _resolve_provider()
    if provider == "strategos":
        prompt = _build_strategos_prompt(messages[:-2], system_content, user_content)
        content = _run_strategos_prompt(prompt)
    else:
        content = _run_ollama_prompt(messages, model=model)
    messages.append({"role": "assistant", "content": content})
    return content

def gen_theme(messages: list | None = None, model: str | None = None) -> str:
    system = BASE_SYSTEM + (
        "Propose a compelling mythic/fantasy theme that is based in Greek mythology "
        "and a character that exists in that period. Return only the theme text."
    )
    user = "Propose the theme now. Return only the theme text."
    return chat_step(messages, system, user, model)

def gen_visual_concept(messages: list, model: str | None = None) -> str:

    system = BASE_SYSTEM + "Generate only the Visual Concept. No commentary; return only the Visual Concept text."
    user = "Based on the theme above, write the Visual Concept. Return only the Visual Concept text."
    return chat_step(messages, system, user, model)

def gen_character_context(messages: list, model: str | None = None) -> str:
    """Generate the Character Context as a single string, using prior theme and visual concept."""
    system = BASE_SYSTEM + "Generate only the Character Context. No commentary; return only the Character Context text."
    user = (
        "Using the theme and Visual Concept above, write the Character Context. "
        "Return only the Character Context text."
    )
    return chat_step(messages, system, user, model)

def gen_caption(messages: list, model: str | None = None) -> str:
  
  system = BASE_SYSTEM + BASE_CAPTION
  user = (
      "Using the theme, Visual Concept, and Character Context above, write a concise meme caption. "
      "Use the caption template and examples in order to write the ideal caption based on the image"
      "Return only the caption text. The caption should be humorous and follow modern day memes and trends but also in line with the image"
  )
  return chat_step(messages, system, user, model)

def generate_all(model: str | None = None) -> tuple[str, str, str, str]:
    """
    Orchestrate the 4-step conversation:
      1) Theme 
      2) Visual Concept
      3) Character Context
      4) Caption

    Returns a tuple: (theme, visual_concept, character_context, caption)
    """
    messages: list = []
    theme = gen_theme(messages, model=model)
    visual = gen_visual_concept(messages, model=model)
    character = gen_character_context(messages, model=model)
    caption = gen_caption(messages, model=model)
    return theme, visual, character, caption

def generate_image_prompt(theme, visual_concept, character_context, caption):
    rules = (
        "Make sure text does not touch the edges of the image, with at least 10% padding on all sides."
    )

    style_era = (
        """
            Late 1990s to early 2000s console graphics — transition from PlayStation 1 to Xbox and PlayStation 2 aesthetics. 
            Low-poly but detailed geometry, early real-time lighting, and smoother rendering."
        """
    )

    geometry = (
        """
            Moderate polygon counts with recognizable anatomy and structure, 
            simple but defined silhouettes, 
            low-res normal detail, clean UV layouts, 
            minimal vertex wobble.
        """
    )

    textures = (
        """
            Higher-resolution textures (128x128 to 256x256 px), bilinear filtering for smoother surfaces, 
            subtle pixelation retained for authenticity, 
            less dithering, baked lighting and ambient occlusion in textures
        """
    )

    rendering = (
        """
          Affine texture mapping (warped textures), 
          No perspective correction, 
          16-bit color depth with dithering, 
          Vertex jitter and aliasing, 
          No hardware z-buffer (polygon overlap flicker), 
          Limited texture resolution (64×64 px), 
          Gouraud shading, 
          Fog masking for draw distance, 
          Texture seams and popping geometry, 
          Flat ambient lighting, 
          320×240 render resolution, 
          True to PS1 rendering limitations,
          Gouraud and early Phong shading mix, early hardware lighting and shadow approximation, 
          partial z-buffer correction, stable perspective mapping, light fog for atmosphere.
        """
    )

    lighting = (
        """
          Soft ambient lighting with subtle contrast, early dynamic light sources (e.g., sunlight, reflections), 
          gentle specular highlights and environmental color tinting.
        """
    )

    color_palette = (
        """
          24-bit color depth, balanced saturation, 
          realistic but stylized tones, 
          limited banding, 
          slight CRT bloom or warmth.
        """
    )

    effects = (
        """
          Early particle systems for dust and light rays, 
          smooth transparency, 
          texture mipmapping, 
          atmospheric fog for depth, no harsh pixel stepping.
        """
    )

    resolution = (
        """
          Rendered at 640x480 or 720p equivalent with mild CRT bloom and film grain for authenticity.","overall_mood": 
          "Retro-futuristic adventure with nostalgic charm — evokes the technical quirks and warmth of early 3D console visuals.
        """
    )

    visual_style = {
        "style_era": {style_era},
        "geometry": {geometry},
        "textures": {textures},
        "rendering": {rendering},
        "lighting": {lighting},
        "color_palette": {color_palette},
        "effects": {effects},
        "resolution": {resolution}
        }
    
    text_style = (
        """
          Font: White bold sans-serif (meme style) with black outline.
          Placement: Centered, clean, with lots of breathing room around figures (gods deserve negative space).
          Length: 1–2 lines max — just enough to sound like a divine whisper or sarcastic decree.
          Resolution: 1080×1080 (square marble tablet dimensions).
        """
    )

    instagram_reels_specs = {
    "render_resolution": "1080p ",
    
}


    prompt = f"""
    Create an image:

    rules: {rules}

    Theme: {theme}

    Visual Concept: {textwrap.fill(visual_concept, width=90)}
    Character Context: {textwrap.fill(character_context, width=90)}

    Text Overlay: {caption}
    Text Overlay Style: {text_style}

    Visual Style: {visual_style}

    instagram_reels_specs: {instagram_reels_specs}
    """

    return textwrap.dedent(prompt).strip()

def create_prompt():

  start_t=time.perf_counter()

  theme, visual, character, caption = generate_all()

  prompt = generate_image_prompt(theme,visual,character,caption)

  end_t=time.perf_counter()
  print(f"total runtime: {end_t-start_t:.2f}s")

  return prompt

def main():
    print("test create prompt")
    #create_prompt()

if __name__ == "__main__":
    main()
    
