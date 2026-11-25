import json,math
d=json.load(open('./clio.geojson'))
parts=[]  # (f,t,lon0,lon1,lat0,lat1,w)
for ft in d['features']:
    p=ft['properties']
    if p['ty']!='POLITY':continue
    for poly in ft['geometry']['coordinates']:
        ring=poly[0]
        lons=[c[0] for c in ring];lats=[c[1] for c in ring]
        if max(lons)-min(lons)>180: lons=[x+360 if x<0 else x for x in lons]  # ring crossing antimeridian
        lo,hi=min(lons),max(lons);la0,la1=min(lats),max(lats)
        w=max((hi-lo)*(la1-la0),1e-3)
        parts.append((p['f'],p['t'],lo,hi,la0,la1,w))
print(len(parts))
def wq(vals,ws,q):
    s=sorted(zip(vals,ws));tot=sum(w for _,w in s);c=0
    for v,w in s:
        c+=w
        if c>=q*tot:return v
    return s[-1][0]
def box(y):
    A=[x for x in parts if x[0]<=y<=x[1]]
    if not A:return None
    # circular lon: centers
    cx=[(a[2]+a[3])/2 for a in A];ws=[a[6] for a in A]
    # largest weighted-empty arc: bin 360 deg
    occ=[0]*360
    for a in A:
        for k in range(int(a[2]//1),int(a[3]//1)+1):occ[k%360]+=1
    # find longest run of empty bins
    best=(0,0);run=0;start=0
    for i in range(720):
        if occ[i%360]==0:
            if run==0:start=i
            run+=1
            if run>best[0] and run<360:best=(run,start)
        else:run=0
    seam=(best[1]+best[0]//2)%360  # lon at the middle of the gap = new antimeridian
    def sh(x):return (x-seam)%360
    lo=[sh((a[2]+a[3])/2) for a in A];
    L0=wq([sh(a[2]) for a in A],ws,0.02);L1=wq([sh(a[3]) for a in A],ws,0.98)
    B0=wq([a[4] for a in A],ws,0.02);B1=wq([a[5] for a in A],ws,0.98)
    return (L0+seam,L1+seam,B0,B1)
out={}
for i in range(0,2700,1):
    y=round(-3400+i*(2024+3400)/2699)
    if y in out:continue
    out[y]=box(y)
json.dump({str(k):v for k,v in out.items()},open('./bbox_year.json','w'))
for y in (-3300,-2500,-1500,-500,0,500,1000,1200,1500,1800,1918,2000,2024):
    print(y,[round(x,1) for x in out[min(out,key=lambda k:abs(k-y))]])
