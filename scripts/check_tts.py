"""Test réel Google Cloud TTS, sans Gemini, vidéo ni publication."""
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import argparse
from datetime import date
import json
import os
import sys
import tempfile
import wave

from video_publisher.audio import synthesize
from video_publisher.core import demo_script, required

ROOT = Path(__file__).resolve().parents[1]


class CheckError(ValueError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Tester les 12 signes (12 appels TTS)")
    args = parser.parse_args()
    try:
        credentials = Path(required("GOOGLE_APPLICATION_CREDENTIALS")).expanduser()
        if not credentials.is_absolute():
            credentials = ROOT / credentials
        if not credentials.is_file():
            raise CheckError("JSON introuvable : vérifier GOOGLE_APPLICATION_CREDENTIALS dans .env")
        try:
            data = json.loads(credentials.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            raise CheckError("JSON vide ou invalide : utiliser le fichier téléchargé de Google Cloud") from None
        if not isinstance(data, dict) or data.get("type") != "service_account" or not all(
            data.get(key) for key in ("private_key", "client_email", "token_uri", "project_id")
        ):
            raise CheckError("Le JSON doit être une clé de compte de service Google Cloud")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials)
        items = demo_script(date.today())["horoscopes"]
        if not args.all:
            items = items[:1]
        output = ROOT / "output" / ("tts-check-all" if args.all else "tts-check")
        output.mkdir(parents=True, exist_ok=True)
        print(f"Appel TTS réel : {len(items)} extrait(s), sans relance automatique...", flush=True)
        # Dossier neuf : un ancien WAV ne doit jamais masquer un appel API en échec.
        with tempfile.TemporaryDirectory(prefix=".run-", dir=output) as tmp:
            paths = synthesize(items, Path(tmp), demo=False)
            for path in paths:
                with wave.open(str(path), "rb") as audio:
                    if audio.getnframes() == 0:
                        raise CheckError("Audio WAV vide")
            for item, path in zip(items, paths):
                target = output / path.name
                path.replace(target)
                print(f"{item['sign']} : {target.relative_to(ROOT)}")
        print("OK : audio reçu de Google et WAV non vide. Écoute les fichiers pour valider la voix.")
        return 0
    except CheckError as error:
        # Seuls les messages locaux contrôlés ci-dessus sont affichés tels quels.
        print(f"Échec : {error}", file=sys.stderr)
    except Exception as error:
        # Pas de traceback, contenu du JSON, réponse HTTP ni jeton dans les logs.
        print(f"Échec TTS ({type(error).__name__}). Voir le tableau de dépannage de l'issue #3.",
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
