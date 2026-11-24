"""OAuth TikTok lance sur hipo (sans navigateur). Ecrit le lien d'autorisation dans un fichier,
attend le retour sur 127.0.0.1:8765 (port a rediriger depuis le navigateur de Malo), puis
remplace var/project/tales/secrets/tiktok-token.json (ancienne copie gardee en -avant-). N'affiche jamais le code ni les jetons."""
import hashlib, secrets, shutil, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlencode
sys.path.insert(0, 'src'); sys.path.insert(0, 'scripts')
from authorize_tiktok import callback_code
from video_publisher.tiktok_inbox import LIST_SCOPE, REDIRECT, SCOPES, TikTokError, read_json, store_token, token_request

S = Path('var/project/tales/secrets')
LINK = Path('/tmp/tiktok-auth-link.txt')
client = read_json(S / 'tiktok-client.json')
state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
challenge = hashlib.sha256(verifier.encode()).hexdigest()
result = {}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        try:
            result['code'] = callback_code(self.path, state)
            msg, st = 'Autorisation recue. Tu peux fermer cet onglet.'.encode(), 200
        except ValueError:
            msg, st = b'Retour invalide ou refuse.', 400
        self.send_response(st); self.send_header('Content-Type', 'text/plain; charset=utf-8'); self.send_header('Cache-Control', 'no-store')
        self.end_headers(); self.wfile.write(msg)


params = {'client_key': client['client_key'], 'response_type': 'code', 'scope': ','.join(sorted(SCOPES | {LIST_SCOPE})),
          'redirect_uri': REDIRECT, 'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256'}
LINK.write_text('https://www.tiktok.com/v2/auth/authorize/?' + urlencode(params))
LINK.chmod(0o600)
deadline = time.time() + 900
with HTTPServer(('127.0.0.1', 8765), H) as srv:
    srv.timeout = 20
    print('en attente du retour', flush=True)
    while 'code' not in result and time.time() < deadline:
        srv.handle_request()
LINK.unlink(missing_ok=True)
if 'code' not in result:
    print('delai depasse, rien change'); raise SystemExit(1)
try:
    data = token_request(client, {'grant_type': 'authorization_code', 'code': result['code'], 'redirect_uri': REDIRECT, 'code_verifier': verifier})
except TikTokError as e:
    print('echec echange du code:', e); raise SystemExit(1)
target = S / 'tiktok-token.json'
if target.exists():
    b = S / ('tiktok-token-avant-%s.json' % time.strftime('%Y%m%d-%H%M%S'))
    shutil.copy2(target, b); b.chmod(0o600)
tok = store_token(target, data)
print('token enregistre; scopes:', tok.get('scope'))
