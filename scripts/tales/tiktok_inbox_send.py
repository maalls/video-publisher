#!/usr/bin/env python3
"""Envoie UN mp4 dans la boite de reception TikTok (brouillon), sans invite interactive.

A lancer seulement par publish_conte.py (apres approve + go explicite de Malo).
Utilise TIKTOK_PENDING_DIR (par defaut state/tiktok-private-pending, inscriptible par instinct) :
l'ancien defaut secrets/tiktok-pending n'etait pas inscriptible et a fait echouer l'envoi du 23/11.
Journal anti-doublon : un journal existant pour ce fichier bloque le renvoi (utiliser --status).
Lancer depuis var/project/tales avec PYTHONPATH=src.
"""
import sys, time
from pathlib import Path
import video_publisher.tiktok_inbox as t

video = Path(sys.argv[1]).resolve(strict=True)
t.PENDING_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
token = t.load_token('secrets/tiktok-client.json', 'secrets/tiktok-token.json')
user = t.user_info(token)
journal = Path('state') / ('tiktok-inbox-%s-%s.json' % (t.hashlib.sha256(token['open_id'].encode()).hexdigest()[:16], t.file_digest(video)))
print('compte', user.get('display_name'), 'journal', journal)
status = t.upload_inbox(video, token, journal, explicit_consent=True)
for _ in range(60):
    if status in {'SEND_TO_USER_INBOX', 'PUBLISH_COMPLETE', 'FAILED'}:
        break
    time.sleep(10)
    status = t.check_status(token, journal)
print('statut TikTok:', status)
