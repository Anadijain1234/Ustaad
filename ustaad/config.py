"""All settings come from environment variables (set them on Render, or in a local .env file that git ignores)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# --- Hindsight (the memory). One memory bank per industry: <prefix>-<industry> ---
HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY", "").strip()
HINDSIGHT_BASE_URL = os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io").strip()
HINDSIGHT_BANK_PREFIX = os.getenv("HINDSIGHT_BANK_PREFIX", "ustaad").strip()

# --- Groq (language model, speech-to-text, photo reading) ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo").strip()
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct").strip()

# --- Sarvam (Indian-language voice in/out, translation, backup brain) — optional ---
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "").strip()
SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v4").strip()
SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3").strip()
SARVAM_TRANSLATE_MODEL = os.getenv("SARVAM_TRANSLATE_MODEL", "mayura:v1").strip()
SARVAM_CHAT_MODEL = os.getenv("SARVAM_CHAT_MODEL", "sarvam-105b").strip()

# --- Who writes the answers. Default: Sarvam writes, Groq is the backup (WRITER=groq swaps them). ---
WRITER = os.getenv("WRITER", "sarvam").strip().lower()
SARVAM_WRITE_TIMEOUT = float(os.getenv("SARVAM_WRITE_TIMEOUT", "45"))  # slower than this -> Groq takes over

# --- Bring your own brain (optional): any AI that accepts OpenAI-style chat requests —
# OpenAI, Gemini, Claude, or a company's own model (Ollama / vLLM on its own server). If set, it writes first. ---
BRAIN_URL = os.getenv("BRAIN_URL", "").strip()      # e.g. https://api.openai.com/v1
BRAIN_KEY = os.getenv("BRAIN_KEY", "").strip()
BRAIN_MODEL = os.getenv("BRAIN_MODEL", "").strip()  # e.g. gpt-4o-mini, gemini-2.5-flash, llama3.1
BRAIN_NAME = os.getenv("BRAIN_NAME", "").strip()    # how it is shown in the app, e.g. "ChatGPT"

# --- Where it runs. On Vercel the project folder is read-only and instances stop when idle:
# keep the database and new custom industries in /tmp, and save memories before replying. ---
ON_VERCEL = bool(os.getenv("VERCEL"))
SYNC_RETAIN = ON_VERCEL or os.getenv("SYNC_RETAIN", "") == "1"

# --- Local storage ---
DB_PATH = os.getenv("DB_PATH", "/tmp/ustaad.db" if ON_VERCEL else str(ROOT / "ustaad.db"))
PACKS_DIR = ROOT / "data" / "packs"
CUSTOM_PACKS_DIR = Path(os.getenv("CUSTOM_PACKS_DIR", "/tmp/ustaad_packs" if ON_VERCEL else str(PACKS_DIR)))
PROCESSED_DIR = ROOT / "data" / "processed"


def bank_id(industry):
    return f"{HINDSIGHT_BANK_PREFIX}-{industry}"
