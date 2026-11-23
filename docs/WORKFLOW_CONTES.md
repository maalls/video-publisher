# Workflow de production d'un conte animé (état au 23/11/2026)

Exemple chiffré : conte 6, "Le Pot qui avait fait un petit" (v1 à v3, publié le 23/11 à 18:00).
Mesuré = horodatage du journal `timing-recap.md` (script `scripts/tales/steptimer.py`). Estimé = déduit des dates de fichiers ou des habitudes, signalé comme tel. Aucune clé ni secret ici.

## Vue d'ensemble
Écriture → voix → alignement texte/voix → références visuelles → images (1 par plan) → animations (1 par plan) → montage ffmpeg + musique + sous-titres → projet YABBE (relecture/sous-titres) → carte de fin → publication (YouTube, Instagram, TikTok). Les relectures de Malo bouclent plusieurs fois (v1, v2, v3).

## Étapes, scripts et durées (conte 6)
| Étape | Script / outil | Durée v1 (mesurée) | Reprises v2 / v3 (mesurées) |
|---|---|---|---|
| Écriture narration, plans, prompts | `narration.json` (écrit par l'agent) | 13 s de saisie. La rédaction elle-même n'est pas chronométrée (estimé quelques minutes) | accroche v3 : nouveau texte |
| Voix | Gemini TTS, voix Sadaltager, une prise (outil de l'agent parent, hors hipo) | 3 min 02 | v3 : 20 min 17 (nouvelle prise + attente, pas du calcul pur) |
| Découpe en phrases | `scripts/tales/split_narration.py` | 2 s | 2 s |
| Transcription des mots | Whisper medium, CPU (`faster-whisper`) | 2 min 07 | 2 min 12 (v3b) |
| Alignement sous-titres (max 2 lignes) | `scripts/tales/align_subtitles.py`, `realign_subtitles_global.py` | 3 min 12 (1er essai en erreur : chunk de plus de 2 lignes, corrigé) | 2 min 17 |
| Références (personnages, décor) | `conte06-references.py`, ComfyUI | 12 min 46 | non refaites |
| Images (10 plans) | `conte06-images*.py`, ComfyUI, Qwen-Image-Edit 2511 fp8 | 30 min (borne du chronomètre, voir note) | v2 réparations 15 min 01, v3 25 min 45, v4 plan 5 29 min 31 |
| Animations (10 plans) | `conte06-anims*.py`, ComfyUI, Wan 2.2 TI2V 5B fp16 | 33 min 46 | v2 13 min, v3 21 min 46 + 8 min |
| Montage | `conte06-montage.py` : ffmpeg, musique CC BY (Kevin MacLeod), sous-titres incrustés, intro 1 s | 11 min 05 | v2 4 min 58, v3 10 min 44 |
| Projet YABBE | `scripts/tales/yabbe_project.py` (API locale YABBE) | 5 s | retour à la ligne des sous-titres 0 s |
| Carte de fin voix + CTA | `scripts/tales/end_card.py` | inclus dans le montage (non chronométré à part) | idem |
| Publication | voir ci-dessous | non chronométré (estimé 15 min de préparation, le jour même) | |

Totaux mesurés : travail machine/agent 4 h 30, attente de relecture ou blocage 21 min (conte 6, toutes versions).
Horodatage : première étape 22/11 21:28, master v3 prêt 23/11 02:24, soit environ 5 h de bout en bout.

## Notes de mesure
- Les durées ComfyUI par plan sont mesurées à ±15 s près : le script lit `/history` toutes les 15 s, et l'écart entre le workflow et le reçu donne 180 s par image et 195 s par animation (multiples de 15 s, très réguliers). Correction : une première version de ce document les présentait comme des bornes de sondage à 180/195 s, ce qui était faux.
- "images 30 min 00 s" = 10 images x 180 s. Une image prend donc environ 3 min, une animation 3 min 15 (mesuré, pas estimé). Les plans de 285 à 720 s sont des relances réelles.
- Une partie du temps total est de l'itération (plans refusés : plan 5, plan 3, plan 9) et non de la production nominale. Une production sans reprise serait d'environ 1 h 30 à 2 h (estimé : références 13, images 30, animations 34, montage 11, voix et alignement 8).
- Les étapes voix-v3 et whisper-prise-v3 sont mal bornées (étapes restées ouvertes dans le chronomètre) : durées gonflées.

## Publication
- YouTube : `scripts/tales/upload_youtube_scheduled.py`, envoi privé avec `--publish-at`, YouTube publie lui-même à l'heure. Journal anti-doublon.
- Instagram (@les1001contes) : `scripts/tales/instagram_unified.py` (plan, create, publish). Fichier AAC 112k faststart, cover 9:16, URL temporaire (serveur local + tunnel Cloudflare) pour que Meta récupère le média, publication à l'heure par un processus hipo.
- TikTok : `scripts/upload_tiktok_inbox.py` envoie un brouillon dans la boîte de réception. Malo finalise dans l'app et colle la légende. Point d'attention : le dossier de l'URL privée doit être `state/tiktok-private-pending` (le défaut `secrets/tiktok-pending` n'est pas inscriptible, c'est ce qui a fait échouer l'envoi de 18:00 le 23/11 avant tout octet envoyé).

## Ce qui peut être automatisé davantage
1. Un seul lanceur par conte au lieu de scripts `conteNN-*.py` copiés et modifiés (références, images, animations, montage lisent un `conte.json`).
2. Attente ComfyUI plus fine (sondage 2 s au lieu de 15 s, fait dans le lanceur ; WebSocket non installé).
3. Chronométrage automatique : chaque script appelle `steptimer` (plus d'étapes ouvertes ou saisies à la main).
4. Contrôle qualité automatique avant relecture : visage/mains, cohérence personnage (comparaison aux références), planche contact pour revue rapide.
5. Alignement : règle des 2 lignes intégrée au découpage pour éviter l'erreur du premier essai.
6. Publication : corriger le dossier TikTok par défaut dans le code, un seul script `publish_conte.py` qui prépare les trois plateformes depuis un `publication.json` (titre, légende, heure) et vérifie les hash.
7. Cover, dérivé Instagram et textes de publication générés par le script de montage.
8. Garder en Git les scripts de production de chaque conte (aujourd'hui sous `var/`, ignoré).
