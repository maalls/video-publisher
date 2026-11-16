"""Smoke test Gemini : vérifie la clé et le JSON des 12 signes."""
from datetime import datetime

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


from video_publisher.core import PARIS
from video_publisher.text import generate


def main() -> int:
    day = datetime.now(PARIS).date()
    print(f"Appel Gemini pour l'horoscope du {day.isoformat()}...")
    script = generate(day)  # un seul appel API, validation du JSON incluse
    for item in script["horoscopes"]:
        print(f"{item['sign']} : {item['text']}")
    print("\nOK : clé valide, JSON des 12 signes conforme.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())