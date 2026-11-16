"""Materialize CI secrets without echoing them."""
import json
import os
from pathlib import Path

Path("secrets").mkdir(exist_ok=True)
for env, filename in [("GCP_TTS_CREDENTIALS_JSON", "tts-service-account.json"),
                      ("YOUTUBE_TOKEN_JSON", "youtube-token.json")]:
    value = os.environ.get(env, "").strip()
    if value:
        json.loads(value)
        path = Path("secrets") / filename
        path.write_text(value, encoding="utf-8")
        os.chmod(path, 0o600)
