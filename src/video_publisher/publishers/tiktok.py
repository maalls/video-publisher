"""Experimental low-level Direct Post adapter. NOT a compliant posting product.

Not called by the CLI or the scheduled workflow. Before calling from a future UI:
show creator nickname, preview, editable metadata, privacy with no default,
interaction controls, disclosures and Music Usage Confirmation. Obtain express
consent for THIS video. A private own-account utility is not an acceptable audited
use case. See docs/TIKTOK.md. No public publishing method is provided here.
"""
import time
from pathlib import Path
import requests

BASE = "https://open.tiktokapis.com/v2/"


class TikTokSandbox:
    def __init__(self, access_token: str):
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {access_token}"})

    def _post(self, route, payload):
        response = self.session.post(BASE+route, json=payload, timeout=60)
        if response.status_code != 200:
            raise RuntimeError(f"TikTok HTTP {response.status_code}; réponse non journalisée")
        body = response.json()
        if body.get("error", {}).get("code") != "ok":
            raise RuntimeError("TikTok a refusé la demande; vérifier scopes/compte/quota")
        return body["data"]

    def creator_info(self):
        return self._post("post/publish/creator_info/query/", {})

    def post_self_only(self, video: Path, title: str, seconds: float, *,
                       selected_privacy: str, explicit_consent: bool,
                       compliant_ui_ready: bool, journal: Path):
        from ..core import save_json
        if not compliant_ui_ready or not explicit_consent or selected_privacy != "SELF_ONLY":
            raise ValueError("Interface conforme et consentement propre à cette vidéo requis")
        if journal.exists():
            raise RuntimeError("Intent TikTok existant. Contrôler le statut, ne pas renvoyer.")
        info = self.creator_info()
        if selected_privacy not in info.get("privacy_level_options", []):
            raise ValueError("SELF_ONLY indisponible pour ce créateur")
        if seconds > info["max_video_post_duration_sec"]:
            raise ValueError("Durée supérieure à la limite du créateur")
        size = video.stat().st_size
        # Une seule tranche pour cette v1, pas de découpage arbitraire non conforme.
        if not 0 < size <= 64_000_000:
            raise ValueError("Adaptateur v1 limité aux fichiers de 64 Mo maximum")
        save_json(journal, {"status": "started"})
        data = self._post("post/publish/video/init/", {
            "post_info": {"title": title[:2200], "privacy_level": selected_privacy,
                "disable_duet": True, "disable_comment": True, "disable_stitch": True,
                "is_aigc": True},
            "source_info": {"source": "FILE_UPLOAD", "video_size": size,
                            "chunk_size": size, "total_chunk_count": 1}})
        publish_id = data["publish_id"]
        save_json(journal, {"status": "initialized", "publish_id": publish_id})
        # Ne pas transmettre le Bearer token à l'hôte de stockage upload_url.
        with video.open("rb") as stream:
            response = requests.put(data["upload_url"], data=stream, headers={
                "Content-Type": "video/mp4", "Content-Length": str(size),
                "Content-Range": f"bytes 0-{size-1}/{size}"}, timeout=180)
        if response.status_code not in (200, 201):
            raise RuntimeError("Transfert TikTok incertain; contrôler publish_id avant toute relance")
        return self.wait(publish_id, journal)

    def wait(self, publish_id: str, journal: Path):
        from ..core import save_json
        for _ in range(24):
            state = self._post("post/publish/status/fetch/", {"publish_id": publish_id})
            save_json(journal, {"publish_id": publish_id, **state})
            if state.get("status") == "PUBLISH_COMPLETE":
                return state
            if state.get("status") == "FAILED":
                raise RuntimeError("Traitement TikTok échoué; consulter le journal")
            time.sleep(10)
        raise TimeoutError("Traitement TikTok en attente. Réutiliser publish_id, ne pas republier.")
