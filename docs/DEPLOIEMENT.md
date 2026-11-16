# Déployer par étapes, sans publication surprise

État vérifié le 16 novembre 2026. Ce correctif prépare les essais Actions. Il
n'active rien : ne change pas les variables du dépôt en appliquant un patch.

## 1. Garder le quotidien désactivé

Dans le dépôt GitHub, **Settings → Secrets and variables → Actions → Variables** :

- `ENABLE_DAILY=false` : le cron ne lance aucun job, même si les secrets existent.
- `ENABLE_YOUTUBE=false` : protection supplémentaire pour le futur cron.

Ces variables sont distinctes du `.env` sur le Mac. Le `.env` peut garder
`ENABLE_YOUTUBE=true` pour tes essais locaux privés. Il ne doit jamais être poussé.
Le correctif doit être poussé sur la branche par défaut pour protéger le cron.
Avant cela, l'ancien workflow peut encore lancer la génération à 05:00 Paris.

Après le patch, les modes sont :

| Déclenchement | Réglage | Résultat |
| --- | --- | --- |
| Manuel | `demo` | Exemple et silence, aucune API, aucun upload |
| Manuel | `render` | Gemini et TTS, MP4 réel, aucun upload |
| Manuel | `private-test` | MP4 réel et upload YouTube privé, jamais programmé |
| Cron | `ENABLE_DAILY` absent ou `false` | Aucun job de génération |
| Cron | `ENABLE_DAILY=true`, `ENABLE_YOUTUBE=false` | Génération réelle seulement |
| Cron | Les deux à `true` | Programmation YouTube à 07:00 Paris, après recette distincte |

Le cron reste aux heures UTC 03:00 et 04:00, avec garde Europe/Paris : une seule
fenêtre 05:00–05:59 acceptée par jour. Le passage été/hiver est géré par Python.
GitHub peut retarder ou perdre un déclenchement; ce n'est pas une garantie à 05:00.
Après 07:00, le code refuse la programmation du jour. Ne pas activer pour l'instant.

## 2. Préparer les essais Actions

Ne jamais mettre les clés ou JSON dans une issue, un commentaire ou un message.
Renseigner directement les Secrets Actions, pas les Variables :

- `GEMINI_API_KEY` : même clé qu'au test local.
- `GCP_TTS_CREDENTIALS_JSON` : contenu du JSON TTS local valide.
- `YOUTUBE_TOKEN_JSON` : contenu du JSON OAuth de la chaîne, pour `private-test`.

Variables non secrètes : `GEMINI_MODEL` (même modèle gratuit validé localement),
`YOUTUBE_CHANNEL_ID` (la chaîne `UC...` testée), et les deux interrupteurs à `false`.
Ne pas copier les chemins macOS des polices : Actions installe DejaVu sous Linux.

Dans **Actions → Horoscope quotidien → Run workflow**, tester successivement :

1. `demo`, puis télécharger l'artifact et regarder le MP4.
2. `render`, puis vérifier la voix, les cartes et le timing.
3. `private-test`, puis vérifier dans Studio la bonne chaîne et le statut privé.

Le test privé peut se faire dans la journée, sans attendre le lendemain.
Le journal refuse un deuxième upload privé pour la même date s'il est présent.
Une relance n'est pas une consigne d'effacer les caches : consulter Studio d'abord.
Les artifacts de ce dépôt public ne sont pas un espace de stockage confidentiel.

## 3. Résoudre OAuth avant un fonctionnement durable

Dans Google Cloud → Google Auth Platform → Audience, vérifier le statut :

- **Testing, audience External** : avec nos scopes YouTube, le refresh token expire
  après 7 jours. Un essai réussi aujourd'hui ne règle pas ce problème.
- **In production** : ce statut est distinct d'une vérification OAuth. Google prévoit
  une exemption de vérification pour une app à usage personnel de moins de 100
  utilisateurs, avec les avertissements d'app non vérifiée applicables.

Si le statut est changé après décision, refaire l'autorisation sur le Mac avec
`python scripts/authorize_youtube.py`, puis remplacer le Secret Actions
`YOUTUBE_TOKEN_JSON` avec le nouveau fichier, jamais dans le dépôt. Aucun jeton
n'est garanti éternel : révocation, quotas d'émission et autres causes existent.

La documentation YouTube `videos.insert` consultée indique actuellement que les
uploads des projets API non vérifiés ne sont pas limités au privé. Ne pas confondre
ce point avec les règles OAuth, et ne pas en déduire que la programmation publique
a déjà été testée sur cette chaîne. Elle ne l'a pas été dans cette recette.

## 4. Ce qui reste avant le cron YouTube public

- Accord explicite sur l'activation et sur la première date de diffusion.
- OAuth durable configuré, nouveaux secrets testés dans Actions, quotas contrôlés.
- Stockage anti-doublon durable à ajouter : les caches Actions actuels peuvent être
  évincés; ils ne suffisent pas à promettre une exploitation sans surveillance.
- Essai de programmation publique convenu, confirmation dans Studio du bon horaire,
  de la bonne chaîne, puis du résultat après l'heure de diffusion.
- Notifications d'échec activées et vérification des premiers jours. Un cron absent
  ne produit pas lui-même une alerte; GitHub peut aussi le désactiver après 60 jours
  sans activité du dépôt public.

Ne pas activer `ENABLE_DAILY=true` et `ENABLE_YOUTUBE=true` avant ces étapes.
Le patch conserve la limitation connue de persistance; il ne la masque pas.

## 5. TikTok : choix distinct

Le même `video.mp4` peut être récupéré dans l'artifact pour une publication manuelle
sur TikTok, si ce fonctionnement est retenu. Aucun accès TikTok n'est nécessaire
pour préparer le MP4. Aucun transfert ni publication TikTok n'est déclenché ici.

Direct Post n'est pas une bonne base pour cet utilitaire personnel : les règles
excluent ce cas et demandent aperçu, choix et consentement avant envoi. Le mode non
audité impose aussi SELF_ONLY et un compte privé. L'API Upload vers la boîte de
réception exige une app approuvée pour `video.upload` et l'autorisation du créateur;
elle oblige ensuite à terminer la publication dans TikTok. Ce n'est pas une
solution de publication autonome ni une garantie d'approbation de cette app.

Voir [TIKTOK.md](TIKTOK.md). Ne pas automatiser le navigateur pour contourner cela.

## Sources officielles consultées

- OAuth, expiration : https://developers.google.com/identity/protocols/oauth2
- Exemption usage personnel : https://support.google.com/cloud/answer/13464323?hl=en
- Upload YouTube : https://developers.google.com/youtube/data/reference/rest/v3/videos/insert
- Retards Actions : https://docs.github.com/en/actions/how-tos/troubleshoot-workflows
- Désactivation Actions : https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows
- TikTok Direct Post : https://developers.tiktok.com/docs/en/content-sharing-guidelines
- TikTok Upload : https://developers.tiktok.com/doc/content-posting-api-get-started-upload-content
