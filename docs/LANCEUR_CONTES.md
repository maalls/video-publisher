# Lanceur unique des contes animés

Un conte = un fichier `conte.json` (modèle : `docs/conte.example.json`). Plus de scripts `conteNN-*.py` à réécrire.

## Utilisation
```
cd /home/instinct/video-publisher
python3 scripts/tales/launcher.py check var/project/tales/productions/<id>          # valide conte.json
python3 scripts/tales/launcher.py run   var/project/tales/productions/<id> --dry-run # workflows construits, rien lancé
python3 scripts/tales/launcher.py run   var/project/tales/productions/<id> --version v1
python3 scripts/tales/launcher.py run   ... --redo 05-ravi          # nouvelle variante d'un plan (image + animation)
python3 scripts/tales/launcher.py approve ... --evidence "Malo 19:40: 'ok on publie'"   # après sa relecture
python3 scripts/tales/publish_conte.py  ... --at 2026-11-24T19:00                        # plan seulement
python3 scripts/tales/publish_conte.py  ... --at ... --execute --go-evidence "..."       # après son go explicite
python3 scripts/tales/publish_conte.py  ... --cleanup                                    # serveur/tunnel temporaires
```
Les longues commandes se lancent en arrière-plan (`nohup ... < /dev/null &`), comme avant.

## Étapes (dans l'ordre) et scripts
| Étape | Ce qui se passe | Script |
|---|---|---|
| check | `conte.json` complet, plans qui couvrent toutes les phrases, références connues, musique présente | `launcher.py` |
| voix | écrit `narration.json`, vérifie `voix/voix-NN.wav`. La voix (Gemini TTS Sadaltager) n'est pas générée par le lanceur : il s'arrête proprement si elle manque | `launcher.py` |
| split | découpe en phrases | `split_narration.py` |
| references | une candidate par référence (ComfyUI, Qwen-Image-Edit), choix dans `references-chosen.json` (1re par défaut, modifiable avant `images`) | `launcher.py`, `comfy_client.py` |
| images | une image par plan, avec la référence | idem |
| animations | une animation par plan (Wan 2.2 TI2V 5B), modèle de workflow `templates/wan22_i2v.workflow.json` | idem |
| sous-titres | Whisper medium (CPU) + alignement, 2 lignes max | `align_subtitles.py` |
| montage | ffmpeg : segments, fondus, sous-titres incrustés, musique, carte de fin voix + CTA | `montage_generic.py` |
| qc | contrôles automatiques (voir plus bas), planche contact | `launcher.py` |
| validation | **arrêt**. Écrit `awaiting-validation.json` (master + sha256). Malo relit | `launcher.py` |
| publication | seulement après `approve` puis `--execute --go-evidence` | `publish_conte.py` |

## Attente ComfyUI et chrono
- Chaque élément ComfyUI a un journal `*.receipt.json` : soumis une seule fois, jamais de double soumission, reprise après coupure. Le reçu contient `seconds` (durée mesurée).
- Attente : interrogation de `/history` toutes les 2 s (avant : 15 s). Ce n'est pas un événement WebSocket : la librairie n'est pas installée sur hipo. La précision est de 2 s.
- Chaque étape est chronométrée automatiquement (`steptimer.py` : `timing.jsonl`, `timing-recap.md`).

## Contrôle qualité automatique
Résolution 704x832, codecs h264+aac, durée 45 à 180 s, taille, sous-titres 2 lignes max et sans trou de plus de 4 s, audio audible, crédit musique renseigné, planche contact `planche-contact.jpg`. Il ne remplace pas la relecture (visages, cohérence des personnages, prononciation).

## Publication (`publish_conte.py`)
- Refuse sans `approved.json` valide (sha256 du master), si l'heure est passée, ou sans `--go-evidence`.
- Textes générés depuis `conte.json` : crédit musique, mention IA et licence CC BY 4.0 ajoutés automatiquement.
- YouTube : envoi privé + `publishAt`. Instagram : conteneur créé avant, publication à l'heure exacte. TikTok : brouillon dans la boîte de réception, à finaliser par Malo dans l'app.
- Correction du bug du 23/11 : le dossier des URL privées TikTok est maintenant `state/tiktok-private-pending` (variable `TIKTOK_PENDING_DIR`).

## Ce qui est testé et ce qui ne l'est pas
Testé (`tests/test_launcher.py`) : validation, dry-run sans appel ComfyUI, arrêt propre sans voix, soumission ComfyUI unique avec un faux serveur, variantes, garde-fous de publication.
Non testé de bout en bout : montage ffmpeg générique et publication réelle. Le montage reprend à l'identique la logique de `conte06-montage.py` ; la publication reprend les commandes qui ont servi au conte 6. Premier vrai test : le conte 7.

## Voix : Gemini TTS (étape voix)
- Clé : `var/project/tales/secrets/gemini-tts.json`, format `{"api_key": "..."}`. Hors Git (`/var/` est ignoré). Le fichier doit appartenir à l'utilisateur `instinct` et être en 600 (le lanceur refuse sinon). La clé passe dans l'en-tête `x-goog-api-key`, jamais dans une URL, un log ou un journal.
- Création sans passer par un chat, depuis une session sudo sur hipo :
  `sudo install -o instinct -g instinct -m 600 /dev/null /home/instinct/video-publisher/var/project/tales/secrets/gemini-tts.json` puis coller le JSON avec `sudo tee` (ou `sudo -u instinct nano ...`).
- Si `voix/voix-NN.wav` manque, le lanceur fait UNE prise (modèle `gemini-3.8-flash-tts` par défaut, surchargeable par `narration.tts_model`, voix `narration.voice` = Sadaltager, style = `narration.voice_instructions`), puis `cut_take.py` (Whisper) la coupe en un fichier par segment. Coût estimé ~0,03 $ par conte. Sans clé exploitable, il s'arrête proprement.
- Non testé avec la vraie API (pas de clé encore) : requête construite d'après la doc Google (Interactions API, `POST /v1beta/interactions`), testée contre un faux serveur.
