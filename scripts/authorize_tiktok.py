"""Local Desktop OAuth. Never prints credentials or callback query parameters."""
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import secrets
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
import webbrowser

from video_publisher.tiktok_inbox import (LIST_SCOPE, REDIRECT, SCOPES, TikTokError, read_json,
                                          store_token, token_request)


def callback_code(path, expected_state):
    parsed = urlsplit(path)
    query = parse_qs(parsed.query)
    if parsed.path != "/callback/" or query.get("state") != [expected_state]:
        raise ValueError("Retour OAuth inattendu")
    if query.get("error") or len(query.get("code", [])) != 1:
        raise ValueError("Autorisation TikTok refusée")
    return query["code"][0]


def main():
    client = read_json("secrets/tiktok-client.json")
    if set(client) != {"client_key", "client_secret"} or not all(client.values()):
        raise ValueError("Configurer le JSON local avec client_key et client_secret")
    target = Path("secrets/tiktok-token.json")
    if target.exists() and input("Remplacer l'autorisation existante ? Tape REMPLACER : ") != "REMPLACER":
        return
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = hashlib.sha256(verifier.encode()).hexdigest()
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            try:
                code = callback_code(self.path, state)
                result["code"] = code
                message = b"Autorisation recue. Tu peux fermer cet onglet et revenir au terminal."
                self.send_response(200)
            except ValueError:
                message = b"Retour OAuth invalide ou autorisation refusee. Revenir au terminal."
                self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(message)

    params = {"client_key": client["client_key"], "response_type": "code",
              "scope": ",".join(sorted(SCOPES | {LIST_SCOPE})), "redirect_uri": REDIRECT, "state": state,
              "code_challenge": challenge, "code_challenge_method": "S256"}
    with HTTPServer(("127.0.0.1", 8765), Handler) as server:
        server.timeout = 300
        print("Le navigateur va demander ton accord. Choisis le compte Horoscope attendu.")
        if not webbrowser.open("https://www.tiktok.com/v2/auth/authorize/?" + urlencode(params)):
            raise TikTokError("Navigateur non ouvert; choisir un navigateur par défaut puis relancer")
        server.handle_request()
    if "code" not in result:
        raise TikTokError("Aucune autorisation valide reçue dans le délai; relancer")
    data = token_request(client, {"grant_type": "authorization_code", "code": result["code"],
                                 "redirect_uri": REDIRECT, "code_verifier": verifier})
    store_token(target, data)
    print("Autorisation enregistrée dans secrets/tiktok-token.json. Ne pas partager ce fichier.")


if __name__ == "__main__":
    try:
        main()
    except TikTokError as error:
        print(str(error))
        raise SystemExit(1) from None
    except Exception:
        # Do not expose HTTP requests, client credentials or browser callback.
        print("Autorisation non terminée. Vérifier sandbox, compte cible, scopes et callback local.")
        raise SystemExit(1) from None
