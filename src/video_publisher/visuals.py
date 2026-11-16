import math
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from .core import french_date

BG = (16, 23, 42)
WHITE = (247, 241, 224)
GOLD = (223, 190, 116)


def font(size: int, bold: bool = False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    variable = "FONT_BOLD_PATH" if bold else "FONT_PATH"
    path = os.path.expanduser(os.environ.get(variable, "").strip())
    return ImageFont.truetype(path or name, size)


def centered(draw, y, text, face, fill=WHITE):
    box = draw.textbbox((0, 0), text, font=face)
    draw.text(((1080-(box[2]-box[0]))/2, y), text, font=face, fill=fill)


def lines_for(draw, text, face, width):
    lines = []; current = ""
    for word in text.split():
        candidate = (current + " " + word).strip()
        if draw.textlength(candidate, font=face) > width and current:
            lines.append(current); current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def card(item: dict, index: int, day, target: Path, demo=False):
    image = Image.new("RGB", (1080, 1920), BG)
    draw = ImageDraw.Draw(image)
    # Marge droite et bas libres pour les commandes des lecteurs verticaux.
    centered(draw, 200, "HOROSCOPE", font(31, True), GOLD)
    centered(draw, 255, french_date(day), font(30))
    cx, cy, r = 540, 710, 230
    draw.ellipse((cx-r, cy-r, cx+r, cy+r), outline=GOLD, width=3)
    for n in range(12):
        a = n*math.pi/6
        x, y = cx+math.sin(a)*r, cy-math.cos(a)*r
        draw.ellipse((x-6,y-6,x+6,y+6), fill=GOLD)
    # Numéro de signe plutôt que glyphes dépendants d'une police non fournie.
    centered(draw, 620, f"{index+1:02}", font(125), GOLD)
    centered(draw, 1010, item["sign"], font(64, True))
    # Sous-titre synchronisé par segment, intégré à l'image finale.
    face = font(42)
    lines = lines_for(draw, item["text"], face, 790)
    if len(lines) > 4:
        raise ValueError("Texte trop long pour le template")
    for n, line in enumerate(lines):
        centered(draw, 1180+n*64, line, face)
    draw.line((140, 1550, 940, 1550), fill=(60, 69, 86), width=2)
    draw.line((140, 1550, 140+int(800*(index+1)/12), 1550), fill=GOLD, width=5)
    centered(draw, 1610, "Pour le plaisir, pas une prédiction certaine.", font(24), (165, 176, 195))
    if demo:
        centered(draw, 1680, "DÉMO SANS VOIX", font(26, True), GOLD)
    image.save(target)


def thumbnail(day, target: Path):
    image = Image.new("RGB", (1080, 1920), BG)
    draw = ImageDraw.Draw(image)
    centered(draw, 440, "HOROSCOPE", font(82, True), GOLD)
    centered(draw, 640, "Les 12 signes", font(62))
    centered(draw, 790, french_date(day), font(35))
    centered(draw, 1270, "Ton rendez-vous quotidien", font(35), GOLD)
    image.save(target)
