# video-publisher

Outils Python pour produire et publier des vidéos verticales avec des IA. Le dépôt
contient deux pipelines :

1. **Les 1001 Contes** (pipeline principal, actif) : un conte du monde entier devient
   une vidéo animée d'environ 1 min 30 (voix, images, animations, sous-titres,
   musique), publiée sur YouTube, Instagram et TikTok.
2. **Horoscope quotidien** (starter historique, non activé) : 12 signes dans un MP4
   1080 x 1920, publié sur YouTube. Voir [docs/HOROSCOPE.md](docs/HOROSCOPE.md).

Rien n'est publié sans une validation humaine explicite. Le lanceur des contes
s'arrête toujours avant la publication.

## Documentation

| Page | Contenu |
| --- | --- |
| [docs/WORKFLOW_AUTOMATIQUE.md](docs/WORKFLOW_AUTOMATIQUE.md) | Le flux d'exécution d'un conte, de bout en bout, étape par étape |
| [docs/LANCEUR_CONTES.md](docs/LANCEUR_CONTES.md) | Commandes du lanceur, étapes, contrôle qualité, publication |
| [docs/conte.example.json](docs/conte.example.json) | Modèle de fichier `conte.json` |
| [docs/WORKFLOW_CONTES.md](docs/WORKFLOW_CONTES.md) | Exemple chiffré d'une production (conte 6, état du 23/11/2026) |
| [docs/TIKTOK_INBOX.md](docs/TIKTOK_INBOX.md) | Envoi de brouillons TikTok |
| [docs/HIPO_LAYOUT.md](docs/HIPO_LAYOUT.md) | Organisation des dossiers sur la machine de production |
| [docs/DEPLOIEMENT.md](docs/DEPLOIEMENT.md), [docs/DURABLE_STATE.md](docs/DURABLE_STATE.md) | Déploiement et état durable (pipeline horoscope) |

## Installation

Le pipeline des contes tourne sur une machine Linux avec carte graphique. Il ne
tourne pas sur GitHub Actions : les modèles d'image et d'animation sont locaux.

### 1. Prérequis système

- Linux, Python 3.11 ou plus récent, Git.
- FFmpeg et ffprobe, police DejaVu Sans (sous-titres et cartes).
- Un GPU compatible avec ComfyUI (les modèles ci-dessous tiennent en fp8/fp16 sur
  une carte grand public récente).
- Un tunnel `cloudflared` (publication Instagram, voir plus bas) si tu publies sur
  Instagram.

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg fonts-dejavu-core python3-venv git
git clone https://github.com/maalls/video-publisher.git
cd video-publisher
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -v
```

Pour reproduire exactement l'environnement de production, installe
`requirements-production.lock` à la place de `requirements.txt`.

### 2. ComfyUI et modèles

Les images et animations passent par un serveur ComfyUI local (par défaut
`http://127.0.0.1:8188`, variable `COMFY_API`).

- Images et références : **Qwen-Image-Edit** (variante fp8).
- Animation : **Wan 2.2 TI2V 5B** (fp16), workflow modèle dans
  `scripts/tales/templates/wan22_i2v.workflow.json`.
- Les sorties de ComfyUI sont lues dans `COMFY_OUTPUT` (dossier `output` de ComfyUI).

Installe ComfyUI et télécharge les modèles depuis leurs sources officielles, en
respectant leurs licences. Ils ne sont pas dans ce dépôt.

### 3. Sous-titres : Whisper

L'alignement des sous-titres utilise `faster-whisper` (modèle medium, CPU) dans un
environnement Python séparé, indiqué par `WHISPER_PY`.

```bash
python3 -m venv ~/whisper-venv
~/whisper-venv/bin/pip install faster-whisper
export WHISPER_PY=~/whisper-venv/bin/python
```

### 4. Voix : Gemini TTS

La voix est générée en une prise (Cloud Text-to-Speech, modèle Gemini TTS, voix
**Sadaltager** en français). Il faut un compte de service Google Cloud autorisé pour
Text-to-Speech, ou un fichier de clé API pour l'API Gemini (`GEMINI_TTS_KEY_FILE`).
Le lanceur refuse un fichier d'identifiants lisible par d'autres utilisateurs.
Aucun identifiant ne va dans Git : le dossier de travail `var/` et `secrets/` sont
ignorés.

### 5. Publication (facultatif)

Chaque plateforme a son propre accès, créé une fois par le propriétaire du compte :

- **YouTube** : client OAuth "application de bureau", puis
  `python scripts/authorize_youtube.py` sur un ordinateur avec navigateur.
- **Instagram** : compte professionnel relié à une app Meta (API Instagram avec
  connexion Instagram). Le fichier vidéo doit être servi par une URL publique
  pendant la création : le script démarre un mini-serveur local et un tunnel
  `cloudflared` temporaires.
- **TikTok** : envoi en brouillon dans la boîte de réception, à finaliser dans
  l'application. Voir [docs/TIKTOK_INBOX.md](docs/TIKTOK_INBOX.md).

### 6. Musique

Les contes utilisent des morceaux Creative Commons (Kevin MacLeod, incompetech.com,
licence CC BY 4.0). Le crédit et la mention "musique raccourcie" sont ajoutés
automatiquement dans les légendes. Respecte la licence de tout autre morceau.

## Produire un conte (résumé)

```bash
# 1. Créer var/project/tales/productions/<id>/conte.json (modèle : docs/conte.example.json)
python3 scripts/tales/launcher.py check var/project/tales/productions/<id>
python3 scripts/tales/launcher.py run   var/project/tales/productions/<id> --dry-run
python3 scripts/tales/launcher.py run   var/project/tales/productions/<id> --version v1
# 2. Relire la vidéo, corriger un plan au besoin : --redo <plan>
# 3. Après le feu vert humain :
python3 scripts/tales/launcher.py approve var/project/tales/productions/<id> --evidence "..."
python3 scripts/tales/publish_conte.py var/project/tales/productions/<id> --at AAAA-MM-JJTHH:MM
```

Le détail de chaque étape est dans
[docs/WORKFLOW_AUTOMATIQUE.md](docs/WORKFLOW_AUTOMATIQUE.md).

## Structure

```text
scripts/tales/        pipeline des contes
  launcher.py         lanceur unique : check, run, status, approve
  gemini_tts.py       voix, une prise
  cut_take.py         découpe de la prise en un fichier par phrase (Whisper)
  split_narration.py  découpe du texte en phrases
  comfy_client.py     client ComfyUI (soumission unique, reçus, reprise)
  align_subtitles.py  alignement mot à mot des sous-titres
  montage_generic.py  montage ffmpeg, musique, sous-titres, carte de fin
  end_card.py         carte de fin "Les 1001 Contes"
  steptimer.py        chronométrage automatique des étapes
  publish_conte.py    publication YouTube, Instagram, TikTok (brouillon)
  upload_youtube_scheduled.py, instagram_unified.py, tiktok_inbox_send.py
  templates/          workflow ComfyUI d'animation
src/video_publisher/  pipeline horoscope (historique)
scripts/              OAuth, état durable, outils horoscope et statistiques
docs/                 documentation
tests/                tests unitaires
var/                  données réelles et secrets locaux, ignorés par Git
```

## Garde-fous

- Pas de publication sans `approve` (empreinte sha256 du master) puis
  `--execute --go-evidence` avec la citation du feu vert humain.
- Chaque publication a un journal anti-doublon. En cas d'état incertain, on lit
  le journal et la plateforme avant tout nouvel envoi.
- Les secrets (clés, jetons, fichiers OAuth) ne sont jamais écrits dans les
  journaux, les rapports ni Git.
- La mention "créé avec l'aide de l'IA" est ajoutée à chaque publication.

## Licence et droits

Les images, animations et voix sont générées par IA. Vérifie les licences des
modèles utilisés et des musiques avant toute diffusion.
