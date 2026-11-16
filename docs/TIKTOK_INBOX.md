# Prototype TikTok Upload/inbox, essai local uniquement

Ce prototype utilise `video.upload`, pas Direct Post ni `video.publish`. Il envoie
un MP4 dans la boîte de réception TikTok pour que tu le vérifies, l'édites et
termines la publication dans l'app. Il ne programme rien et n'est pas relié au
workflow quotidien, à `ENABLE_YOUTUBE` ou à la CLI `video-publisher`.

## Accès sandbox : ce qui reste à tester

Le sandbox permet des essais sans revue, pour les comptes cibles ajoutés. Le scope
`video.upload` doit être disponible ET accordé par OAuth. Sa présence à l'écran ne
prouve pas que l'appel de transfert sera accepté. La documentation sandbox exclut
la Content Posting API pour les vidéos publiques sans préciser tous les effets
sur la finalisation manuelle d'un envoi inbox. Ce test doit donc vérifier la
notification et le parcours dans l'app, sans promettre le résultat ni un usage
quotidien durable. Une revue production reste un autre sujet.

Ne pas appliquer à Upload les restrictions SELF_ONLY/compte privé documentées pour
Direct Post. N'active pas Direct Post et ne change pas la confidentialité globale
de ton compte personnel pour ce test. Le compte cible doit être celui Horoscope.

## Configuration sur le portail

Dans le sandbox de l'app :

1. Ajouter Login Kit et Content Posting API, scopes `user.info.basic` et
   `video.upload` seulement pour ce prototype.
2. Dans Login Kit, configurer la plateforme Desktop et le Redirect URI exact :
   `http://127.0.0.1:8765/callback/` (avec le slash final).
3. Dans Sandbox settings → Target users → Add account, connecter le compte TikTok
   Horoscope. L'apparition peut prendre jusqu'à une heure. Apply changes si proposé.

Si le portail exige d'autres champs ou refuse ce callback, s'arrêter et inspecter
les champs exacts avant de remplir. Ne pas inventer de site ou politique de
confidentialité et ne pas publier de clé.

## Configuration sur le Mac

Dans `secrets/` (déjà exclu de Git), créer localement `tiktok-client.json` :

```json
{
  "client_key": "VALEUR_SANDBOX_LOCALE",
  "client_secret": "VALEUR_SANDBOX_LOCALE"
}
```

Remplacer ces valeurs uniquement dans le fichier local avec les identifiants du
sandbox, pas de la production. Ne pas envoyer ce JSON en message/issue, ne pas le
committer ni le mettre dans un artifact. Le garder privé; sur macOS :

```bash
chmod 600 secrets/tiktok-client.json
python scripts/authorize_tiktok.py
```

Le navigateur ouvre la connexion et le consentement TikTok. Choisir le compte
Horoscope et accepter les deux scopes. Le script attend au maximum 5 minutes le
retour local et vérifie l'état anti-CSRF; PKCE Desktop utilise SHA256 en hex comme
indiqué par TikTok. Ne pas copier l'URL de retour dans un message : elle contient
un code d'autorisation. Si le navigateur ne s'ouvre pas, le configurer par défaut
sur le Mac puis relancer, sans afficher les paramètres d'autorisation.

Le jeton est écrit en mode 0600 dans `secrets/tiktok-token.json`, jamais affiché.
Le refresh conserve le nouveau refresh token atomiquement, vérifie le compte et
utilise les durées renvoyées par TikTok, sans coder une durée fixe en dur. Une
erreur réseau au refresh peut nécessiter une nouvelle autorisation : pas de
rotation aveugle en boucle. Tout reste local pour cet essai.

## Une vidéo, avec vérification avant envoi

Ouvrir le MP4 généré dans QuickTime. Puis lancer avec le chemin réel du fichier :

```bash
python scripts/upload_tiktok_inbox.py output/AAAA-MM-JJ-live/video.mp4
```

La commande affiche le nom du profil (pas nécessairement unique), son `open_id`,
le chemin complet et le journal, puis demande de taper `ENVOYER`. Avant de le faire,
vérifier que le navigateur a autorisé le bon compte, que le MP4 est le bon et que
tu veux transférer cette vidéo précise à ce compte. Sinon annuler. Un transfert
est réel, même si ce n'est pas encore une publication publique.

Le prototype prend uniquement un MP4 de 64 Mo maximum, envoyé directement avec
FILE_UPLOAD. Pas de lien d'hébergement, aucune conversion ou publication cachée.
Il ne détecte pas encore toutes les incompatibilités codec/durée : le MP4 du
pipeline doit avoir été contrôlé et TikTok peut encore le refuser.

Limites documentées : 6 initialisations par minute par jeton, au plus 5 partages en
attente sur 24 h, URL de transfert valable une heure. Le script n'essaie jamais de
contourner ces limites. Il ne retente pas automatiquement un transfert incertain.

## Comprendre le résultat

- `SEND_TO_USER_INBOX` : notification envoyée, **pas vidéo publiée**. Ouvrir la
  notification dans TikTok, vérifier la vidéo et choisir titre, visibilité,
  interactions et mentions nécessaires (contenu IA, droits musique, contenu
  commercial s'il s'applique), puis décider soi-même de publier ou non.
- `PUBLISH_COMPLETE` : le suivi TikTok dit que la publication s'est terminée
  depuis son parcours d'édition; ce script ne promet pas une visibilité précise.
- Échec ou attente : conserver le journal, ne pas renvoyer aveuglément. Un journal
  sans `publish_id` signifie une initialisation incertaine, pas une absence prouvée
  de transfert.

Pour reprendre UNIQUEMENT la lecture du statut, utiliser le chemin exact du
journal affiché, sans supprimer de fichier :

```bash
python scripts/upload_tiktok_inbox.py --status state/NOM-DU-JOURNAL.json
```

Le journal associe compte et empreinte SHA256 du fichier, avec création exclusive
avant le premier appel. Une deuxième tentative du même fichier au même compte est
bloquée. Cela n'est pas une protection contre la suppression du journal, une autre
copie du poste ou un autre fichier exporté. Aucun stockage durable partagé n'est
fourni. Pas de cron tant que l'accès, les jetons et ce parcours ne sont pas validés.

## Sources consultées le 16 novembre 2026

- https://developers.tiktok.com/doc/add-a-sandbox/
- https://developers.tiktok.com/doc/login-kit-desktop/
- https://developers.tiktok.com/doc/oauth-user-access-token-management/
- https://developers.tiktok.com/doc/oauth-user-access-token-management
- https://developers.tiktok.com/doc/tiktok-api-v2-get-user-info/
- https://developers.tiktok.com/doc/content-posting-api-get-started-upload-content
- https://developers.tiktok.com/doc/content-posting-api-reference-upload-video
- https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide
- https://developers.tiktok.com/doc/content-posting-api-reference-get-video-status

Certaines variantes de la page OAuth présentent des durées contradictoires; le
prototype utilise donc exclusivement `expires_in`/`refresh_expires_in` de la réponse
réelle et conserve le nouveau refresh token à chaque renouvellement.


## Correctif des serveurs et reprise avant PUT

L'hôte exact `open-upload-i18n.tiktokapis.com` a été observé dans la réponse
TikTok de l'essai local. Il est ajouté explicitement, pas par un joker général.
Les autres formes acceptées sont `open-upload.tiktokapis.com` et
`upload.<région>.tiktokapis.com` montrées par les exemples officiels. HTTPS/443,
absence de credentials/fragment dans l'URL et refus de redirection restent requis.
Le Bearer OAuth ne part jamais vers le serveur de stockage.

Pour les NOUVELLES initialisations, l'URL signée est gardée uniquement dans
`secrets/tiktok-pending/`, fichier mode 0600, jamais affichée et jamais écrite dans
`state/`. Ce dossier est couvert par `secrets/` dans `.gitignore`; le workflow
n'inclut pas `secrets/` dans les artifacts et ne lance pas ce prototype. Ne jamais
joindre ce dossier à une issue, archive, artifact ou message. L'URL est un secret.

Validité locale maximale 59 minutes (marge sous l'heure TikTok). Le fichier est
supprimé après tout PUT, même incertain, et les fichiers expirés sont purgés à la
prochaine utilisation du script. Si on abandonne le test sans relancer le script,
les fichiers peuvent rester sur disque après expiration mais ne permettent plus
une reprise valide; on peut supprimer le dossier `secrets/tiktok-pending/` pour
retirer ces credentials temporaires, sans supprimer aucun journal de `state/`.

Si une FUTURE init est bloquée avant PUT, le script conserve cette URL privée.
Après examen et accord, `--resume CHEMIN_DU_JOURNAL` avec le MP4 permet de reprendre
la même init : même compte et empreinte, URL non expirée, `transfer_attempted=false`,
zéro octet fraîchement confirmé et saisie ENVOYER. Aucune nouvelle init. Un verrou
exclusif par init marque l'intention PUT; après PUT tenté ou incertain, le renvoi
est interdit, même si un statut ultérieur indiquait zéro. Lire `--status` seulement.

Les deux anciennes tentatives de cet incident n'avaient pas conservé leurs URLs.
Ce correctif ne peut pas les recréer : `--resume` les refusera, sans nouvelle init.
Conserver leurs journaux. Toute éventuelle nouvelle tentative doit passer par la
reprise explicite `--retry-empty` déjà documentée, après lecture fraîche et décision,
pas en supprimant un journal ou en répétant aveuglément la commande.
