import argparse
from typing import List, Dict

from ollama_client import OllamaClient


def run_generate(client: OllamaClient, prompt: str, model: str | None) -> None:
    res = client.generate(prompt=prompt, model=model)
    # /api/generate returns { response: str, ... }
    print(res.get("response", ""))


def run_chat(client: OllamaClient, messages: List[Dict[str, str]], model: str | None) -> None:
    res = client.chat(messages=messages, model=model)
    # /api/chat returns { message: { role, content }, ... }
    msg = res.get("message", {})
    print(msg.get("content", ""))


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick Ollama API demo")
    parser.add_argument("--model", help="Model name (overrides OLLAMA_MODEL)")
    parser.add_argument("--prompt", help="Prompt string for /generate")
    parser.add_argument("--chat", action="store_true", help="Use chat endpoint with a user message")
    args = parser.parse_args()

    client = OllamaClient()

    # Quick health/model hints before the main call
    try:
        ver = client.version()
        # print(f"Ollama server: {ver}")  # keep quiet by default
    except Exception as e:
        print("Cannot reach Ollama at http://localhost:11434. Is `ollama serve` running?")
        print(f"Details: {e}")
        return

    try:
        if args.chat:
            if not args.prompt:
                parser.error("--chat requires --prompt as the user message")
            messages = [{"role": "user", "content": args.prompt}]
            run_chat(client, messages, args.model)
        else:
            if not args.prompt:
                parser.error("--prompt is required when not using --chat")
            run_generate(client, args.prompt, args.model)
    except Exception as e:
        # Offer helpful hints for common cases
        model = args.model
        print("Request failed.")
        print(e)
        if model and not client.is_model_available(model):
            print(f"Hint: model '{model}' is not available. Try: ollama pull {model}")
        else:
            print("Hints: verify model name, ensure server is v0.3+ and API enabled.")


if __name__ == "__main__":
    main()
