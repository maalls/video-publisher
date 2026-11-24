# Workflow automatique d'un conte, de bout en bout

Cette page explique, dans l'ordre, ce qui se passe entre l'idée d'un conte et sa
publication. Elle ne donne aucune durée : l'objectif est de comprendre le flux. Les
commandes sont dans [LANCEUR_CONTES.md](LANCEUR_CONTES.md).

## Vue d'ensemble

```text
idée -> conte.json -> check -> voix -> split -> références -> images -> animations
     -> sous-titres -> montage -> contrôle qualité -> ARRÊT (relecture humaine)
     -> approve -> publication (YouTube, Instagram, TikTok brouillon) -> vérification
```

Le lanceur (`scripts/tales/launcher.py`) enchaîne les étapes techniques et
**s'arrête toujours à la validation**. La publication est un second programme
(`publish_conte.py`) qui ne démarre qu'après un feu vert humain enregistré.

Ce qui est manuel : choisir et écrire le conte, relire, décider des corrections,
valider et choisir le jour et l'heure. Tout le reste est automatique.

## Les dossiers

Chaque conte vit dans `var/project/tales/productions/<id>/` (ignoré par Git). On y
trouve `conte.json` (la source de vérité), la voix, les reçus ComfyUI, les clips,
les sous-titres, les versions du film (`...-master-v1.mp4`, `-v2`, ...) et les
journaux. Les versions ne s'écrasent jamais : une correction produit une nouvelle
version et l'ancienne est gardée.

## Étape 0 : choisir et écrire le conte (manuel)

On choisit une histoire libre de droits ou une adaptation originale, puis on écrit
`conte.json` (modèle : [conte.example.json](conte.example.json)) :

- `narration.segments` : le texte, en phrases courtes. Chaque cause et chaque
  conséquence doivent être dites dans le texte : le spectateur ne voit que 5 à 6
  secondes d'image par plan, l'image ne remplace pas l'explication.
- `style` : la phrase de style commune à toutes les images (dessin à la main,
  aquarelle, pas de texte dans l'image).
- `references` : les personnages (et parfois un duo) décrits une fois, avec une
  graine aléatoire fixe.
- `plans` : une liste de plans. Chaque plan a un prompt d'image, un prompt de
  mouvement, la référence qu'il utilise et les phrases qu'il illustre.
- `music` : le morceau (titre, artiste, fichier).
- `publication` : titre, légende, hashtags, description YouTube.

Règles pour les prompts d'image : un seul lieu, un nombre fixe de personnages,
deux bras par personne, pas de liquide, et ce que dit le texte doit être ce que
montre l'image. Pour un conte de nuit, la nuit doit être écrite explicitement dans
les prompts des plans qui utilisent une référence "duo", sinon l'image tend vers
un décor de jour.

## Étape 1 : `check`

Le lanceur valide `conte.json` sans rien lancer : champs obligatoires, plans qui
couvrent toutes les phrases sans trou ni recouvrement, références connues, fichier
de musique présent. Une erreur arrête tout avant le premier calcul.

`run --dry-run` va plus loin : il construit tous les workflows ComfyUI dans un
sous-dossier, sans aucun appel au serveur ni à ffmpeg.

## Étape 2 : voix

Si `voix/voix-NN.wav` n'existe pas, le lanceur génère **une seule prise** pour tout
le texte (Gemini TTS, voix Sadaltager en français, consignes de style lentes avec
des pauses dans `narration.voice_instructions`). Une seule prise donne une voix
homogène du début à la fin.

Ensuite `cut_take.py` transcrit la prise avec Whisper et la découpe en un fichier
par phrase. Si la prise est tronquée (des mots manquent), elle est refaite
automatiquement, jusqu'à 3 essais. Une narration "complète" (`narration-complete.wav`)
est assemblée plus tard, au montage. La voix d'une version est réutilisée telle
quelle dans les versions suivantes.

## Étape 3 : split

`split_narration.py` découpe le texte en phrases numérotées. Ces numéros sont ce que
les plans désignent avec `phrases: [début, fin]`.

## Étape 4 : références visuelles

Pour chaque personnage de `references`, ComfyUI (Qwen-Image-Edit) génère une image
de référence. Le choix est écrit dans `references-chosen.json` (la première image
par défaut, modifiable avant l'étape suivante). Ces références servent à garder le
même visage, les mêmes vêtements et le même style d'un plan à l'autre.

## Étape 5 : images, un plan à la fois

Pour chaque plan, le lanceur construit un workflow ComfyUI (prompt du plan + style
commun + référence du plan + graine) et le soumet.

Le client ComfyUI (`comfy_client.py`) est conçu pour ne jamais soumettre deux fois :
chaque élément a un reçu `*.receipt.json` écrit à la soumission. En cas de coupure
ou de relance, un élément déjà soumis est repris, pas recommencé. L'attente
interroge l'historique du serveur toutes les 2 secondes. Le reçu garde la durée
réelle.

Une image déjà faite n'est pas refaite lors d'une nouvelle version.

## Étape 6 : animations

Chaque image devient un clip d'environ 5 secondes avec Wan 2.2 TI2V 5B
(`templates/wan22_i2v.workflow.json`), guidé par le prompt de mouvement du plan.
Même mécanisme de reçus et de reprise. Si un plan dure plus longtemps que son clip
(la voix qui l'accompagne est plus longue), le montage ralentit le clip pour couvrir
la durée : le mouvement paraît alors plus lent.

## Étape 7 : sous-titres

`align_subtitles.py` fait **une seule passe Whisper** (modèle medium, CPU) sur la
narration complète, avec les horodatages de chaque mot. Puis il aligne les phrases
connues du texte sur les mots entendus, phrase par phrase, dans une fenêtre bornée
pour qu'une erreur locale ne se propage pas. Les sous-titres sont découpés en
morceaux de 2 lignes au plus (52 caractères au total, 30 par ligne par défaut) et
affichés à partir du vrai premier mot. Si le début d'une phrase n'est pas entendu
dans l'audio (mots manquants dans la voix), l'étape échoue avec un message clair :
il faut refaire la prise.

Le résultat est `subtitle-events.json`, l'ancien fichier est gardé une fois.

## Étape 8 : montage

`montage_generic.py` assemble avec ffmpeg, en 704 x 832 :

1. un court plan d'intro ;
2. les clips d'animation de chaque plan, calés sur la durée de leurs phrases, avec
   des fondus ;
3. la narration complète, avec une pause laissée entre les phrases ;
4. la musique (raccourcie, volume baissé sous la voix, fondu d'entrée et de sortie) ;
5. les sous-titres incrustés (police DejaVu Sans, contour sombre) ;
6. une carte de fin "Les 1001 Contes" avec un appel à suivre, dit à voix haute
   (`end_card.py`) ;
7. les sorties : `<id>-master-<version>.mp4` et une version allégée pour WhatsApp.

## Étape 9 : contrôle qualité

Contrôles automatiques : résolution, codecs (h264 + aac), durée entre 45 et 180 s,
taille du fichier, sous-titres (2 lignes au plus, pas de trou de plus de 4 s), audio
audible, crédit musique présent. Une planche contact `planche-contact.jpg` est
produite pour la relecture visuelle.

Ces contrôles ne voient pas tout : visages, mains en trop, incohérence entre ce que
dit le texte et ce que montre l'image, prononciation d'un nom propre. Un humain
(ou l'agent qui regarde la planche) relit.

## Étape 10 : arrêt et relecture

Le lanceur écrit `awaiting-validation.json` (nom du master et empreinte sha256) et
s'arrête. La personne qui valide regarde la vidéo et répond de l'une de ces façons :

- **valider** ;
- **corriger** : `launcher.py run <dossier> --redo <plan>` refait l'image et
  l'animation du seul plan fautif, puis refait sous-titres, montage et contrôle.
  Le résultat est une nouvelle version (`v2`, `v3`...). Les sauvegardes du
  `conte.json` précédent et des versions antérieures sont conservées ;
- modifier le découpage des plans dans `conte.json` (par exemple scinder un plan en
  deux) et relancer : seuls les plans nouveaux ou modifiés sont calculés.

## Étape 11 : `approve`

```text
launcher.py approve <dossier> --evidence "<citation du feu vert>"
```

`approve` fige le fichier validé : il écrit `approved.json` avec le nom du master, sa
taille et son empreinte sha256, et la preuve du feu vert (qui l'a donné, quand).
Toute modification du fichier après coup change l'empreinte et bloque la
publication.

## Étape 12 : publication (`publish_conte.py`)

Sans `--execute`, le programme affiche seulement un plan : plateformes, heure, texte
de la légende. Avec `--execute --go-evidence "<citation>"`, il agit. Il refuse si
`approved.json` manque ou ne correspond pas au fichier, si l'heure est dans le passé,
ou s'il n'y a pas de preuve de feu vert. Les textes sont générés depuis
`conte.json` et complétés automatiquement par la mention IA, le crédit de la
musique et sa licence.

- **YouTube** : `upload_youtube_scheduled.py` envoie la vidéo en privé avec une
  date de publication (`publishAt`). YouTube la rend publique lui-même à l'heure.
  Un journal anti-doublon est écrit avant l'envoi.
- **Instagram** : le programme crée une version adaptée (audio AAC, démarrage
  rapide) et une couverture 9:16, démarre un mini-serveur et un tunnel temporaires
  pour que Meta puisse télécharger le fichier, crée le conteneur de Reel, attend
  qu'il soit prêt, puis un processus détaché publie à l'heure exacte. Un conteneur
  expire au bout de 24 heures : on l'arme donc le jour même ou la veille, pas plus
  tôt. Le tunnel et le serveur doivent rester actifs jusqu'à la publication.
- **TikTok** : à l'heure prévue plus 10 secondes, la vidéo part en **brouillon**
  dans la boîte de réception TikTok. La personne la finalise dans l'application
  (légende, publication).

## Étape 13 : vérification et nettoyage

Après l'heure : on vérifie que la vidéo YouTube est publique, que le Reel est publié
et que le brouillon TikTok est arrivé, en lisant les journaux et les plateformes.
Puis `publish_conte.py <dossier> --cleanup` arrête le serveur et le tunnel
temporaires et supprime les médias temporaires.

## Reprises et sécurité

- Les reçus ComfyUI et les journaux de publication empêchent les doublons. En cas
  d'état incertain (réseau coupé pendant un envoi), on lit le journal et la
  plateforme avant de relancer.
- Chaque étape est chronométrée automatiquement (`steptimer.py`) dans
  `timing.jsonl` et `timing-recap.md`.
- Les versions précédentes ne sont jamais écrasées.
- Les secrets ne sont pas dans Git et ne sont jamais écrits dans les journaux.

## Ce qui n'est pas encore automatisé

- Le choix du conte et l'écriture de `conte.json`.
- L'écoute de la voix (prononciation des noms propres) : pas de contrôle automatique.
- Un contrôle automatique par vision des images (personnes en trop, membres
  déformés, cohérence avec le texte) : proposé, pas codé.
- Un test automatique de clarté de la narration (les causes et conséquences sont-elles
  dites ?) : proposé, pas codé.
- La finalisation TikTok (brouillon à publier dans l'application).
