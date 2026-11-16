from .core import french_date


def metadata(day, timeline):
    timestamps = "\n".join(f"{int(x['start'])//60:02}:{int(x['start'])%60:02} {x['sign']}" for x in timeline)
    return {
        "title": f"Horoscope du {french_date(day)} #Shorts",
        "description": f"Les 12 signes du jour, en français.\n\nRepères temporels :\n{timestamps}"
            "\n\nContenu de divertissement généré avec l'aide de l'IA."
            " Aucune donnée astrologique réelle n'est utilisée en v1."
            " Ni conseil médical, ni conseil financier.\n#horoscope #astrologie #shorts",
        "tags": ["horoscope", "horoscope du jour", "astrologie", "français", "Shorts"],
        "categoryId": "24",
    }
