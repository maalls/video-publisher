"""Run locally only. Creates a token file, never prints a refresh token."""
import argparse
import os
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from video_publisher.publishers.youtube import SCOPES

parser = argparse.ArgumentParser()
parser.add_argument("--client", type=Path, default=Path("secrets/client_secret.json"))
parser.add_argument("--output", type=Path, default=Path("secrets/youtube-token.json"))
args = parser.parse_args()
flow = InstalledAppFlow.from_client_secrets_file(str(args.client), SCOPES)
credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent", open_browser=True)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(credentials.to_json(), encoding="utf-8")
os.chmod(args.output, 0o600)
print(f"Jeton enregistré dans {args.output}. Ne pas partager ni committer ce fichier.")
