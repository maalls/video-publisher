"""Manual TikTok Upload/inbox prototype, never Direct Post or a cron task."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlsplit

import requests

API = "https://open.tiktokapis.com/v2/"
REDIRECT = "http://127.0.0.1:8765/callback/"
SCOPES = {"user.info.basic", "video.upload"}
PENDING_DIR = Path("secrets/tiktok-pending")


class TikTokError(RuntimeError):
    pass


def private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tiktok-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def post_json(route, token, payload):
    try:
        response = requests.post(API + route, json=payload,
                                 headers={"Authorization": "Bearer " + token},
                                 timeout=60, allow_redirects=False)
        body = response.json()
    except (requests.RequestException, ValueError):
        raise TikTokError("Réponse TikTok incertaine; ne pas renvoyer le fichier") from None
    code = body.get("error", {}).get("code", "invalid_response")
    if response.status_code != 200 or code != "ok":
        # Only known-safe machine codes, never provider prose, tokens or URLs.
        safe = code if isinstance(code, str) and re.fullmatch(r"[a-z_]{1,80}", code) else "invalid_response"
        raise TikTokError("TikTok a refusé la demande : " + safe)
    return body["data"]


def store_token(path, data, expected_open_id=None):
    if not SCOPES.issubset(set(data.get("scope", "").split(","))):
        raise TikTokError("Les permissions user.info.basic et video.upload sont requises")
    if not all(data.get(key) for key in ("access_token", "refresh_token", "open_id")):
        raise TikTokError("Réponse OAuth incomplète")
    if expected_open_id and data["open_id"] != expected_open_id:
        raise TikTokError("Le compte OAuth a changé; aucune donnée enregistrée")
    now = time.time()
    data = {**data, "expires_at": now + int(data["expires_in"]),
            "refresh_expires_at": now + int(data["refresh_expires_in"])}
    private_json(path, data)
    return data


def token_request(client, parameters):
    try:
        response = requests.post(API + "oauth/token/", data={**client, **parameters},
                                 timeout=60, allow_redirects=False)
        body = response.json()
    except (requests.RequestException, ValueError):
        raise TikTokError("Échange OAuth incertain; réponse non affichée") from None
    if response.status_code != 200 or body.get("error"):
        raise TikTokError("OAuth TikTok refusé; vérifier la configuration et les scopes")
    return body


def load_token(client_path, token_path, *, before_refresh=None):
    token = read_json(token_path)
    if time.time() + 120 >= token.get("expires_at", 0):
        if time.time() >= token.get("refresh_expires_at", 0):
            raise TikTokError("Autorisation expirée; relancer authorize_tiktok.py")
        if before_refresh:
            before_refresh()
        updated = token_request(read_json(client_path),
                                {"grant_type": "refresh_token", "refresh_token": token["refresh_token"]})
        token = store_token(token_path, updated, token["open_id"])
    return token


def user_info(token):
    try:
        response = requests.get(API + "user/info/", params={"fields": "open_id,display_name"},
                                headers={"Authorization": "Bearer " + token["access_token"]},
                                timeout=60, allow_redirects=False)
        data = response.json()
    except (requests.RequestException, ValueError):
        raise TikTokError("Identité TikTok non vérifiable") from None
    if response.status_code != 200 or data.get("error", {}).get("code") != "ok":
        raise TikTokError("Identité TikTok non vérifiable")
    user = data["data"]["user"]
    if user.get("open_id") != token["open_id"]:
        raise TikTokError("Identité TikTok différente du jeton")
    return user


def upload_url_allowed(value):
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        recognized = host in {"open-upload.tiktokapis.com", "open-upload-i18n.tiktokapis.com"} or bool(
            re.fullmatch(r"upload\.[a-z0-9](?:[a-z0-9-]{0,14}[a-z0-9])?\.tiktokapis\.com", host))
        return (parts.scheme == "https" and recognized
                and parts.port in (None, 443) and not parts.username and not parts.password
                and not parts.fragment)
    except ValueError:
        return False


def file_digest(video):
    digest = hashlib.sha256()
    with Path(video).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def upload_inbox(video, token, journal, *, explicit_consent=False, persist_receipt=None):
    video, journal = Path(video), Path(journal)
    if not explicit_consent:
        raise ValueError("Consentement à cette vidéo et ce compte requis")
    size = video.stat().st_size
    if video.suffix.lower() != ".mp4" or not 0 < size <= 64_000_000:
        raise ValueError("Prototype limité aux fichiers MP4 de 64 Mo maximum")
    journal.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive intent: an interrupted or ambiguous upload is not repeated.
    receipt = {"status": "started", "open_id": token["open_id"], "sha256": file_digest(video)}
    fd = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(receipt, stream)
    if persist_receipt:
        persist_receipt(receipt)
    data = post_json("post/publish/inbox/video/init/", token["access_token"], {
        "source_info": {"source": "FILE_UPLOAD", "video_size": size,
                        "chunk_size": size, "total_chunk_count": 1}})
    receipt.update(status="initialized", publish_id=data["publish_id"], transfer_attempted=False)
    private_json(journal, receipt)
    if persist_receipt:
        persist_receipt(receipt)
    # Signed upload URL is a credential. Never put it in state/artifacts/logs.
    private_json(pending_path(journal), {
        "upload_url": data["upload_url"], "expires_at": time.time() + 3540,
        "open_id": token["open_id"], "sha256": receipt["sha256"],
        "publish_id": receipt["publish_id"]})
    return transfer_pending(video, token, journal, persist_receipt=persist_receipt)


def pending_path(journal):
    key = hashlib.sha256(str(Path(journal).resolve()).encode()).hexdigest()
    return PENDING_DIR / (key + ".json")


def cleanup_expired_pending():
    """Cleanup runs locally whenever this prototype is used, never logs secrets."""
    if not PENDING_DIR.exists():
        return
    for path in PENDING_DIR.glob("*.json"):
        try:
            record = read_json(path)
            if time.time() >= record["expires_at"]:
                path.unlink()
        except (ValueError, KeyError, TypeError):
            # Corrupt secret files need local inspection, not printing.
            continue


def resume_pending(video, token, journal, *, explicit_consent=False):
    if not explicit_consent:
        raise ValueError("Consentement explicite à la reprise requis")
    receipt = read_json(journal)
    if receipt.get("transfer_attempted") is not False:
        raise TikTokError("Reprise interdite : un PUT a pu être tenté ou état inconnu")
    if receipt.get("open_id") != token["open_id"] or receipt.get("sha256") != file_digest(video):
        raise TikTokError("Compte ou fichier différent; reprise refusée")
    status = check_status(token, journal)
    current = read_json(journal)
    if status != "PROCESSING_UPLOAD" or current.get("uploaded_bytes") != 0:
        raise TikTokError("Reprise refusée : zéro octet frais et PROCESSING_UPLOAD requis")
    return transfer_pending(Path(video), token, Path(journal))


def transfer_pending(video, token, journal, *, persist_receipt=None):
    secret_file = pending_path(journal)
    if not secret_file.is_file():
        raise TikTokError("URL privée non conservée pour cette ancienne tentative; aucune nouvelle init créée")
    pending, receipt = read_json(secret_file), read_json(journal)
    if any(pending.get(key) != receipt.get(key) for key in ("open_id", "sha256", "publish_id")):
        raise TikTokError("Reprise privée incompatible avec le journal")
    if receipt.get("open_id") != token["open_id"] or receipt.get("sha256") != file_digest(video):
        raise TikTokError("Compte ou fichier différent; aucun transfert")
    if receipt.get("transfer_attempted") is not False:
        raise TikTokError("PUT déjà tenté ou état inconnu; aucun renvoi")
    if time.time() >= pending["expires_at"]:
        secret_file.unlink()
        raise TikTokError("URL de transfert expirée; aucune nouvelle init créée")
    url = pending["upload_url"]
    if not upload_url_allowed(url):
        try:
            host = urlsplit(url).hostname or "invalide"
        except ValueError:
            host = "invalide"
        safe_host = host if re.fullmatch(r"[a-zA-Z0-9.-]{1,253}", host) else "invalide"
        raise TikTokError("Hôte de transfert TikTok non reconnu (" + safe_host + "); aucun fichier envoyé")
    # Exclusive per-init PUT intent, in addition to the persistent safe journal.
    marker = secret_file.with_suffix(".put-reservation")
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    receipt["transfer_attempted"] = True
    private_json(journal, receipt)
    if persist_receipt:
        persist_receipt(receipt)
    size = video.stat().st_size
    try:
        with video.open("rb") as stream:
            response = requests.put(url, data=stream, headers={
                "Content-Type": "video/mp4", "Content-Length": str(size),
                "Content-Range": f"bytes 0-{size-1}/{size}"}, timeout=180, allow_redirects=False)
    except requests.RequestException:
        raise TikTokError("Transfert incertain; utiliser --status, ne pas renvoyer") from None
    finally:
        # Even ambiguous PUTs must not be retried from the credential file.
        secret_file.unlink(missing_ok=True)
    if response.status_code != 201:
        raise TikTokError("Transfert non confirmé complet; utiliser --status, ne pas renvoyer")
    status = check_status(token, journal)
    if persist_receipt:
        persist_receipt(read_json(journal))
    return status


def check_status(token, journal):
    receipt = read_json(journal)
    if receipt["open_id"] != token["open_id"]:
        raise TikTokError("Ce journal appartient à un autre compte")
    if not receipt.get("publish_id"):
        raise TikTokError("Initialisation incertaine sans publish_id; vérifier TikTok avant toute reprise")
    data = post_json("post/publish/status/fetch/", token["access_token"],
                     {"publish_id": receipt["publish_id"]})
    status = data.get("status", "UNKNOWN")
    # Do not store expiring upload URLs or arbitrary provider messages.
    safe = {key: value for key, value in receipt.items() if key != "uploaded_bytes"}
    safe["status"] = status
    if isinstance(data.get("uploaded_bytes"), int):
        safe["uploaded_bytes"] = data["uploaded_bytes"]
    private_json(journal, safe)
    return status


def retry_empty_journal(token, old_journal, video):
    """Prepare a separate attempt only after the creator's explicit decision."""
    import uuid
    old_journal = Path(old_journal)
    previous = read_json(old_journal)
    if previous.get("open_id") != token["open_id"] or previous.get("sha256") != file_digest(video):
        raise TikTokError("La vidéo ou le compte ne correspond pas au journal précédent")
    if previous.get("transfer_attempted") is True:
        raise TikTokError("Un transfert a été tenté; reprise automatique interdite")
    status = check_status(token, old_journal)
    current = read_json(old_journal)
    if status != "PROCESSING_UPLOAD" or current.get("uploaded_bytes") != 0:
        raise TikTokError("Reprise refusée : il faut un statut PROCESSING_UPLOAD et zéro octet confirmé")
    # Keep the original intact and attach provenance to a distinct new attempt.
    journal = old_journal.with_name(old_journal.stem + "-retry-" + uuid.uuid4().hex[:12] + ".json")
    # Only one recovery can be prepared from this old initialization.
    marker = old_journal.with_suffix(".retry-reservation")
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(str(journal))
    return journal
