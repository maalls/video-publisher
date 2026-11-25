# Chrono Atlas, rendu video

Etat valide le 25/11/2026: version verticale 9:16 (video_V5.html), 90 s, musique ajoutee a part.

- pages/video_V5.html: vertical 540x960 (rendu a 1080x1920), carte monde en haut, Top 10 centre dessous.
- pages/video_G.html: horizontale (apercu G), pages/video_C.html: horizontale de reference.
- scripts/: serveur local (srv.py), rendu image par image (render2g.mjs, puppeteer-core + Chrome for Testing), apercu fixe (still.mjs), lancement (runV.sh).
- Les pages se placent dans un dossier avec lib/ (maplibre) et data/ (donnees Cliopatria simplifiees, non versionnees, voir ../build_data.py).
- Assemblage: ffmpeg -framerate 30 -i outV/f%05d.jpg -i audio.m4a -c:v libx264 -crf 20 -c:a copy -t 90 sortie.mp4
- Donnees: Cliopatria (Seshat), CC BY 4.0, a citer.
