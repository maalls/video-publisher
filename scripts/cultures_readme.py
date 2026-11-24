#!/usr/bin/env python3
"""Régénère data/cultures/README.md depuis data/cultures.csv (le CSV est la source).
Usage : python3 scripts/cultures_readme.py  (depuis la racine du dépôt)"""
import csv, os
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
r = list(csv.reader(open(os.path.join(root, "data/cultures.csv"), encoding="utf-8")))
h = r[0]; i = h.index("nb_titres_listes"); f = h.index("fichier")
rows = [x for x in r[1:] if x[f]]
out = ["# Contes par culture", "",
 "Généré depuis [../cultures.csv](../cultures.csv) (le CSV est la source). Chaque titre est rattaché à une source citée dans le fichier de sa culture.", "",
 "Régénérer : `python3 scripts/cultures_readme.py` (depuis la racine du dépôt).", "",
 f"{sum(int(x[i]) for x in rows)} titres, {len(rows)} cultures.", "",
 "| culture | titres | fichier |", "|---|---|---|"]
for x in rows:
    n = os.path.basename(x[f]); out.append(f"| {x[0]} | {x[i]} | [{n}]({n}) |")
open(os.path.join(root, "data/cultures/README.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
