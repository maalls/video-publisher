#!/usr/bin/env python3
"""Unified Login only. Manual business OAuth and one-Reel publication. Python 3.10+."""
import argparse
import fcntl
import hashlib
import http.server
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import struct
import tempfile
import time
import urllib.error
import urllib.parse as U
import urllib.request as R

SCOPES = {'instagram_basic', 'instagram_manage_messages', 'instagram_manage_comments', 'instagram_content_publish', 'ads_management', 'ads_read'}
BASE = 'https://graph.facebook.com/'

class Stop(RuntimeError):
    pass

class NoRedirect(R.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

OPENER = R.build_opener(NoRedirect)

def save(path, obj):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.instagram-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(obj, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def load(path):
    path = Path(path)
    if path.stat().st_mode & 0o077:
        raise Stop('Fichier prive trop ouvert : chmod 600 requis')
    return json.loads(path.read_text())

def request(url, params=None, token=None, post=False):
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = U.urlencode(params or {}).encode() if post else None
    if params and not post:
        url += '?' + U.urlencode(params)
    req = R.Request(url, data=data, headers=headers, method='POST' if post else 'GET')
    try:
        with OPENER.open(req, timeout=90) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            body = json.load(error).get('error', {})
            code = body.get('code', 'unknown') if isinstance(body, dict) else 'unknown'
            sub = body.get('error_subcode', 'none') if isinstance(body, dict) else 'none'
        except (ValueError, OSError):
            code, sub = 'unknown', 'none'
        safe = lambda x: str(x) if str(x).isdigit() else 'unknown'
        raise Stop('Meta HTTP %s code=%s subcode=%s. Aucun renvoi automatique.' % (error.code, safe(code), safe(sub))) from None
    except (OSError, ValueError):
        raise Stop('Reponse incertaine. Ne pas repeter une creation/publication ; relire le journal.') from None
    if result.get('error'):
        raise Stop('Erreur Meta ; reponse masquee pour proteger les secrets')
    return result

def one(value):
    if 'data' in value:
        if not isinstance(value['data'], list) or len(value['data']) != 1:
            raise Stop('Reponse identite/OAuth ambigue')
        return value['data'][0]
    return value

def api(config, path, token, params=None, post=False):
    return request(BASE + config['api_version'] + '/' + path, params, token, post)

def identity(config, access):
    business = api(config, 'me', access, {'fields': 'client_business_id'})
    if not str(business.get('client_business_id', '')).isdigit():
        raise Stop('Portfolio business non confirme')
    result = api(config, 'me/assigned_instagram_accounts', access, {'fields': 'id,username'})
    users = result.get('data', [])
    if len(users) != 1 or result.get('paging', {}).get('next'):
        raise Stop('Partager exactement un seul compte Instagram dedie ; selection multiple refusee')
    user = users[0]
    if not str(user.get('id', '')).isdigit():
        raise Stop('ID professionnel absent')
    expected = (config.get('expected_username') or '').lstrip('@').lower()
    if expected and user.get('username', '').lower() != expected:
        raise Stop('Mauvais compte Instagram. Aucune publication.')
    if config.get('expected_business_id') and str(business['client_business_id']) != str(config['expected_business_id']):
        raise Stop('Mauvais portfolio business')
    return {'user_id': str(user['id']), 'username': user['username'],
            'client_business_id': str(business['client_business_id'])}

def inspect_token(config, access):
    data = api(config, 'debug_token', config['meta_app_id'] + '|' + config['meta_app_secret'],
               {'input_token': access})['data']
    if not data.get('is_valid') or str(data.get('app_id')) != str(config['meta_app_id']):
        raise Stop('Jeton invalide ou mauvaise app Meta')
    scopes = set(data.get('scopes', []))
    approved = set(config['approved_permissions']) | set(config.get('tolerated_extra_permissions', []))
    if not SCOPES.issubset(scopes) or not scopes.issubset(approved | {'public_profile'}):
        safe_scopes = sorted(x for x in scopes if isinstance(x, str) and __import__('re').fullmatch(r'[a-z_]{1,80}', x))
        missing = sorted(SCOPES - scopes)
        extra = sorted(scopes - approved - {'public_profile'})
        safe_extra = [x for x in extra if isinstance(x, str) and __import__('re').fullmatch(r'[a-z_]{1,80}', x)]
        raise Stop('Permissions refusees. Recues=' + ','.join(safe_scopes) + '; manquantes=' + ','.join(missing)
                   + '; hors accord=' + ','.join(safe_extra) + '. Aucun stockage/publication.')
    expires = int(data['expires_at'])
    if expires and expires <= time.time() + 120:
        raise Stop('Jeton expire ou presque expire')
    return {'permissions': sorted(scopes), 'expires_at': expires,
            'data_access_expires_at': int(data.get('data_access_expires_at', 0))}

def checked(config, token_path):
    token = load(token_path)
    if token['expires_at'] and time.time() + 120 >= token['expires_at']:
        raise Stop('Jeton expire ou presque expire : renouvellement/OAuth requis')
    inspect_token(config, token['access_token'])
    if token.get('config_id') != str(config['config_id']):
        raise Stop('Configuration differente du jeton conserve')
    user = identity(config, token['access_token'])
    if user['user_id'] != token['user_id'] or user['client_business_id'] != token['client_business_id']:
        raise Stop('Identite differente de la liaison OAuth')
    return token, user

def authorize(config, token_path, port):
    if config.get('messaging_permission_approved') is not True:
        raise Stop('Approbation explicite de la permission messages requise pour ce parcours')
    if set(config.get('approved_permissions', [])) != SCOPES:
        raise Stop('Configuration limitee aux six permissions explicitement approuvees requise')
    redirect = U.urlsplit(config['redirect_uri'])
    if redirect.scheme != 'https' or redirect.query or redirect.fragment or not redirect.hostname or redirect.username:
        raise Stop('Un callback HTTPS controle, sans query ni fragment, est requis')
    state = secrets.token_urlsafe(32)
    received = {}
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            parsed = U.urlsplit(self.path)
            query = U.parse_qs(parsed.query)
            valid = (parsed.path == (redirect.path or '/') and len(query.get('state', [])) == 1
                     and secrets.compare_digest(query['state'][0], state))
            if valid:
                received.update(query)
            self.send_response(200 if valid else 400)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            self.wfile.write(b'Retour recu. Vous pouvez fermer cette page.' if valid else b'Retour invalide.')
    params = {'client_id': config['meta_app_id'], 'config_id': config['config_id'],
              'redirect_uri': config['redirect_uri'], 'response_type': 'code', 'state': state,
              'display': 'popup', 'prompt': 'login'}
    with http.server.HTTPServer(('127.0.0.1', port), Handler) as server:
        server.timeout = 2
        print('Ouvrir dans votre navigateur personnel, choisir UNIQUEMENT le compte dedie :', flush=True)
        print('https://www.facebook.com/dialog/oauth?' + U.urlencode(params), flush=True)
        deadline = time.monotonic() + 600
        while not received and time.monotonic() < deadline:
            server.handle_request()
    if received.get('error') or len(received.get('code', [])) != 1:
        raise Stop('Consentement refuse, incomplet ou delai depasse. Aucun jeton enregistre.')
    response = request(BASE + config['api_version'] + '/oauth/access_token', {
        'client_id': config['meta_app_id'], 'client_secret': config['meta_app_secret'],
        'redirect_uri': config['redirect_uri'], 'code': received['code'][0]})
    access = response['access_token']
    inspected = inspect_token(config, access)
    user = identity(config, access)
    if Path(token_path).exists():
        old = load(token_path)
        if old['user_id'] != user['user_id'] or old['client_business_id'] != user['client_business_id']:
            raise Stop('Changement de compte/portfolio interdit ; ancien jeton conserve')
    save(token_path, {**user, **inspected, 'access_token': access,
         'issued_at': time.time(), 'config_id': str(config['config_id']), 'token_type': 'SUAT'})
    print(json.dumps({'authorized': True, **user, 'token_type': 'SUAT',
                      'expires_at': inspected['expires_at'], 'token_saved': str(token_path)}))

def refresh(config, token_path):
    raise Stop('Pas de refresh Instagram 60 jours pour SUAT. Reconnecter via authorize. Gestion SUAT non activee car elle exige business_management.')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def verify_url(url, expected):
    parts = U.urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise Stop('URL HTTPS publique requise, sans identifiants ni fragment')
    for info in socket.getaddrinfo(parts.hostname, parts.port or 443):
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise Stop('URL non publique refusee')
    h, size = hashlib.sha256(), 0
    try:
        with OPENER.open(url, timeout=90) as response:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                size += len(block)
                if size > 300_000_000:
                    raise Stop('Media depasse 300 Mo')
                h.update(block)
    except (OSError, ValueError):
        raise Stop('URL media inaccessible sans authentification ; aucun conteneur cree') from None
    if h.hexdigest() != expected:
        raise Stop('Les octets heberges different du MP4 local valide')

def validate_video(path):
    try:
        data = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
            '-show_format', '-of', 'json', str(path)], stderr=subprocess.PIPE))
        videos = [s for s in data['streams'] if s['codec_type'] == 'video']
        audios = [s for s in data['streams'] if s['codec_type'] == 'audio']
        if len(videos) != 1 or len(audios) != 1:
            raise Stop('Cet outil exige exactement une piste video et une piste audio')
        v, a = videos[0], audios[0]
        num, den = map(int, v['r_frame_rate'].split('/'))
        valid = (v['codec_name'] in {'h264', 'hevc'} and v['pix_fmt'] == 'yuv420p'
                 and v.get('field_order', 'progressive') in {'progressive', 'unknown'}
                 and 23 <= num / den <= 60 and int(v['width']) <= 1920
                 and 0.01 <= int(v['width']) / int(v['height']) <= 10
                 and int(v['bit_rate']) <= 25_000_000 and a['codec_name'] == 'aac'
                 and int(a['sample_rate']) <= 48000 and int(a['channels']) in {1, 2}
                 and int(a['bit_rate']) <= 128_000 and 3 <= float(data['format']['duration']) <= 900)
        if not valid:
            raise Stop('MP4 hors specifications Reels. Controler ffprobe avant publication.')
        # The source must be faststart. Full closed-GOP/edit-list inspection is not claimed here.
        atoms = []
        with Path(path).open('rb') as stream:
            end = Path(path).stat().st_size
            while stream.tell() + 8 <= end:
                start = stream.tell()
                size, kind = struct.unpack('>I4s', stream.read(8))
                if size == 1:
                    size = struct.unpack('>Q', stream.read(8))[0]
                if size == 0:
                    size = end - start
                if size < 8:
                    raise Stop('Structure MP4 invalide')
                atoms.append(kind)
                stream.seek(start + size)
        if b'moov' not in atoms or b'mdat' not in atoms or atoms.index(b'moov') > atoms.index(b'mdat'):
            raise Stop('MP4 faststart requis, moov avant mdat')
    except (subprocess.SubprocessError, FileNotFoundError, KeyError, ValueError, ZeroDivisionError):
        raise Stop('Controle ffprobe impossible. ffmpeg/ffprobe requis, aucun envoi.') from None

def validate_cover(path):
    cover = Path(path)
    if cover.suffix.lower() not in {'.jpg', '.jpeg'} or not 0 < cover.stat().st_size < 8_000_000:
        raise Stop('Couverture JPEG requise, moins de 8 Mo')
    try:
        data = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
            '-of', 'json', str(cover)], stderr=subprocess.PIPE))
        streams = data['streams']
        if (len(streams) != 1 or streams[0]['codec_name'] != 'mjpeg'
                or int(streams[0]['width']) * 16 != int(streams[0]['height']) * 9):
            raise Stop('Couverture JPEG verticale 9:16 requise')
    except (subprocess.SubprocessError, FileNotFoundError, KeyError, ValueError):
        raise Stop('Controle de la couverture impossible ; aucun envoi') from None

def plan(args, user):
    caption = Path(args.caption_file).read_text(encoding='utf-8').strip()
    if not caption or len(caption) > 2200:
        raise Stop('Legende requise, 2200 caracteres maximum dans cet outil')
    video = Path(args.video)
    if video.suffix.lower() != '.mp4' or not 0 < video.stat().st_size <= 300_000_000:
        raise Stop('MP4 requis, maximum 300 Mo')
    validate_video(video)
    result = {**user, 'sha256': digest(video), 'caption': caption,
              'is_ai_generated': args.ai_generated == 'yes', 'share_to_feed': args.share_to_feed == 'yes'}
    if getattr(args, 'cover', None):
        validate_cover(args.cover)
        result['cover_sha256'] = digest(args.cover)
    result['plan_sha256'] = hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return result

def status(config, token, journal):
    record = load(journal)
    if record['user_id'] != token['user_id']:
        raise Stop('Journal pour un autre compte')
    if not record.get('container_id'):
        raise Stop('Creation incertaine sans ID. Reconciliation manuelle obligatoire.')
    data = api(config, record['container_id'], token['access_token'], {'fields': 'status_code,status'})
    record['container_status'] = data.get('status_code', 'UNKNOWN')
    save(journal, record)
    if record.get('media_id'):
        media = api(config, record['media_id'], token['access_token'],
                    {'fields': 'id,permalink,caption,media_product_type,is_ai_generated'})
        record['verified_media'] = media
        save(journal, record)
        if (str(media.get('id')) != record['media_id'] or media.get('caption', '') != record['caption']
                or media.get('media_product_type') != 'REELS'
                or media.get('is_ai_generated') != record['is_ai_generated']):
            raise Stop('Publication creee mais metadonnees non confirmees. Ne pas republier ; inspecter le journal.')
        return {'container_status': record['container_status'], 'verified': True, 'media': media}
    return {'container_status': record['container_status'], 'phase': record['phase']}

def reel(args, config, token_path):
    token, user = checked(config, token_path)
    folder = Path(args.state_dir)
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.action in {'plan', 'create'}:
        spec = plan(args, user)
        journal = folder / ('reel-' + user['user_id'] + '-' + spec['sha256'] + '.json')
        if args.action == 'plan':
            print(json.dumps({**spec, 'journal': str(journal)}, ensure_ascii=False, indent=2))
            return
    else:
        journal = Path(args.journal)
    with open(str(journal) + '.lock', 'a') as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'status':
            print(json.dumps(status(config, token, journal), ensure_ascii=False))
            return
        if not args.execute:
            raise Stop('--execute requis pour tout effet distant')
        if args.action == 'create':
            if args.confirm_plan != spec['plan_sha256']:
                raise Stop('Empreinte du plan approuve requise')
            if journal.exists():
                raise Stop('Journal deja existant. Relire avec status ; aucune nouvelle creation.')
            verify_url(args.video_url, spec['sha256'])
            cover_url = getattr(args, 'cover_url', None)
            if bool(spec.get('cover_sha256')) != bool(cover_url):
                raise Stop('Couverture locale et URL HTTPS doivent etre fournies ensemble')
            if cover_url:
                verify_url(cover_url, spec['cover_sha256'])
            record = {**spec, 'phase': 'create_intent', 'created_at': time.time()}
            save(journal, record)
            params = {
                'media_type': 'REELS', 'video_url': args.video_url, 'caption': spec['caption'],
                'share_to_feed': str(spec['share_to_feed']).lower(),
                'is_ai_generated': str(spec['is_ai_generated']).lower()}
            if cover_url:
                params['cover_url'] = cover_url
            data = api(config, user['user_id'] + '/media', token['access_token'], params, post=True)
            record.update(container_id=str(data['id']), phase='container_created')
            save(journal, record)
            print(json.dumps({'journal': str(journal), 'phase': record['phase'], 'container_id': record['container_id']}))
            return
        record = load(journal)
        if args.confirm_plan != record['plan_sha256']:
            raise Stop('Empreinte du plan approuve requise')
        if record['phase'] != 'container_created':
            raise Stop('Publication deja tentee ou incertaine. Aucun renvoi ; status seulement.')
        current = status(config, token, journal)
        if current['container_status'] != 'FINISHED':
            raise Stop('Conteneur pas FINISHED. Relire status plus tard ; aucun publish.')
        record = load(journal)
        record['phase'] = 'publish_intent'
        save(journal, record)
        data = api(config, user['user_id'] + '/media_publish', token['access_token'],
                   {'creation_id': record['container_id']}, post=True)
        record.update(media_id=str(data['id']), phase='published')
        save(journal, record)
        print(json.dumps(status(config, token, journal), ensure_ascii=False))

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', default=str(Path(__file__).resolve().parents[2] / 'var/project/tales/secrets/instagram/unified-client.json'))
    p.add_argument('--token', default=str(Path(__file__).resolve().parents[2] / 'var/project/tales/secrets/instagram/unified-token.json'))
    p.add_argument('--state-dir', default=str(Path(__file__).resolve().parents[2] / 'var/project/tales/state/instagram-unified'))
    sub = p.add_subparsers(dest='action', required=True)
    auth = sub.add_parser('authorize')
    auth.add_argument('--port', type=int, default=8767)
    sub.add_parser('identity')
    sub.add_parser('refresh')
    for action in ['plan', 'create', 'status', 'publish']:
        s = sub.add_parser(action)
        if action in {'plan', 'create'}:
            s.add_argument('--video', required=True)
            s.add_argument('--cover', help='Couverture JPEG 9:16 optionnelle, liee au plan par SHA256')
            s.add_argument('--caption-file', required=True)
            s.add_argument('--ai-generated', choices=['yes', 'no'], required=True)
            s.add_argument('--share-to-feed', choices=['yes', 'no'], required=True)
        if action == 'create':
            s.add_argument('--video-url', required=True)
            s.add_argument('--cover-url')
        if action in {'status', 'publish'}:
            s.add_argument('--journal', required=True)
        if action in {'create', 'publish'}:
            s.add_argument('--execute', action='store_true')
            s.add_argument('--confirm-plan', required=True)
    args = p.parse_args(argv)
    config = load(args.config)
    if not __import__('re').fullmatch(r'v\d+\.0', config['api_version']):
        raise Stop('Version API explicite requise')
    if args.action == 'authorize':
        authorize(config, args.token, args.port)
    elif args.action == 'refresh':
        refresh(config, args.token)
    elif args.action == 'identity':
        _, user = checked(config, args.token)
        print(json.dumps(user))
    else:
        reel(args, config, args.token)

if __name__ == '__main__':
    try:
        main()
    except (Stop, OSError, ValueError, KeyError) as error:
        print(str(error) if isinstance(error, Stop) else 'Arret local. Configuration ou journal a verifier. Aucun renvoi automatique.')
        raise SystemExit(1)
