"""Explicit one-video upload, no scheduling or Direct Post."""
import argparse
import hashlib
from pathlib import Path
import time

from video_publisher.tiktok_inbox import (TikTokError, check_status, cleanup_expired_pending, file_digest,
                                        load_token, read_json, resume_pending, retry_empty_journal, upload_inbox, user_info)


def main():
    parser = argparse.ArgumentParser(description="Transférer un MP4 dans la boîte de réception TikTok")
    parser.add_argument("video", type=Path, nargs="?")
    parser.add_argument("--status", type=Path, help="Lire un journal existant, sans transfert")
    parser.add_argument("--retry-empty", type=Path, help="Reprise explicite d’une init bloquée avant transfert, journal conservé")
    parser.add_argument("--resume", type=Path, help="Reprendre la même init avant tout PUT, sans nouvelle init")
    args = parser.parse_args()
    if bool(args.video) == bool(args.status):
        parser.error("Choisir un MP4 OU --status journal.json")
    if args.resume and (not args.video or args.status or args.retry_empty):
        parser.error("--resume exige le MP4 et exclut --status/--retry-empty")
    if args.retry_empty and (not args.video or args.status):
        parser.error("--retry-empty exige le MP4 et exclut --status")
    cleanup_expired_pending()
    token = load_token("secrets/tiktok-client.json", "secrets/tiktok-token.json")
    user = user_info(token)
    # repr escapes newline/control characters in external profile data.
    print("Compte cible :", repr(user.get("display_name", "")))
    print("Identifiant de compte (open_id) :", repr(token["open_id"]))
    if args.status:
        journal = args.status
        status = check_status(token, journal)
        print("Statut TikTok :", repr(status))
        print("Octets reçus selon TikTok :", read_json(journal).get("uploaded_bytes", "non indiqué"))
    else:
        video = args.video.resolve(strict=True)
        identity = hashlib.sha256(token["open_id"].encode()).hexdigest()[:16]
        journal = Path("state") / f"tiktok-inbox-{identity}-{file_digest(video)}.json"
        if args.retry_empty:
            print("Ancienne tentative conservée :", str(args.retry_empty))
            print("Uniquement si le premier essai disait hôte non reconnu AVANT tout envoi.")
            print("Une nouvelle initialisation sera créée; l’ancienne URL n’est plus disponible.")
            if input("Pour vérifier zéro octet puis préparer une nouvelle tentative, tape REPRENDRE : ") != "REPRENDRE":
                print("Annulé, aucune initialisation.")
                return
            journal = retry_empty_journal(token, args.retry_empty, video)
        if args.resume:
            journal = args.resume
            print("Reprise de la MÊME initialisation, aucun nouvel envoi init.")
        print("Vidéo :", str(video))
        print("Journal :", str(journal))
        print("Aperçu : ouvre ce MP4 dans QuickTime. Vérifie la vidéo et le compte ci-dessus.")
        print("Ce transfert n'est pas une publication. Tu finiras dans TikTok et choisiras les réglages,")
        print("le titre, les mentions IA/commerciales et les droits audio applicables.")
        if input("Pour envoyer CETTE vidéo à CE compte, tape ENVOYER : ") != "ENVOYER":
            print("Annulé, aucun transfert.")
            return
        if args.resume:
            status = resume_pending(video, token, journal, explicit_consent=True)
        else:
            status = upload_inbox(video, token, journal, explicit_consent=True)
        for _ in range(11):
            if status in {"SEND_TO_USER_INBOX", "PUBLISH_COMPLETE", "FAILED"}:
                break
            time.sleep(10)
            status = check_status(token, journal)
    messages = {
        "SEND_TO_USER_INBOX": "Notification envoyée à TikTok. Ouvre-la pour vérifier et terminer dans l'app. Rien n'est publié par ce script.",
        "PUBLISH_COMPLETE": "TikTok confirme que le contenu a été publié depuis son parcours d'édition.",
        "FAILED": "TikTok signale un échec. Ne pas renvoyer sans vérifier l'app et le journal.",
    }
    print(messages.get(status, "Traitement encore en attente. Relire plus tard avec --status et ce journal."))
    print("Journal :", str(journal))
    if status == "FAILED":
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except TikTokError as error:
        print(str(error))
        raise SystemExit(1) from None
    except (ValueError, OSError, KeyError):
        print("Opération arrêtée. Vérifier la configuration ou relire le statut du journal; ne pas renvoyer aveuglément.")
        raise SystemExit(1) from None
