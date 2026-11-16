import os
import requests

url = os.environ.get("ALERT_WEBHOOK_URL", "")
if not url:
    print("Pas de webhook configuré. Consulter les notifications d'échec GitHub Actions.")
else:
    # L'URL du service n'est jamais affichée et aucun secret n'est inclus dans le corps.
    message = "Échec video-publisher. Vérifie GitHub Actions et YouTube Studio avant de relancer."
    try:
        response = requests.post(url, json={"text": message}, timeout=15)
        if not 200 <= response.status_code < 300:
            raise RuntimeError("Webhook refusé")
        print("Alerte envoyée")
    except Exception:
        print("Échec de l'alerte webhook. Utiliser les notifications GitHub Actions.")
        raise SystemExit(1)
