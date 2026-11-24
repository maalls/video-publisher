# Carte des civilisations (prototype)

Page statique : MapLibre GL JS + polygones Cliopatria + curseur de temps (-5000 à 2024).
Prototype de rendu, non publié. Les 152 cultures ne sont pas encore ajoutées.

Données et licences :
- Polygones : Cliopatria v0.2.1 (Seshat Global History Databank), CC BY 4.0, https://zenodo.org/records/13363121 , https://doi.org/10.1038/s41597-025-04516-9
  Fichier simplifié par `build_data.py` (Douglas-Peucker 0,2 degré, trous retirés, petits polygones supprimés). Modifié par rapport à l'original.
- Terres : Natural Earth 110m (domaine public) via world-atlas (ISC).
- Rendu : MapLibre GL JS 6.19.0 (BSD-3-Clause), copié dans `lib/`.

Générer les données (173 Mo téléchargés, sortie ~17 Mo) :  `cd carte && python3 build_data.py 0.2`
Servir en local : `cd carte && python3 -m http.server 8765` puis http://localhost:8765/
Aucune donnée n'est chargée depuis un serveur tiers.
