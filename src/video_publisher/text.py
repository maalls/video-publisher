from datetime import date
import json
from .core import SIGNS, required, validate_script


def generate(day: date) -> dict:
    from google import genai
    from google.genai import types
    schema = {
        "type": "object", "required": ["date", "horoscopes"],
        "properties": {
            "date": {"type": "string"},
            "horoscopes": {"type": "array", "minItems": 12, "maxItems": 12,
                "items": {"type": "object", "required": ["sign", "text"],
                    "properties": {"sign": {"type": "string", "enum": list(SIGNS)},
                                   "text": {"type": "string"}}}}
        }
    }
    prompt = f"""Écris un horoscope de divertissement en français pour le {day.isoformat()}.
Une phrase de 8 à 14 mots par signe, sans répéter le nom du signe dans la phrase.
Ordre exact : {', '.join(SIGNS)}. Ton chaleureux, varié, tutoiement.
Pas de prédictions certaines, conseil médical, financier ou juridique.
Pas de prétendue donnée astronomique réelle. Pas de markdown, balise ou saut de ligne
à l'intérieur des phrases. La date JSON doit être {day.isoformat()}.
Le nom du signe sera lu avant chaque phrase. Objectif : environ 75 secondes au total.
"""
    # Un seul appel applicatif, aucun fallback payant et aucune régénération automatique.
    with genai.Client(api_key=required("GEMINI_API_KEY"),
                      http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1))) as client:
        response = client.models.generate_content(
            model=required("GEMINI_MODEL"), contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json",
                                               response_schema=schema, temperature=0.8))
    if not response.text:
        raise ValueError("Gemini n'a pas retourné de texte")
    return validate_script(json.loads(response.text), day)
