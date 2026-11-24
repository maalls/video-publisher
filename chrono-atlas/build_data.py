import json,sys,math
EPS=float(sys.argv[1]) if len(sys.argv)>1 else 0.2
import zlib,urllib.request,zipfile,os
SRC="https://github.com/Seshat-Global-History-Databank/cliopatria/raw/main/cliopatria.geojson.zip"
if not os.path.exists("cliopatria_polities_only_v021.geojson"):
    urllib.request.urlretrieve(SRC,"clio.zip"); zipfile.ZipFile("clio.zip").extractall(".")

def dp(pts,eps):
    n=len(pts)
    if n<=4: return pts
    keep=[False]*n; keep[0]=keep[-1]=True
    st=[(0,n-1)]
    e2=eps*eps
    while st:
        a,b=st.pop()
        ax,ay=pts[a]; bx,by=pts[b]
        dx=bx-ax; dy=by-ay; L=dx*dx+dy*dy
        mx=-1; mi=-1
        for i in range(a+1,b):
            px,py=pts[i]
            if L==0: d=(px-ax)**2+(py-ay)**2
            else:
                t=((px-ax)*dx+(py-ay)*dy)/L
                t=0 if t<0 else 1 if t>1 else t
                d=(px-ax-t*dx)**2+(py-ay-t*dy)**2
            if d>mx: mx=d; mi=i
        if mx>e2:
            keep[mi]=True; st.append((a,mi)); st.append((mi,b))
    return [p for p,k in zip(pts,keep) if k]
def ring(r,eps):
    r=dp(r,eps)
    if len(r)<4: return None
    # area filter
    xs=[p[0] for p in r]; ys=[p[1] for p in r]
    if (max(xs)-min(xs))*(max(ys)-min(ys))<eps*eps*4: return None
    return [[round(x,2),round(y,2)] for x,y in r]
d=json.load(open("cliopatria_polities_only_v021.geojson"))
LIN=json.load(open("data/lineages.json"))["name_to_lineage"] if os.path.exists("data/lineages.json") else {}
out=[]
for f in d["features"]:
    g=f["geometry"]; polys=g["coordinates"] if g["type"]=="MultiPolygon" else [g["coordinates"]]
    np=[]
    for p in polys:
        o=ring(p[0],EPS)
        if o: np.append([o])  # outer ring only (holes dropped)
    if not np: continue
    p=f["properties"]
    out.append({"type":"Feature","properties":{"n":p["Name"],"f":p["FromYear"],"t":p["ToYear"],"ty":p.get("Type"),"a":round(p.get("Area") or 0),"m":p.get("MemberOf") or "","k":p.get("Components") or "","q":p.get("Wikidata") or "","c":("hsl(%d,55%%,52%%)"%(zlib.crc32(LIN.get(p["Name"],p["Name"]).encode())%360)) if p.get("Type")!="RELATION" else "#999"},"geometry":{"type":"MultiPolygon","coordinates":np}})
json.dump({"type":"FeatureCollection","features":out},open("data/cliopatria_simplifie.geojson","w"),separators=(",",":"),ensure_ascii=False)
print(len(out))
