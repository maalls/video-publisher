# Préparation du suivi durable chiffré

Ce module est une brique préparatoire. Il n'est appelé par aucun workflow ni
par le pipeline vidéo. L'appliquer n'active rien, ne crée aucune branche,
ne renouvelle aucune autorisation et n'envoie aucune vidéo.

## Stockage prévu dans un dépôt privé séparé

- Dépôt privé dédié, branche `main`, fichier fixe `state.enc`.
- Le caractère privé du dépôt est revérifié avant lecture et écriture.
- Chiffrement authentifié Fernet via la bibliothèque cryptography.
- Clé exclusivement dans un secret d'environnement Actions de production.
- Les journaux, comptes et jetons OAuth restent dans le document chiffré.
- Aucun nom de vidéo, compte ou identifiant de publication dans les noms de
  fichiers ou les messages de commit.
- Les lecteurs autorisés du dépôt voient la taille et les dates des mises à jour.
- Le dépôt de code actuel reste public; aucune visibilité n’est changée.
- Les anciens chiffrés restent dans l'historique Git. Une fuite de clé pourrait
  permettre leur lecture. Révoquer les autorisations concernées et changer la
  clé dans ce cas. Le chiffrement ne protège pas d'un workflow compromis qui
  reçoit à la fois clé et données.

Le GITHUB_TOKEN du dépôt de code ne suffit pas pour accéder à un autre dépôt.
Il faut un accès approuvé limité au seul dépôt privé avec Contents:write
(fine-grained token ou GitHub App). Garder cet accès et la clé dans les secrets
de l'environnement de production. L'expiration et le renouvellement de cet
accès doivent être prévus. Ne donner cet accès qu'au job sur code de confiance. La CI de pull requests
reste sans secrets et en lecture seule. Ne jamais exécuter le contenu de la
branche d'état. Garder les actions et dépendances de production vérifiées.

## Refus de renvoi en cas d'incertitude

L'adaptateur refuse un état absent, corrompu, trop gros ou une erreur réseau.
Il ne crée ni branche ni fichier implicitement. Une mise à jour remplace
uniquement la révision SHA attendue. Une réponse d'écriture ambiguë ou un
conflit empoisonne la session : il faut relire et réconcilier, pas réessayer
l'envoi. Le résultat d'écriture est contrôlé contre le SHA Git des octets
chiffrés exacts.

Le futur orchestrateur devra réserver une intention durable avant chaque
appel qui peut envoyer une vidéo, puis sauvegarder le résultat. Une intention
existante bloque un second envoi, même après échec. Le propriétaire devra
pouvoir lire le statut et décider d'une reprise séparée; aucune suppression
ou remise à zéro automatique.

Après un refresh OAuth, sauvegarder la réponse privée immédiatement, avant
l'opération suivante. Si la réponse au refresh est perdue, une réautorisation
peut être nécessaire. Les secrets Actions initiaux ne doivent jamais écraser
le document durable à chaque démarrage.

## Ce qui reste à intégrer avant mise en service

1. Bootstrap explicite de la branche et de l'état initial, avec consentement
   du propriétaire. Générer la clé sans l'afficher, puis la placer directement
   dans le secret Actions. Ne jamais la demander par chat.
2. Liaison du document au dépôt, à la configuration et aux comptes attendus;
   clés d'opération dérivées de date + plateforme + compte, pour interdire une
   deuxième variante du fichier le même jour.
3. Connexion de chaque intention et résultat YouTube/TikTok au stockage.
   Les deux plateformes doivent pouvoir progresser indépendamment.
4. Persistance des tokens rafraîchis et séparation des autorisations de test.
5. Opt-in quotidien borné : comptes, une vidéo par jour, heure de Paris,
   durée de validité, arrêt et plafond de coûts. Les frais TTS et le statut
   OAuth Google sont à régler avant activation.
6. Durcissement du workflow de production : branche main, environnement,
   droits minimaux, actions figées, aucune restauration d'état depuis un cache,
   aucun secret ou fichier chiffré destiné aux artefacts vidéo.
7. Test distant sans publication et réconciliation après interruption.

Aucun de ces points n'est implicitement validé par ce patch préparatoire.
