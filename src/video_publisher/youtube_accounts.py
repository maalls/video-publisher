"""Registre de comptes YouTube (switch entre chaines). Ne contient aucun secret :
chaque compte pointe vers un fichier de jeton place dans le dossier secrets (hors depot)."""
import json
import re
from pathlib import Path

LABEL = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")
CHANNEL = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
TOKEN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.json$")


class AccountError(ValueError):
    pass


def load_registry(path):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise AccountError("Registre de comptes illisible") from None
    accounts = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(accounts, dict) or not accounts:
        raise AccountError("Registre vide ou invalide")
    clean = {}
    for label, item in accounts.items():
        if not LABEL.match(label) or not isinstance(item, dict):
            raise AccountError("Nom de compte invalide")
        token = item.get("token_file")
        channel = item.get("channel_id")
        if not isinstance(token, str) or not TOKEN_NAME.match(token):
            raise AccountError("Fichier de jeton invalide pour %s" % label)
        if channel is not None and not CHANNEL.match(str(channel)):
            raise AccountError("Identifiant de chaine invalide pour %s" % label)
        clean[label] = {"name": str(item.get("name", label))[:80], "token_file": token, "channel_id": channel}
    default = data.get("default")
    if default is not None and default not in clean:
        raise AccountError("Compte par defaut inconnu")
    return {"default": default, "accounts": clean}


def resolve(registry, secrets_dir, label=None):
    """Retourne (label, chemin du jeton, channel_id). Refuse sans choix explicite :
    aucun compte n'est choisi par defaut pour publier."""
    if not label:
        raise AccountError("Choisir un compte explicitement (--account)")
    item = registry["accounts"].get(label)
    if item is None:
        raise AccountError("Compte inconnu : %s" % label)
    if not item["channel_id"]:
        raise AccountError("Chaine de %s pas encore verifiee : autoriser le compte puis renseigner channel_id" % label)
    token = (Path(secrets_dir) / item["token_file"]).resolve()
    if Path(secrets_dir).resolve() not in token.parents:
        raise AccountError("Jeton hors du dossier secrets")
    if not token.is_file():
        raise AccountError("Jeton absent pour %s : compte pas encore autorise" % label)
    return label, token, item["channel_id"]


def describe(registry, secrets_dir):
    rows = []
    for label, item in registry["accounts"].items():
        token = Path(secrets_dir) / item["token_file"]
        rows.append({"account": label, "name": item["name"], "channel_id": item["channel_id"],
                     "authorized": token.is_file(), "ready": token.is_file() and bool(item["channel_id"])})
    return rows
