#!/usr/bin/env python3
"""Régénère data/cultures/*.md, data/cultures/README.md et les colonnes calculées de data/cultures.csv.
Sources de vérité : data/cultures_titres.json (titres + source + origine, par culture) et les 10 premières colonnes de data/cultures.csv.
Usage : python3 scripts/cultures_build.py  (depuis la racine du dépôt)"""
import csv,json,re,unicodedata,os,shutil
root=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P=lambda *a: os.path.join(root,*a)
rows=[x[:10] for x in csv.reader(open(P("data/cultures.csv"),encoding="utf-8"))]
hdr=rows[0]; data=rows[1:]
avis=json.load(open(P("data/cultures_avis.json"),encoding="utf-8"))
esc=json.load(open(P("data/cultures_escales.json"),encoding="utf-8"))
titres=json.load(open(P("data/cultures_titres.json"),encoding="utf-8"))
LONG={
"Epic of Gilgamesh":("récit long","Épisode adaptable identifié : la Tablette XI, le Déluge (récit autonome, voir https://en.wikisource.org/wiki/Epic_of_Gilgamesh). Version 1-2 min non vérifiée."),
"Popol Vuh":("récit long","Épisode adaptable identifié : « The Myth of Vukub-Cakix » (section titrée de Spence, https://www.gutenberg.org/files/56550/56550-h/56550-h.htm). Version 1-2 min non vérifiée."),
"Kebra Nagast (la reine de Saba et Ménélik)":("récit long","Épisode adaptable identifié : chapitre 25 « How the Queen came to Solomon the King » (https://sacred-texts.com/book/the-kebra-nagast). Version 1-2 min non vérifiée."),
"Serat Kancil (Java)":("récit long","Épisode adaptable identifié : le tigre et le buffle (pupuh 2 à 4 du résumé « Ringkasan Cerita », https://jv.wikisource.org/wiki/Serat_Kancil_1). Version 1-2 min non vérifiée."),
"Ural-Batyr":("récit long","Aucun épisode titré identifié dans la source ouverte : édition spéciale longue."),
"Sons of the Sun (Fjellner, via Billson)":("récit long","Aucun épisode identifié (source secondaire) : édition spéciale longue."),
}
def typ(t):
    if t in LONG: return LONG[t]
    if t.startswith("RUNE "): return ("récit long (épisode d'épopée)","Chaque rune du Kalevala est un épisode titré dans la source ; version 1-2 min non vérifiée, à valider par adaptation.")
    return ("conte court (présumé, non vérifié)","")
def slug(s):
    s=unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode().lower()
    s=re.sub(r"\(.*?\)","",s); s=re.sub(r"[^a-z0-9]+","-",s).strip("-")
    return s[:40].strip("-")
D=P("data/cultures"); shutil.rmtree(D,ignore_errors=True); os.makedirs(D)
GH="https://github.com/maalls/video-publisher/blob/main/data/cultures/"
newhdr=hdr+["nb_titres_listes","nb_recits_longs","fichier","lien_github","avis_communaute","escale_bateau"]
newrows=[]; idx=[]
for r in data:
    c=r[0]; n=int(r[2]); L=titres.get(c,[])
    if n==0 and not L:
        newrows.append(r+["0","0","","",avis.get(c,"à évaluer"),esc.get(c,"")]); continue
    fn=f"{len(idx)+1:03d}-{slug(c)}.md"
    md=[f"# {c}","",f"- Région : {r[1]}",f"- Nombre de contes visés : {n}",f"- Contes listés avec source : {len(L)}",f"- Sensibilité / droits : {r[5]}",f"- Escale du voyage en bateau : {esc.get(c) or '-'}",f"- Avis de la communauté requis avant production : {avis.get(c,'à évaluer')}",f"- Note : {r[6]}",f"- Sources de référence (vérifiées en ligne) : {r[3]}","",
        "Aucun titre n'est inventé : chaque ligne vient d'une source citée. Résumés, droits de chaque édition et doublons restent à vérifier avant de produire le conte.","",
        "| n | titre | type | source | origine du titre | note adaptation conte court |","|---|---|---|---|---|---|"]
    for k,(t,u,o) in enumerate(L,1):
        ty,nt=typ(t)
        if c in('Hmong',"Afrique de l'Ouest (Akan)"): o='À VÉRIFIER : '+o
        md.append(f"| {k} | {t.replace('|','/')} | {ty} | {u} | {o} | {nt} |")
    if len(L)<n: md+=["",f"Reste à relever : {n-len(L)} titres (source à ouvrir ou autre recueil à identifier)."]
    open(f"{D}/{fn}","w",encoding="utf-8").write("\n".join(md)+"\n")
    idx.append((c,len(L),fn))
    newrows.append(r+[str(len(L)),str(sum(1 for x in L if typ(x[0])[0].startswith("récit long"))),f"data/cultures/{fn}",GH+fn,avis.get(c,"à évaluer"),esc.get(c,"")])
csv.writer(open(P("data/cultures.csv"),"w",newline="",encoding="utf-8")).writerows([newhdr]+newrows)
tot=sum(x[1] for x in idx)
rd=["# Contes par culture","","Généré depuis [../cultures.csv](../cultures.csv) et [../cultures_titres.json](../cultures_titres.json) (sources de vérité), data/cultures_avis.json (flag avis_communaute : oui, non, à évaluer). Chaque titre est rattaché à une source citée dans le fichier de sa culture.","",
 "Régénérer : `python3 scripts/cultures_build.py` (depuis la racine du dépôt).","",f"{tot} titres, {len(idx)} cultures.","","| culture | titres | fichier |","|---|---|---|"]
for c,l,fn in idx: rd.append(f"| {c} | {l} | [{fn}]({fn}) |")
open(f"{D}/README.md","w",encoding="utf-8").write("\n".join(rd)+"\n")
print(len(idx),tot)
