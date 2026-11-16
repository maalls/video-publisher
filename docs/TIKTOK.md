> Nouveau : un prototype **Upload/inbox** local, distinct de Direct Post, est
> disponible dans [TIKTOK_INBOX.md](TIKTOK_INBOX.md). Il transfère un MP4 après
> confirmation, pour finalisation dans l'app TikTok. L'accès sandbox et le résultat
> restent à tester. Les restrictions Direct Post décrites ci-dessous ne prouvent
> pas que l'essai Upload/inbox est impossible. Aucun cron TikTok n'est activé.

# TikTok : intégration de développement, pas de publication autonome activée

Vérification des règles le 16 novembre 2026.

Le point bloquant n'est pas seulement l'audit : les règles Direct Post excluent
un utilitaire privé qui téléverse les contenus sur ses propres comptes ou ceux de
son équipe. L'API vise un produit pour un large public de créateurs. La publication
100 % autonome prévue au départ n'est donc pas une promesse réalisable pour cette
application en l'état, même en mode privé.

Avant tout transfert, l'expérience doit notamment afficher l'aperçu et le nom du
créateur, permettre d'éditer le titre et de choisir la confidentialité sans valeur
par défaut, proposer les réglages d'interaction non cochés et recueillir le
consentement explicite pour CE contenu. La déclaration Music Usage Confirmation
et les déclarations commerciales applicables doivent être présentes.

L'adaptateur `publishers/tiktok.py` contient les appels techniques : creator_info,
initialisation FILE_UPLOAD, transfert d'une tranche, suivi de publish_id. Il est
volontairement absent de la CLI et du workflow. Ses gardes-fous ne remplacent pas
une interface, ni un audit. Aucun appel TikTok n'a été testé avec un compte réel.

Pour une app non auditée, les tests Direct Post sont SELF_ONLY et le compte doit
lui-même être privé. Le scope `video.publish` et l'autorisation OAuth du créateur
sont nécessaires. Les jetons expirent : un futur parcours OAuth/refresh reste à
implémenter, avec stockage privé. Ne pas coller un jeton durable dans le code.

## Choix recommandé pour ce starter

Télécharger `video.mp4` dans les artifacts GitHub Actions et publier manuellement
sur TikTok. Ne pas essayer de contourner la revue en automatisant l'interface web.

Si le projet devient un produit destiné à d'autres créateurs, revoir sa conformité,
construire l'interface de publication, l'auth OAuth et la gestion des autorisations,
puis demander l'audit. Une réussite de l'audit ne garantit pas un droit à publier
sans consentement propre à chaque vidéo.

Sources officielles :
- https://developers.tiktok.com/doc/content-sharing-guidelines
- https://developers.tiktok.com/doc/content-posting-api-reference-direct-post
- https://developers.tiktok.com/doc/content-posting-api-reference-query-creator-info
- https://developers.tiktok.com/doc/content-posting-api-reference-get-video-status
