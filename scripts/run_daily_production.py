"""Explicit gated production entrypoint; no bootstrap and no implicit opt-in."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

from video_publisher.core import PARIS, publish_time
from video_publisher.daily_plan import PlanError
from video_publisher.daily_runner import run, parse_grant
from video_publisher.durable_state import StateError
from video_publisher.production_config import load_state_session
from video_publisher import tiktok_inbox as tt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight', action='store_true', help='Read/decrypt state only, no platform calls')
    args = parser.parse_args()
    if os.environ.get('ENABLE_PRODUCTION') != 'true' and not args.preflight:
        raise StateError('Production non activée')
    session = load_state_session(os.environ)
    grant = parse_grant(session.state.get('grant'))
    if args.preflight:
        print('État privé lisible et accord structuré. Aucun appel vidéo, OAuth ou génération.')
        return
    now = datetime.now(PARIS)
    if now.hour != 5:
        raise PlanError('Production uniquement entre 05h00 et 05h59 Paris')
    root = Path('secrets'); root.mkdir(exist_ok=True)
    # Only the state is authoritative for rotated credentials. Static bootstrap
    # secrets never overwrite it on each run.
    for platform, filename in [('youtube','youtube-token.json'),('tiktok','tiktok-token.json')]:
        enabled = grant.youtube_enabled if platform == 'youtube' else grant.tiktok_enabled
        if not enabled:
            continue
        if session.state.get('refreshes', {}).get(platform) == 'intent':
            raise StateError('Refresh antérieur incertain; réautorisation requise')
        saved = session.state['tokens'].get(platform)
        expected = grant.youtube_account if platform == 'youtube' else grant.tiktok_account
        if not saved or saved.get('account') != expected:
            raise StateError('Jeton durable absent ou compte différent')
        tt.private_json(root / filename, saved['value'])
    if grant.tiktok_enabled:
        client = json.loads(os.environ.get('TIKTOK_CLIENT_JSON', '{}'))
        if set(client) != {'client_key','client_secret'} or not all(client.values()):
            raise StateError('Client TikTok non configuré')
        tt.private_json(root/'tiktok-client.json',client)
    os.environ['YOUTUBE_TOKEN_FILE'] = str(root/'youtube-token.json')
    os.environ['YOUTUBE_CHANNEL_ID'] = grant.youtube_account
    os.environ['ENABLE_YOUTUBE'] = 'true'
    tokens = {}

    def identities(current):
        youtube_id = tiktok_id = ''
        if current.youtube_enabled:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            from video_publisher.publishers.youtube import SCOPES
            credentials = Credentials.from_authorized_user_file(str(root/'youtube-token.json'), SCOPES)
            if credentials.expired and credentials.refresh_token:
                session.begin_refresh('youtube')
                credentials.refresh(Request())
                value = json.loads(credentials.to_json())
                session.replace_token('youtube', current.youtube_account, value)
                tt.private_json(root/'youtube-token.json',value)
            result = build('youtube','v3',credentials=credentials,cache_discovery=False).channels().list(part='id',mine=True).execute()
            ids = [item['id'] for item in result.get('items',[])]
            youtube_id = ids[0] if len(ids)==1 else ''
        if current.tiktok_enabled:
            # The loader may rotate a token. Immediately persist its private result.
            token = tt.load_token(root/'tiktok-client.json', root/'tiktok-token.json',
                                  before_refresh=lambda: session.begin_refresh('tiktok'))
            session.replace_token('tiktok', current.tiktok_account, token)
            user = tt.user_info(token)
            tiktok_id = user['open_id']; tokens['tiktok'] = token
        return youtube_id, tiktok_id

    def generate(day):
        subprocess.run(['video-publisher','--date',day.isoformat()],check=True)
        return Path('output')/(day.isoformat()+'-live')/'video.mp4'

    def youtube(video,day,current,persist):
        from video_publisher.publishers.youtube import upload
        meta = json.loads((video.parent/'metadata.json').read_text())
        journal=Path('state')/(day.isoformat()+'-live-youtube.json')
        return upload(video,meta,publish_time(day),journal,
                      persist_token=lambda token: session.replace_token('youtube',current.youtube_account,token),
                      persist_receipt=persist, before_refresh=lambda: session.begin_refresh('youtube'))

    def tiktok(video,day,current,persist):
        token=tokens['tiktok']
        if tt.user_info(token)['open_id'] != current.tiktok_account:
            raise StateError('Compte TikTok différent')
        journal=Path('state')/(day.isoformat()+'-tiktok.json')
        status=tt.upload_inbox(video,token,journal,explicit_consent=True,persist_receipt=persist)
        # No new upload, only a bounded status loop. Pending delivery is not failure.
        import time
        for _ in range(11):
            if status in {'SEND_TO_USER_INBOX','PUBLISH_COMPLETE','FAILED'}:break
            time.sleep(10);status=tt.check_status(token,journal);persist(tt.read_json(journal))
        receipt=tt.read_json(journal)
        if status not in {'SEND_TO_USER_INBOX','PUBLISH_COMPLETE'}:
            raise RuntimeError('Statut TikTok à réconcilier')
        return receipt

    result=run(session,now,generate,identities,youtube,tiktok)
    for platform,status in result.items():
        print(platform+': '+status)
    if 'uncertain' in result.values():
        raise StateError('Un envoi nécessite une vérification; aucun renvoi automatique')


if __name__=='__main__':
    try:
        main()
    except Exception:
        # Do not expose response bodies, credentials, signed URLs or tracebacks.
        print('Production arrêtée. Vérifier configuration et état privé; ne pas renvoyer aveuglément.',file=sys.stderr)
        raise SystemExit(1) from None
