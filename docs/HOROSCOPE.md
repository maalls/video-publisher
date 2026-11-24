# Pipeline horoscope (historique, non activé)

Cette page reprend l'ancien README du dépôt. Le pipeline principal actif est celui des contes : voir [le README](../README.md).

Starter Python pour un horoscope quotidien en français : **12 signes dans un MP4
vertical 1080 × 1920**, cible 75 s, texte Gemini, voix Google Cloud WaveNet, cartes
Pillow, montage FFmpeg et programmation YouTube à 07:00 Europe/Paris.

**État : génération et upload YouTube privé testés localement.** Le déploiement
Actions reste à valider avec tes secrets. TikTok reste manuel tant que son parcours
n'a pas été décidé. Le cron est désactivé par défaut par `ENABLE_DAILY`.
Voir [docs/DEPLOIEMENT.md](DEPLOIEMENT.md) avant toute activation.

## À lire avant d'activer

- **TikTok n'est pas automatisé.** Ses règles excluent l'utilitaire privé pour ses
  propres comptes et exigent une expérience de publication avec consentement.
  L'adaptateur SELF_ONLY est fourni pour développement seulement, sans accès depuis
  le cron. Le MP4 peut être publié manuellement. Voir [docs/TIKTOK.md](TIKTOK.md).
- Les douze repères temporels figurent dans la description. Ce ne sont **pas des
  chapitres YouTube garantis** : YouTube demande au moins 10 s par chapitre, ce qui
  est incompatible avec 12 signes en 75 s. Le starter conserve le format court et
  les repères, sans promettre l'affichage de chapitres.
- Gratuité visée au faible volume, **pas un plafond de facturation garanti**.
  TTS exige un compte de facturation actif et facture les dépassements. Son palier
  WaveNet est actuellement de 4 millions de caractères/mois. Le modèle Gemini doit
  être choisi dans le palier gratuit de ton compte AI Studio. Aucun fallback payant.
  Configure quotas et alertes de budget. Une alerte budget n'est pas un blocage.
- GitHub Actions n'offre pas un lancement exact à 05:00 : les crons peuvent être
  retardés. On utilise deux heures UTC puis on vérifie Europe/Paris (été/hiver).
  Si le runner arrive après 06:00 Paris, le cron est ignoré. Si le rendu termine
  après 07:00, aucune publication tardive n'est faite. Sur un dépôt public inactif,
  GitHub peut désactiver les crons après 60 jours. Ils tournent sur la branche par défaut.
- La miniature PNG est générée mais pas téléversée : sa sélection pour un Short
  dépend du parcours de la plateforme. Elle reste une ressource réutilisable.

## Essai local sans clé

Pré-requis : Python 3.11+, FFmpeg/ffprobe, polices DejaVu. Sur Ubuntu/Debian :

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg fonts-dejavu-core python3-venv
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
video-publisher --demo --width 270
python -m unittest discover -s tests -v
```

`--width 270` produit un aperçu rapide 270 × 480. Sans cet argument, 1080 × 1920.
Le mode démo utilise un texte d'exemple et **du silence**, pas une voix factice.
Il n'appelle aucune API et refuse `--publish-youtube`.
Sous macOS, installe FFmpeg et DejaVu séparément :

```bash
brew install ffmpeg
brew install --cask font-dejavu
```

Pillow ne trouve pas toujours les polices par leur nom seul sur macOS. Renseigne
les deux chemins dans `.env` (en adaptant le dossier si tu as choisi une
installation différente) :

```dotenv
FONT_PATH=~/Library/Fonts/DejaVuSans.ttf
FONT_BOLD_PATH=~/Library/Fonts/DejaVuSans-Bold.ttf
```

Le programme développe `~` en dossier personnel. Sous Windows, installe aussi
FFmpeg et DejaVu séparément et adapte l'activation du venv. Le workflow GitHub
utilise Linux.

Résultat dans `output/AAAA-MM-JJ-demo/` : `video.mp4`, 12 cartes PNG,
`thumbnail.png`, `subtitles.srt`, `script.json`, `timeline.json`, `metadata.json`.
Les phrases sont incrustées dans les cartes pendant leur segment vocal. Le SRT
contient une entrée par signe, pas un alignement mot à mot ni du karaoké.
La voix n'est jamais coupée : chaque segment dure au moins 6,25 s; une voix plus
longue peut faire monter le total vers 90 s. Au-delà, le pipeline s'arrête.

## Comptes et configuration

### 1. Gemini / Google AI Studio

Crée une clé API dans Google AI Studio. Vérifie la disponibilité d'un modèle dans
le palier gratuit de TON compte et renseigne `GEMINI_MODEL` (nom exact) ainsi que
`GEMINI_API_KEY`. Le modèle n'est pas figé dans le code pour ne pas imposer un nom
retiré ou payant. Aucun compte de facturation n'est nécessaire pour un palier
réellement gratuit, là où il est disponible. Les quotas et conditions de données
varient selon offre/région : vérifier la tarification actuelle.

Un seul appel de génération, avec schéma JSON et validation des 12 signes.
Le script est réutilisé si le dossier de la date existe. Une réponse invalide
fait échouer le run, sans deuxième génération automatique ni changement de modèle.

### 2. Google Cloud Text-to-Speech

Crée un projet Google Cloud, active **Cloud Text-to-Speech API** et la facturation.
Crée un compte de service dédié et accorde uniquement les permissions nécessaires
à TTS dans ce projet, pas Owner/Editor. Pour ce starter, télécharge sa clé JSON dans
`secrets/tts-service-account.json` et définis `GOOGLE_APPLICATION_CREDENTIALS`.
Si les clés de compte de service sont interdites par ton organisation, ne change
pas sa politique : passer à Workload Identity Federation est un TODO de déploiement.

La voix par défaut est `fr-FR-Wavenet-A`. Les autres familles sont refusées pour
éviter de basculer sans le vouloir sur une offre plus chère. Le compte doit avoir
accès à cette voix. Douze appels TTS, un par signe, environ 1 à 2 k caractères/jour
selon les textes. Le compte gratuit est partagé avec tes autres usages éventuels.
Pas de musique fournie. Voir [assets/README.md](../assets/README.md) pour les droits.

### 3. YouTube Data API et OAuth de la chaîne

Dans Google Cloud, active **YouTube Data API v3**, configure l'écran de consentement
OAuth, puis crée un client OAuth **application de bureau**. Ajoute ton compte aux
utilisateurs de test si l'app est en mode Testing. Télécharge le client dans
`secrets/client_secret.json`, puis lance **sur ton ordinateur** :

```bash
python scripts/authorize_youtube.py
```

Le navigateur demande l'autorisation. Choisis bien la chaîne voulue. Le jeton est
écrit dans `secrets/youtube-token.json` sans être affiché. Ne le committe jamais.
Les scopes sont `youtube.upload` et `youtube.readonly`, ce dernier servant à vérifier
la chaîne avant chaque upload. Renseigne `YOUTUBE_CHANNEL_ID` avec l'identifiant
exact `UC...` de ta chaîne (dans les paramètres avancés de YouTube).

Un service account ne remplace pas cet OAuth de chaîne. Les refresh tokens des apps
OAuth externes en Testing peuvent expirer après 7 jours pour ces scopes : traiter
la configuration de production/consentement avant de compter sur un fonctionnement
quotidien. Certaines vérifications peuvent être nécessaires selon ta configuration.

Après configuration de `.env`, fais d'abord un rendu réel **sans publication** :

```bash
video-publisher
```

Regarde et écoute le MP4. Puis configure `ENABLE_YOUTUBE=true` et fais un upload privé :

```bash
video-publisher --publish-youtube --private-test
```

Contrôle la bonne chaîne et le résultat dans YouTube Studio. Pour programmer demain :

```bash
video-publisher --date AAAA-MM-JJ --publish-youtube
```

Remplace la date par celle de demain. `publishAt` est calculé à 07:00 Paris et
converti en UTC. Le statut envoyé est `private` avec `publishAt`. L'upload test
reste privé sans `publishAt`. La vidéo est déclarée non destinée aux enfants et
comportant un contenu synthétique par prudence; vérifier que ces choix conviennent
à la chaîne avant d'activer le cron. La recette ne promet ni vues ni monétisation.

### 4. TikTok

Si tu veux étudier l'intégration, crée une app TikTok for Developers, demande le
produit Content Posting API et configure son OAuth. Mais une simple app privée
n'est pas un usage acceptable pour un audit Direct Post. Le starter ne lance pas
l'OAuth TikTok, ne renouvelle pas les tokens et ne poste rien sur TikTok. Les
contraintes et la suite à construire sont dans [docs/TIKTOK.md](TIKTOK.md).

## GitHub Actions : activation progressive

Décompresse le zip, ouvre le dossier dans VS Code, copie les fichiers dans ton dépôt
`video-publisher`, puis commit/push toi-même. Aucun accès GitHub n'est demandé ici.
Sur le dépôt public, les runners standards Actions sont gratuits selon l'offre
actuelle; ce workflow n'utilise ni runner payant ni hébergement persistant.

Dans **Settings → Secrets and variables → Actions**, crée ces **Secrets** :

| Nom exact | Valeur |
| --- | --- |
| `GEMINI_API_KEY` | Clé API AI Studio |
| `GCP_TTS_CREDENTIALS_JSON` | Contenu intégral de la clé JSON du compte de service TTS |
| `YOUTUBE_TOKEN_JSON` | Contenu intégral de `secrets/youtube-token.json`, si upload activé |
| `ALERT_WEBHOOK_URL` | Facultatif, URL d'un webhook acceptant JSON `{"text":"..."}` |

Puis ces **Variables**, qui ne sont pas des secrets :

| Nom exact | Valeur |
| --- | --- |
| `GEMINI_MODEL` | Nom exact d'un modèle gratuit disponible dans ton compte |
| `YOUTUBE_CHANNEL_ID` | Identifiant exact de la chaîne `UC...` |
| `ENABLE_DAILY` | `false` : le cron ne lance aucun job; laisser ainsi pendant les essais |
| `ENABLE_YOUTUBE` | `false` : le cron activé génère seulement; ne pas activer avant la recette publique |

`TTS_VOICE` est configurable localement; le workflow garde la voix par défaut.
Pour ajouter une musique dans Actions, il faudra committer une piste autorisée et
ajouter `MUSIC_FILE: assets/music.mp3` à l'environnement de l'étape de génération.
Aucun secret TikTok n'est nécessaire tant que l'intégration reste désactivée.

1. Laisser `ENABLE_DAILY=false` et `ENABLE_YOUTUBE=false` dans les variables Actions.
2. Onglet **Actions → Horoscope quotidien → Run workflow**, mode `demo` : aucun
   appel API, aucun upload. Télécharger et inspecter le MP4 (sans voix).
3. Mode `render` : génération réelle avec les secrets, **aucun upload**, même si
   une ancienne variable `ENABLE_YOUTUBE=true` est présente.
4. Mode `private-test` : upload YouTube privé explicite, sans `publishAt`, même
   après 07:00. Vérifier la chaîne et la vidéo dans Studio. Ce choix ne modifie
   aucune variable du dépôt et n'active pas le cron.
5. Aucun mode manuel ne programme une vidéo publique. La suite est une décision
   distincte : OAuth durable, anti-doublon durable et recette de programmation.
   Ne pas encore activer le cron public. Voir [le guide](DEPLOIEMENT.md).

Active les notifications d'échec Actions dans les réglages de notification GitHub.
Le webhook est optionnel et dépend de ton service. Son échec n'est pas masqué.
Un cron ignoré, désactivé ou jamais lancé ne peut pas envoyer d'alerte : vérifier
les premiers jours dans Actions. Aucun email ni destinataire n'est codé en dur.

## Reprises, doublons et sécurité

- Verrou de concurrence Actions; un seul run du workflow à la fois.
- Journal `state/` écrit **avant** `videos.insert`, puis reçu avec l'ID YouTube.
  En cas d'upload incertain, pas de nouvel upload automatique. Vérifier YouTube
  Studio, puis résoudre le journal manuellement. Une erreur de réseau n'est pas
  une preuve d'absence de vidéo.
- Les caches journaliers Actions conservent le journal et les médias. Ce n'est
  **pas une base transactionnelle durable** : éviction ou échec de sauvegarde peut
  perdre la protection. Ne pas effacer les caches pour relancer un upload; consulter
  Studio d'abord. Avant une exploitation sans surveillance, ajouter un stockage
  durable partagé avec réservation atomique par date et conserver les reçus.
- Ne pas lancer en parallèle localement et dans Actions : le verrou Actions ne
  protège pas deux ordinateurs. Même date + autre mode peut créer un test privé
  et une publication programmée distincts, volontairement.
- Les artifacts du dépôt public contiennent la vidéo et les textes préparés pour
  publication, pas les secrets. Vérifie leur audience si tu ajoutes du contenu privé.
- Les secrets ne sont pas imprimés; pas de token, clé, `.env` ni dossier `secrets/`
  dans le zip. Des dépendances sont bornées mais pas verrouillées au hash : faire un
  lockfile et épingler les actions à leurs SHA avant un déploiement durci.

## Structure

```text
src/video_publisher/
  cli.py              orchestration et modes sûrs
  core.py             validation JSON, date française, DST, écritures atomiques
  text.py             Gemini, réponse structurée
  audio.py            Google Cloud WaveNet ou silence de démo
  visuals.py          cartes réutilisables + miniature
  render.py           FFmpeg, sous-titres, musique optionnelle
  metadata.py         titre, description, repères et tags
  publishers/
    youtube.py        OAuth, vérification chaîne, journal, publishAt
    tiktok.py         adaptateur technique SELF_ONLY non activé
scripts/              OAuth local, secrets CI, garde horaire et alerte
.github/workflows/    pipeline quotidien et tests
```

## TODO avant exploitation quotidienne

- Valider les trois services Google dans Actions, quotas et chaîne (le test local
  ne suffit pas à valider le runner).
- Choisir le modèle gratuit Gemini et écouter la voix française retenue.
- Vérifier les mentions IA, audience, droits de diffusion et licences musique.
- Traiter l'expiration OAuth, puis ajouter une persistance anti-doublon durable.
- Si TikTok doit être automatisé, revoir le produit et sa conformité plutôt que
  considérer l'audit comme une simple formalité.
- V2 : données astro réelles, alignement précis des mots, transitions, identité
  graphique et tests d'intégration en environnement séparé.

## Sources des contraintes (consultées le 16 novembre 2026)

- Gemini / tarification : https://ai.google.dev/gemini-api/docs/pricing
- JSON Gemini : https://ai.google.dev/gemini-api/docs/structured-output
- TTS / facturation et WaveNet : https://cloud.google.com/text-to-speech/pricing
- Upload YouTube : https://developers.google.com/youtube/v3/docs/videos/insert
- OAuth et jetons : https://developers.google.com/identity/protocols/oauth2
- Chapitres : https://support.google.com/youtube/answer/9884579?hl=en
- Runners Actions : https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- Cron Actions : https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- TikTok : https://developers.tiktok.com/doc/content-sharing-guidelines

Les tarifs, modèles et règles peuvent changer. Pas de garantie de gratuité future.
