"""Offline building blocks for encrypted state; not connected to any workflow.

A store must implement compare-and-swap (CAS), never a blind overwrite. Unknown
write results require human reconciliation. This module performs no network I/O.
"""
from copy import deepcopy
import json
from cryptography.fernet import Fernet, InvalidToken


class StateError(RuntimeError):
    pass


class StateCodec:
    def __init__(self, key):
        try:
            self.cipher = Fernet(key)
        except (ValueError, TypeError):
            raise StateError("Clé d'état invalide; aucune opération") from None

    def encode(self, state):
        self.validate(state)
        data = json.dumps(state, ensure_ascii=False, sort_keys=True).encode()
        return self.cipher.encrypt(data)

    def decode(self, data):
        try:
            state = json.loads(self.cipher.decrypt(data))
        except (InvalidToken, ValueError, TypeError, UnicodeError):
            raise StateError("État privé illisible; arrêt sans envoi") from None
        self.validate(state)
        return state

    @staticmethod
    def validate(state):
        if not isinstance(state, dict) or state.get("version") != 1:
            raise StateError("Version d'état non reconnue")
        if not isinstance(state.get("operations"), dict) or not isinstance(state.get("tokens"), dict):
            raise StateError("Structure d'état non reconnue")


def empty_state():
    return {"version": 1, "operations": {}, "tokens": {}}


class StateSession:
    """A single loaded revision; every mutation must be durably acknowledged.

    store.read() returns (encrypted_bytes, revision). Missing state is an error,
    not an invitation to reinitialize; bootstrap is a separate explicit action.
    store.cas(expected_revision, encrypted_bytes) returns the new revision only
    after confirmed persistence, or raises. A poisoned session cannot continue.
    """
    def __init__(self, store, codec):
        self.store, self.codec = store, codec
        self.poisoned = False
        try:
            data, self.revision = store.read()
            if not self.revision:
                raise StateError("Révision manquante")
            self.state = codec.decode(data)
        except Exception:
            raise StateError("État durable indisponible; arrêt sans envoi") from None

    def _commit(self, updated):
        if self.poisoned:
            raise StateError("Session incertaine; intervention requise")
        try:
            revision = self.store.cas(self.revision, self.codec.encode(updated))
            if not revision:
                raise StateError("Écriture non confirmée")
        except Exception:
            self.poisoned = True
            raise StateError("Écriture durable non confirmée; arrêt sans nouvel envoi") from None
        self.state, self.revision = updated, revision

    def claim(self, operation, binding):
        """Persist before any side effect. Existing intent always blocks replay."""
        if not isinstance(operation, str) or not operation:
            raise StateError("Identifiant d'opération requis")
        if operation in self.state["operations"]:
            raise StateError("Opération déjà réservée; vérifier le résultat sans renvoyer")
        if not isinstance(binding, dict) or not all(binding.get(k) for k in ("date", "platform", "account", "sha256")):
            raise StateError("Liaison date/plateforme/compte/fichier requise")
        updated = deepcopy(self.state)
        updated["operations"][operation] = {"binding": deepcopy(binding), "status": "intent"}
        self._commit(updated)

    def record(self, operation, status, receipt):
        if status not in {"accepted", "complete", "failed", "uncertain"}:
            raise StateError("Statut non reconnu")
        if operation not in self.state["operations"]:
            raise StateError("Intention durable absente")
        updated = deepcopy(self.state)
        updated["operations"][operation].update(status=status, receipt=deepcopy(receipt))
        self._commit(updated)

    def set_grant(self, grant):
        if not isinstance(grant, dict) or not grant:
            raise StateError("Accord explicite requis")
        updated = deepcopy(self.state)
        updated["grant"] = deepcopy(grant)
        self._commit(updated)

    def begin_refresh(self, platform):
        updated = deepcopy(self.state)
        refreshes = updated.setdefault("refreshes", {})
        if refreshes.get(platform) == "intent":
            raise StateError("Refresh antérieur incertain; réautorisation requise")
        refreshes[platform] = "intent"
        self._commit(updated)

    def replace_token(self, platform, expected_account, token):
        """Persist every returned refresh token before continuing the job."""
        if platform not in {"youtube", "tiktok"} or not expected_account:
            raise StateError("Compte cible requis")
        if not isinstance(token, dict) or not token.get("refresh_token"):
            raise StateError("Jeton incomplet")
        previous = self.state["tokens"].get(platform)
        if previous and previous.get("account") != expected_account:
            raise StateError("Compte OAuth différent; remplacement refusé")
        updated = deepcopy(self.state)
        updated["tokens"][platform] = {"account": expected_account, "value": deepcopy(token)}
        updated.setdefault("refreshes", {})[platform] = "complete"
        self._commit(updated)


class GitHubStateStore:
    """Treat one encrypted blob on an existing dedicated branch as data only.

    Never creates a missing branch or missing file. The caller must explicitly
    bootstrap outside this adapter. No request is retried, including reads.
    """
    def __init__(self, repository, token, branch="main", session=None):
        import re
        import requests
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise StateError("Dépôt d'état invalide")
        if branch != "main" or not token:
            raise StateError("Branche main et accès requis")
        self.repo_url = "https://api.github.com/repos/" + repository
        self.url = self.repo_url + "/contents/state.enc"
        self.branch = branch
        self.http = session if session is not None else requests.Session()
        self.headers = {"Authorization": "Bearer " + token,
                        "Accept": "application/vnd.github+json",
                        "Content-Type": "application/json"}

    def _require_private(self):
        try:
            response = self.http.get(self.repo_url, headers=self.headers, timeout=30, allow_redirects=False)
            if response.status_code != 200 or response.json().get("private") is not True:
                raise StateError("Dépôt privé requis")
        except Exception:
            raise StateError("Confidentialité du dépôt non vérifiable; arrêt") from None

    def read(self):
        self._require_private()
        import base64
        import binascii
        try:
            response = self.http.get(self.url, params={"ref": self.branch},
                                     headers=self.headers, timeout=30, allow_redirects=False)
            if response.status_code != 200:
                raise StateError("Lecture refusée")
            data = response.json()
            if data.get("type") != "file" or data.get("encoding") != "base64":
                raise StateError("Format inattendu")
            if not 0 < data.get("size", 0) <= 500_000:
                raise StateError("Taille inattendue")
            content = base64.b64decode("".join(data["content"].split()), validate=True)
            if len(content) != data["size"] or not data.get("sha"):
                raise StateError("État incomplet")
            return content, data["sha"]
        except Exception:
            raise StateError("État durable indisponible; aucun envoi") from None

    def cas(self, expected_revision, data):
        self._require_private()
        import base64
        import hashlib
        if not expected_revision or not isinstance(data, bytes) or not 0 < len(data) <= 500_000:
            raise StateError("Mise à jour d'état invalide")
        # Git blob SHA verifies the returned revision refers to these exact bytes.
        expected_blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        try:
            response = self.http.put(self.url, headers=self.headers, timeout=30,
                                     allow_redirects=False, json={
                                         "message": "Update encrypted state [skip ci]",
                                         "content": base64.b64encode(data).decode(),
                                         "sha": expected_revision, "branch": self.branch})
            if response.status_code != 200:
                raise StateError("Écriture refusée ou incertaine")
            revision = response.json()["content"]["sha"]
            if revision != expected_blob:
                raise StateError("Révision non confirmée")
            return revision
        except Exception:
            raise StateError("Écriture durable non confirmée; intervention requise") from None
