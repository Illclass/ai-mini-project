import os
import requests
from dotenv import load_dotenv

# Load .env (even if already loaded in main.py, duplicate calls are harmless)
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set. Please check your .env file or environment variables.")


def synthesize(text: str, voice: str = "nova", timeout: float = 30.0) -> bytes:
    """텍스트 → MP3 바이트 (OpenAI tts-1). 실패하면 예외."""
    response = requests.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
        json={"model": "tts-1", "input": text, "voice": voice},
        timeout=timeout,
    )
    if response.status_code != 200:
        raise RuntimeError(f"TTS request failed: {response.status_code}")
    return response.content


def text_to_speech(text: str, output_path: str = "output.mp3"):
    with open(output_path, "wb") as f:
        f.write(synthesize(text))
    return output_path
