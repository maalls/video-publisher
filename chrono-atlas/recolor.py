"""Recolore data/cliopatria_simplifie.geojson selon data/lineages.json (sans retelecharger Cliopatria)."""
import json,zlib
L=json.load(open("data/lineages.json"))["name_to_lineage"]
d=json.load(open("data/cliopatria_simplifie.geojson"))
n=0
for f in d["features"]:
    p=f["properties"]
    if p["ty"]=="RELATION": continue
    c="hsl(%d,55%%,52%%)"%(zlib.crc32(L.get(p["n"],L.get(p["n"].strip("()"),p["n"].strip("()"))).encode())%360)
    if c!=p["c"]: n+=1
    p["c"]=c
json.dump(d,open("data/cliopatria_simplifie.geojson","w"),separators=(",",":"),ensure_ascii=False)
print("recolores",n)
