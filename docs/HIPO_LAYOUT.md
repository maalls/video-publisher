# Fichiers locaux sur hipo

Le code est dans le checkout Git. Les données réelles restent sous `var/`, ignoré par Git.

```text
video-publisher/
  src/video_publisher/                 code horoscope existant, inchangé
  scripts/tales/                      adaptateurs de publication réutilisables
  var/project/
    tales/
      productions/
        conte01-soleil-vent/
        conte02-cheval/
      state/                          reçus et états, jamais à effacer pour relancer
      secrets/                        accès privés, jamais à committer
      comfy-assets/                   copie vérifiée des images et clips sources
      legacy-code/                    scripts historiques conservés, pas encore généralisés
    horoscope/                        espace de données réservé, pas de nouvelle cadence activée
  var/backups/                        sauvegarde préalable du rangement
  var/migration/                      inventaires, empreintes et contrôles
```

Les anciens chemins de production restent disponibles par liens de compatibilité. Ils évitent de casser les scripts pendant une migration progressive. Les dossiers hérités et scripts spécifiques à un conte ne constituent pas un nouveau moteur générique.

Les adaptateurs de `scripts/tales/` sont importés sans réécriture fonctionnelle. Ils demandent toujours les mêmes paramètres et conservent leurs journaux anti-doublons. Les chemins Instagram par défaut pointent dans le projet tales du checkout, sans chemin de compte personnel en dur. Les options explicites restent prioritaires.

Les poids des modèles restent partagés avec ComfyUI. Les projets conservent une copie de leurs sources médias, pas une copie des modèles.

Une sauvegarde des fichiers lisibles a été vérifiée avant déplacement. Certains fichiers privés non lisibles par le compte de travail sont préservés intacts avec leurs propriétaires et permissions, sans prétendre avoir contrôlé leur contenu.

## Vérification sans publication

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Le rangement n'autorise aucune publication ni dépense. Un ancien `publishAt` ou un accord d'horaire annulé ne doit jamais être restauré pendant une reprise.
