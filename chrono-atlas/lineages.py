"""Regroupe les entites Cliopatria en lignees (meme civilisation sous des noms differents).
Regle automatique : A -> B si l'emprise de A (derniere annee) et celle de B (premiere annee)
se recouvrent a >= 60 % (intersection / union), avec B qui commence au plus 40 ans apres la fin de A
(ou au plus 10 ans avant). Les agregats (noms entre parentheses) sont exclus.
Puis regroupements editoriaux (EDITORIAL). Sortie : data/lineages.json
Usage : python3 lineages.py cliopatria_polities_only_v021.geojson   (necessite shapely)"""
import json,sys,re,collections
from shapely.geometry import shape
from shapely.strtree import STRtree
TH=0.6
d=json.load(open(sys.argv[1]))
rec=collections.defaultdict(list)
for f in d["features"]:
    p=f["properties"]
    if p["Type"]!="POLITY" or p["Name"].startswith("("): continue
    rec[p["Name"]].append((p["FromYear"],p["ToYear"],f["geometry"]))
def g(x):
    s=shape(x[2]).simplify(0.2); return s if s.is_valid else s.buffer(0)
G={}
for n,L in rec.items():
    L.sort(key=lambda x:x[0])
    G[n]=dict(f=L[0][0],t=max(x[1] for x in L),first=g(L[0]),last=g(L[-1]))
names=list(G); tree=STRtree([G[n]["first"] for n in names])
par={n:n for n in names}
def find(x):
    while par[x]!=x: par[x]=par[par[x]]; x=par[x]
    return x
edges=[]
for a in names:
    A=G[a]
    for i in tree.query(A["last"]):
        b=names[i]
        if b==a: continue
        B=G[b]; gap=B["f"]-A["t"]
        if -10<=gap<=40:
            inter=A["last"].intersection(B["first"]).area
            if inter<=0: continue
            iou=inter/A["last"].union(B["first"]).area
            if iou>=TH:
                edges.append((a,b,round(iou,2))); par[find(a)]=find(b)
# EDITORIAL : regroupements decides a la main (a valider par Malo)
EDITORIAL={
 "Egypte antique (editorial)": [n for n in names if re.search(r"Egypt",n) and G[n]["t"]<=0],
}
src={}
for lab,ms in EDITORIAL.items():
    for m in ms[1:]: par[find(m)]=find(ms[0])
    for m in ms: src[m]="editorial"
comp=collections.defaultdict(list)
for n in names: comp[find(n)].append(n)
out={}; lines={}
for ms in comp.values():
    ms.sort(key=lambda n:G[n]["f"])
    if len(ms)<2: continue
    root=ms[0]
    lines[root]=dict(members=ms,editorial=[m for m in ms if src.get(m)])
    for m in ms: out[m]=root
json.dump({"threshold_iou":TH,"lineages":lines,"edges_auto":edges,"name_to_lineage":out},open("data/lineages.json","w"),ensure_ascii=False,indent=0)
print(len(names),"noms;",len(lines),"lignees;",len(out),"noms regroupes;",sorted((len(v["members"]) for v in lines.values()),reverse=True)[:10])
