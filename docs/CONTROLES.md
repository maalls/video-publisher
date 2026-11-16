# Contrôles du starter

16 novembre 2026, Python 3.12.

- Installation dans un environnement Python isolé : réussie.
- 20 tests unitaires : réussis. Validation des signes/date/longueur, UTC été/hiver,
  jours de transition DST, garde horaire, métadonnées, écritures atomiques, refus
  d'upload démo, garde TikTok, chaîne OAuth incorrecte, journal de reprise, paramètres
  d'upload privé et programmé, vérification finale YouTube avec réponses simulées.
- Compilation Python de tous les modules et scripts : réussie.
- Démo complète sans compte et sans réseau : 12 signes, MP4 H.264 + AAC,
  1080 × 1920, durée 75,022 secondes. Son volontairement silencieux en mode démo.
- Aperçu réduit 270 × 480 : réussi.
- Inspection visuelle : première et dernière images du MP4, miniature et planche
  des 12 signes. Accents lisibles, texte sans débordement, date cohérente.

Non testé : authentification réelle et appels Gemini, Google Cloud TTS, OAuth et
publication YouTube, transfert TikTok; exécution du workflow sur le dépôt GitHub.
Les tests d'adaptateurs utilisent des réponses simulées, pas des comptes réels.
La qualité de la voix et le temps de rendu sur un runner GitHub restent à mesurer.
Les couleurs, polices, marges et sous-titres restent à valider avec toi.

Aucune vidéo n'a été publiée et aucun appel payant n'a été fait pour ces contrôles.
