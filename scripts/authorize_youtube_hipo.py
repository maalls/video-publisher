"""OAuth YouTube pour un compte nomme, lance sur hipo (sans navigateur), comme authorize_tiktok_hipo.py.
Ecrit le lien d'autorisation dans un fichier (0600), attend le retour sur 127.0.0.1:PORT (port a rediriger
depuis le navigateur de l'utilisateur : ssh -L PORT:127.0.0.1:PORT hipo), ecrit le jeton du compte dans le
dossier secrets (jamais ecrase sans copie -avant-), verifie la chaine (lecture seule) et affiche son nom et
son identifiant public. N'affiche jamais le code ni les jetons.
  authorize_youtube_hipo.py --account maalls [--port 8766]"""
import argparse, os, secrets as pysecrets, shutil, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
sys.path.insert(0, 'src')
import requests
from google_auth_oauthlib.flow import Flow
from video_publisher.publishers.youtube import SCOPES
from video_publisher.youtube_accounts import LABEL, AccountError, load_registry

S = Path('var/project/tales/secrets')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--account', required=True); p.add_argument('--port', type=int, default=8766)
    a = p.parse_args()
    if not LABEL.match(a.account): raise SystemExit('nom de compte invalide')
    try: item = load_registry(S / 'youtube-accounts.json')['accounts'][a.account]
    except (AccountError, KeyError): raise SystemExit('compte absent du registre')
    target = S / item['token_file']
    redirect = 'http://127.0.0.1:%d/' % a.port
    flow = Flow.from_client_secrets_file(str(S / 'client_secret.json'), SCOPES, redirect_uri=redirect)
    state = pysecrets.token_urlsafe(32)
    url, _ = flow.authorization_url(access_type='offline', prompt='consent', state=state, include_granted_scopes='false')
    link = Path('/tmp/youtube-auth-link-%s.txt' % a.account); link.write_text(url); link.chmod(0o600)
    got = {}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *x): pass
        def do_GET(self):
            q = parse_qs(urlsplit(self.path).query)
            ok = q.get('state', [''])[0] == state and q.get('code') and not q.get('error')
            if ok: got['code'] = q['code'][0]
            self.send_response(200 if ok else 400); self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store'); self.end_headers()
            self.wfile.write('Autorisation recue, tu peux fermer cet onglet.'.encode() if ok else b'Retour invalide ou refuse.')

    print('lien dans', link, '; en attente du retour sur', redirect, flush=True)
    deadline = time.time() + 900
    with HTTPServer(('127.0.0.1', a.port), H) as srv:
        srv.timeout = 20
        while 'code' not in got and time.time() < deadline: srv.handle_request()
    link.unlink(missing_ok=True)
    if 'code' not in got: raise SystemExit('delai depasse, rien change')
    flow.fetch_token(code=got['code'])
    creds = flow.credentials
    r = requests.get('https://www.googleapis.com/youtube/v3/channels', params={'part': 'id,snippet', 'mine': 'true'},
                     headers={'Authorization': 'Bearer ' + creds.token}, timeout=60)
    chans = [(c['id'], c.get('snippet', {}).get('title', '')) for c in r.json().get('items', [])] if r.ok else []
    if len(chans) != 1: raise SystemExit('chaine non verifiable ou ambigue (%d), jeton NON enregistre' % len(chans))
    expected = item.get('channel_id')
    if expected and chans[0][0] != expected: raise SystemExit('la chaine autorisee n\'est pas celle du registre, jeton NON enregistre')
    if target.exists():
        b = S / (target.stem + '-avant-%s.json' % time.strftime('%Y%m%d-%H%M%S')); shutil.copy2(target, b); b.chmod(0o600)
    target.write_text(creds.to_json(), encoding='utf-8'); os.chmod(target, 0o600)
    print('jeton enregistre pour', a.account, '; chaine:', chans[0][1], chans[0][0])
    if not expected: print('a faire : renseigner channel_id =', chans[0][0], 'dans youtube-accounts.json apres verification par Malo')


if __name__ == '__main__': main()
