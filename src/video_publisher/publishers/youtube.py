"""YouTube upload with local intent journal and expected-channel check."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from ..core import required, save_json

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]


def upload(video: Path, meta: dict, scheduled_at, journal: Path, private_test=False):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    if journal.exists():
        previous = json.loads(journal.read_text(encoding="utf-8"))
        if previous.get("status") == "complete":
            return previous
        raise RuntimeError("Upload précédent incertain. Vérifier YouTube Studio avant toute relance.")
    if not private_test and scheduled_at <= datetime.now(timezone.utc):
        raise ValueError("07:00 est déjà passé : aucune publication tardive automatique")
    credentials = Credentials.from_authorized_user_file(required("YOUTUBE_TOKEN_FILE"), SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    channels = youtube.channels().list(part="id", mine=True).execute()
    ids = [c["id"] for c in channels.get("items", [])]
    if ids != [required("YOUTUBE_CHANNEL_ID")]:
        raise ValueError("La chaîne OAuth ne correspond pas à YOUTUBE_CHANNEL_ID")
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": True}
    if not private_test:
        status["publishAt"] = scheduled_at.isoformat().replace("+00:00", "Z")
    # Un résultat incertain ne déclenche JAMAIS un second videos.insert automatique.
    save_json(journal, {"status": "started", "title": meta["title"],
                        "scheduled_at": None if private_test else scheduled_at.isoformat()})
    request = youtube.videos().insert(part="snippet,status", body={"snippet": meta, "status": status},
        media_body=MediaFileUpload(str(video), mimetype="video/mp4", resumable=True))
    result = None
    while result is None:
        _, result = request.next_chunk(num_retries=0)
    receipt = {"status": "uploaded", "video_id": result["id"],
               "scheduled_at": None if private_test else scheduled_at.isoformat(),
               "requested_status": status, "returned_status": result.get("status", {})}
    save_json(journal, receipt)
    # Vérification en lecture séparée : un upload accepté ne prouve pas la programmation.
    check = youtube.videos().list(part="status", id=result["id"]).execute()
    actual = check.get("items", [{}])[0].get("status", {}) if check.get("items") else {}
    confirmed = actual.get("privacyStatus") == "private"
    if not private_test:
        returned = actual.get("publishAt")
        confirmed = confirmed and bool(returned) and (
            datetime.fromisoformat(returned.replace("Z", "+00:00")) == scheduled_at)
    receipt["verified_status"] = actual
    receipt["verified"] = bool(confirmed)
    receipt["status"] = "complete" if confirmed else "uploaded"
    save_json(journal, receipt)
    if not confirmed:
        raise RuntimeError("Vidéo téléversée mais programmation/confidentialité non confirmée. Vérifier Studio, ne pas renvoyer.")
    return receipt
