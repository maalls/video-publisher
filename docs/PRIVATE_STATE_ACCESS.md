# Accès proposé au dépôt privé

Préparation seulement. Aucun bootstrap ni lancement quotidien n'est effectué
par ce document ou par le module de configuration.

## Noms retenus

- Code : maalls/video-publisher, branche main.
- État privé : maalls/video-publisher-state, branche main, fichier state.enc.
- Environnement Actions dans le dépôt DE CODE : publisher-production.
- Secret d'accès au dépôt état : VP_STATE_TOKEN.
- Secret de chiffrement : VP_STATE_KEY.

Ne jamais mettre ces valeurs dans une issue, un message, un README ou un
artefact. Ne jamais les ajouter au dépôt privé en clair non plus.

## Accès fin, sans jeton classique

Sur GitHub : profil > Settings > Developer settings > Personal access tokens
> Fine-grained tokens > Generate new token.

- Nom proposé : video-publisher-state-actions.
- Resource owner : maalls.
- Repository access : Only select repositories.
- Selected repositories : video-publisher-state seulement.
- Repository permissions : Contents, Read and write.
- Metadata reste en lecture, permission nécessaire implicite.
- Aucun accès Administration, Workflows, Secrets ou compte.
- Expiration proposée : 90 jours. Noter la date réelle affichée pour organiser
  le renouvellement avant expiration; ne pas promettre un accès permanent.

Garder la page du jeton ouverte le temps de le copier directement dans la
page Secrets GitHub. Ne jamais coller le jeton dans une conversation.

Dans maalls/video-publisher : Settings > Environments > publisher-production
(créer cet environnement si approuvé), limiter ses deployment branches à main,
puis Add environment secret, nom VP_STATE_TOKEN, valeur du jeton fin.

Ne pas ajouter le secret dans video-publisher-state : c'est le workflow du
dépôt de code qui doit y accéder. Ne pas démarrer de workflow pour vérifier.
La clé VP_STATE_KEY sera générée et transférée sans affichage pendant le
bootstrap explicite; ne pas en inventer une ou la transmettre par chat.

## Renouvellement

Avant expiration, créer un remplaçant avec les mêmes restrictions, mettre à
jour VP_STATE_TOKEN, valider lecture/écriture d'état SANS appel aux plateformes,
puis révoquer l'ancien. Une erreur d'accès arrête l'automatisation; elle ne doit
jamais provoquer une remise à zéro des journaux ou un second envoi.

Un jeton fin peut lire les dépôts publics, même si un seul dépôt privé est
sélectionné. La restriction importante est son droit d'écriture : seulement
le dépôt état sélectionné. Pour un accès court renouvelé automatiquement,
une GitHub App est une évolution possible, pas un prérequis de cette version.

## Garde-fous du futur workflow

Le workflow de production devra référencer publisher-production et uniquement
s'exécuter sur main via schedule ou workflow_dispatch. Les tests PR ne
référencent pas cet environnement et ne reçoivent ni clé ni jeton. Le
GITHUB_TOKEN du dépôt code peut rester contents:read : le jeton fin assure
l'écriture limitée au dépôt privé séparé. Aucun état n'est exécuté comme code.
Aucune clé/token n'est sauvegardée en cache ou dans les artefacts vidéo.

Sources :
https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
https://docs.github.com/en/rest/repos/contents

## Ordre du déploiement, sans activation implicite

1. Appliquer le patch regroupé, lancer les tests, commit/push du code seulement.
   Ne jamais ajouter secrets/, .env, le fichier d'accord local ou les patchs.
   La production n'est pas activée par le push.
2. Confirmer Google OAuth In production et obtenir un nouveau token local avec
   scripts/authorize_youtube.py. Cela ne vérifie pas la chaîne à lui seul.
3. Confirmer l'identifiant de chaîne YouTube et le compte TikTok exacts. Vérifier
   que l'app/token du bootstrap vise ces comptes, sans partager les tokens.
4. Créer l'environnement publisher-production limité à main et ajouter
   VP_STATE_TOKEN comme décrit plus haut. Le workflow code conserve contents:read.
5. Préparer localement un fichier d'accord sous secrets/ avec les champs suivants.
   Ce n'est pas un accord actif : remplacer les identifiants et dates réels après
   décision du propriétaire. Ne pas recopier ces exemples comme une permission.

```json
{
  "version": 1,
  "content": "daily-french-horoscope",
  "youtube_account": "IDENTIFIANT_CHAINE_CONFIRME",
  "tiktok_account": "OPEN_ID_CONFIRME",
  "starts_on": "DATE_DEBUT_CONFIRMEE",
  "expires_on": "DATE_FIN_CONFIRMEE",
  "youtube_enabled": false,
  "tiktok_enabled": false,
  "costs_confirmed": false
}
```

6. Bootstrap explicite à faire approuver, GitHub CLI connecté à maalls :

```bash
python scripts/bootstrap_private_state.py --grant-file secrets/production-grant.json --confirm-bootstrap
```

Ce script lit les tokens locaux, génère une clé dans un fichier privé exclusif,
transfère la clé à VP_STATE_KEY par stdin via GitHub CLI et écrit uniquement le
chiffré state.enc dans le dépôt privé. Il refuse de remplacer un état existant
et refuse tout accord avec envois/coûts activés. Il ne publie rien. Si GitHub CLI
n'est pas installé/connecté ou si l'environnement n'existe pas, arrêter et faire
la configuration correspondante; ne pas coller de secret dans le terminal.
Après interruption, conserver la clé locale et inspecter avant toute reprise.

7. Ajouter les autres secrets d'environnement requis au moment utile :
   TIKTOK_CLIENT_JSON, GCP_TTS_CREDENTIALS_JSON, GEMINI_API_KEY; variable
   GEMINI_MODEL. Les données OAuth rotatives viennent de l'état privé, pas d'un
   YOUTUBE_TOKEN_JSON statique de production.
8. Dans Actions, sélectionner Production quotidienne (opt-in), mode preflight.
   Cette lecture vérifie accès privé/chiffrement/structure sans refresh OAuth,
   sans génération ni upload. Elle ne prouve pas la validité live des comptes.
9. Arrêter ici avant mise en service : accord quotidien encore désactivé,
   ENABLE_PRODUCTION non défini/false. Il reste à approuver séparément les
   comptes, une vidéo par jour, la période de validité, les frais éventuels
   Gemini/TTS et les limites du parcours TikTok inbox. Aucun script ne transforme
   ce document en consentement. L'édition explicite de l'accord actif et un test
   de récupération restent à effectuer avant activation.

## Limites opérationnelles de cette version préparée

Le nouveau workflow remplace le cron historique, rendu manuel seulement, pour
éviter deux publications quotidiennes. Il démarre dans la fenêtre de 05h Paris
et programme YouTube à 07h seulement si l'heure n'est pas dépassée. TikTok utilise
Upload/inbox, jamais Direct Post : la finalisation mobile reste humaine.

La génération est réservée durablement avant Gemini/TTS. Si le runner meurt,
la prochaine exécution refuse de générer ou d'envoyer à nouveau sans examen.
Cette version privilégie l'absence de doublon à une reprise automatique.
Elle ne récupère pas automatiquement le MP4 d'un runner perdu. Une lecture du
statut et une reprise média contrôlée sont alors nécessaires, avec un correctif
ciblé si besoin; ne jamais supprimer l'état pour débloquer le travail.

Chaque destination peut aboutir même si l'autre renvoie une erreur applicative.
Une panne du stockage privé arrête tout : sans preuve durable, aucun nouvel
appel d'envoi. Les refresh OAuth ont eux aussi une intention durable; une réponse
perdue peut nécessiter une réautorisation. L'état suppose que seuls le propriétaire
et le job fiable possèdent le droit d'écriture. Un détenteur malveillant de ce
droit pourrait rejouer un ancien chiffré valide; les SHA conditionnels ne sont
pas une protection contre ce type de rollback. Ne pas réécrire l'historique.

Le mode serveur Upload/inbox automatisé n'a pas encore été testé; seul le
transfert manuel du Mac et la finalisation mobile ont réussi. Les obligations
Direct Post ne doivent pas être étendues sans preuve à Upload, mais ce test ne
prouve pas non plus l'acceptation d'un consentement Upload récurrent par TikTok.
Ne pas présenter cette préparation comme une mise en production validée.

Les coûts ne sont pas garantis nuls : TTS nécessite une facturation et peut
facturer les dépassements du quota gratuit. costs_confirmed est un verrou
explicite de configuration, pas un plafond de dépenses ni une lecture de la
facturation Google. La mise en service reste bloquée sans résolution du budget.
