import argparse
from datetime import date, datetime
import json
import logging
import os
import shutil
from pathlib import Path
import sys
from .core import PARIS, demo_script, publish_time, save_json, validate_script

log = logging.getLogger("video_publisher")


def main():
    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser(description="Générer un horoscope vertical quotidien")
    parser.add_argument("--date", type=date.fromisoformat, default=datetime.now(PARIS).date())
    parser.add_argument("--demo", action="store_true", help="Texte exemple et silence, aucun appel externe")
    parser.add_argument("--publish-youtube", action="store_true")
    parser.add_argument("--private-test", action="store_true", help="Upload privé, sans programmation publique")
    parser.add_argument("--width", type=int, default=1080, help="270 pour un test rapide, 1080 en production")
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--state", type=Path, default=Path("state"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        execute(args)
    except Exception as error:
        # Ne pas imprimer les réponses HTTP, URL signées ni valeurs de secrets.
        log.error("Échec du pipeline (%s). Vérifier configuration, quotas, fichiers et journaux d'état.",
                  type(error).__name__)
        if isinstance(error, OSError):
            log.error("%s", str(error))
        elif isinstance(error, (ValueError, FileNotFoundError, RuntimeError)) and not hasattr(error, "response"):
            # Les messages applicatifs sont contrôlés; pas de traceback d'API en CI publique.
            log.error("%s", str(error) if type(error) in (ValueError, FileNotFoundError, RuntimeError) else "API refusée")
        sys.exit(1)


def execute(args):
    if args.width <= 0 or args.width % 18:
        raise ValueError("La largeur doit être un multiple positif de 18")
    if args.demo and args.publish_youtube:
        raise ValueError("Publication d'une démo interdite")
    if args.private_test and not args.publish_youtube:
        raise ValueError("--private-test exige --publish-youtube")
    if args.publish_youtube and os.environ.get("ENABLE_YOUTUBE", "false").lower() != "true":
        raise ValueError("Activer ENABLE_YOUTUBE seulement après configuration de la chaîne")
    if args.publish_youtube and args.width != 1080:
        raise ValueError("Publication autorisée seulement en 1080x1920")
    if args.publish_youtube and not args.private_test and publish_time(args.date) <= datetime.now(PARIS):
        raise ValueError("Heure de publication dépassée. Choisir demain ou faire un test privé")
    mode = "demo" if args.demo else "live"
    if args.private_test:
        mode += "-private"
    folder = args.output / f"{args.date.isoformat()}-{mode}"
    folder.mkdir(parents=True, exist_ok=True)
    journal = args.state / f"{args.date.isoformat()}-{mode}-youtube.json"
    if args.publish_youtube and journal.exists():
        state = json.loads(journal.read_text(encoding="utf-8"))
        if state.get("status") == "complete":
            log.info("Upload déjà effectué pour cette date : aucune nouvelle publication")
            return
        raise RuntimeError("Upload précédent incertain : vérifier YouTube Studio avant toute relance")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise FileNotFoundError("Installer ffmpeg et ffprobe avant de générer")
    if not args.demo:
        from .core import required
        required("GEMINI_API_KEY")
        required("GEMINI_MODEL")
        if not Path(required("GOOGLE_APPLICATION_CREDENTIALS")).is_file():
            raise FileNotFoundError("Fichier de compte de service TTS introuvable")
        if args.publish_youtube:
            required("YOUTUBE_CHANNEL_ID")
            if not Path(required("YOUTUBE_TOKEN_FILE")).is_file():
                raise FileNotFoundError("Fichier OAuth YouTube introuvable")
    music = os.environ.get("MUSIC_FILE", "").strip()
    if music and not Path(music).is_file():
        raise FileNotFoundError("MUSIC_FILE introuvable")
    script_path = folder / "script.json"
    if script_path.exists():
        script = validate_script(json.loads(script_path.read_text(encoding="utf-8")), args.date)
    else:
        if args.demo:
            script = demo_script(args.date)
        else:
            from .text import generate
            script = generate(args.date)
        save_json(script_path, script)
    from .audio import synthesize
    from .render import render
    from .metadata import metadata
    log.info("Synthèse audio (%s)", mode)
    audio = synthesize(script["horoscopes"], folder, args.demo)
    log.info("Rendu vidéo")
    timeline = render(script, audio, folder, args.date, args.demo, args.width,
                      Path(music) if music else None)
    save_json(folder / "timeline.json", {"segments": timeline})
    meta = metadata(args.date, timeline)
    save_json(folder / "metadata.json", meta)
    if args.publish_youtube:
        from .publishers.youtube import upload
        upload(folder / "video.mp4", meta, publish_time(args.date), journal, args.private_test)
        log.info("Upload YouTube terminé et paramètres de confidentialité/programmation vérifiés.")
    log.info("Fichiers prêts : %s", folder)


if __name__ == "__main__":
    main()
