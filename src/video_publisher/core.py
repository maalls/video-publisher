from __future__ import annotations
import json
import os
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
SIGNS = ("Bélier", "Taureau", "Gémeaux", "Cancer", "Lion", "Vierge",
         "Balance", "Scorpion", "Sagittaire", "Capricorne", "Verseau", "Poissons")
MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
          "septembre", "octobre", "novembre", "décembre")
WEEKDAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def french_date(day: date) -> str:
    return f"{WEEKDAYS[day.weekday()]} {day.day} {MONTHS[day.month-1]} {day.year}"


def publish_time(day: date) -> datetime:
    return datetime.combine(day, time(7), PARIS).astimezone(timezone.utc)


def schedule_due(now: datetime) -> bool:
    if now.tzinfo is None:
        raise ValueError("Timezone required")
    # Deux crons UTC, une seule fenêtre Paris. Le décalage DST est calculé.
    local = now.astimezone(PARIS)
    return local.hour == 5


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Configuration manquante : {name}")
    return value


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def validate_script(data: dict, day: date) -> dict:
    if data.get("date") != day.isoformat():
        raise ValueError("Date du script incorrecte")
    items = data.get("horoscopes", [])
    if len(items) != 12 or [x.get("sign") for x in items] != list(SIGNS):
        raise ValueError("Les 12 signes doivent être présents, une fois et dans l'ordre")
    for item in items:
        text = item.get("text", "")
        if not isinstance(text, str) or not 8 <= len(text.split()) <= 14:
            raise ValueError("Chaque horoscope doit contenir 8 à 14 mots")
        if any(c in text for c in "\n\r<>{}\\"):
            raise ValueError("Caractère de contrôle ou balise dans le texte")
    return data


def demo_script(day: date) -> dict:
    lines = [
        "Ose un petit changement et garde du temps pour tes proches aujourd'hui.",
        "Avance à ton rythme, une conversation sincère peut éclairer ta journée.",
        "Tes idées méritent une pause avant de choisir ta prochaine direction.",
        "Écoute tes envies et offre une attention simple à quelqu'un aujourd'hui.",
        "Partage ton énergie sans oublier de prendre un moment pour toi.",
        "Allège ton programme et concentre ton attention sur une seule priorité.",
        "Une pause tranquille peut t'aider à retrouver ton équilibre ce matin.",
        "Exprime tes besoins avec douceur et laisse une place aux surprises.",
        "Explore une idée nouvelle sans te précipiter vers une décision importante.",
        "Reconnais tes progrès et accorde du temps aux plaisirs les plus simples.",
        "Fais confiance à ta créativité pour imaginer une journée un peu différente.",
        "Prends une respiration et choisis ce qui nourrit vraiment ton calme intérieur.",
    ]
    return validate_script({"date": day.isoformat(), "horoscopes": [
        {"sign": sign, "text": text} for sign, text in zip(SIGNS, lines)]}, day)
