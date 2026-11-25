import json,math
B={int(k):v for k,v in json.load(open('./bbox_year.json')).items()}
ys=sorted(B)
W,H=540,340; M=1.18; Z0=math.log2(W/512); MINSPAN=70
def my(lat):
    lat=max(-85,min(85,lat));return math.log(math.tan(math.pi/4+math.radians(lat)/2))
def cam(b):
    l0,l1,a0,a1=b
    span=max(l1-l0,MINSPAN*0.5);lat0,lat1=a0,a1
    cl=(l0+l1)/2;ca=(a0+a1)/2
    s=max(span*M,MINSPAN)
    zl=math.log2(W/(s/360*512))
    hy=max((my(a1)-my(a0))*M,my(40)-my(0)*0+0.0)  # min height
    hy=max(hy,(MINSPAN*0.5)*math.pi/180)
    zh=math.log2(H/(hy/(2*math.pi)*512))
    z=max(Z0,min(zl,zh))
    cy=(my(a0)+my(a1))/2
    lat=math.degrees(2*math.atan(math.exp(cy))-math.pi/2)
    cl=((cl+180)%360)-180
    return [cl,lat,z]
raw=[cam(B[y]) for y in ys]
# unwrap lon for smoothing
for i in range(1,len(raw)):
    while raw[i][0]-raw[i-1][0]>180:raw[i][0]-=360
    while raw[i][0]-raw[i-1][0]<-180:raw[i][0]+=360
# smoothing: zoom out fast (a=0.5/step), zoom in slow (0.08/step); centre follows 0.1/step, in 2700 steps ~ 0.033 s each
sm=[raw[0][:]]
for r in raw[1:]:
    p=sm[-1];a=0.35 if r[2]<p[2] else 0.04
    z=p[2]+(r[2]-p[2])*a
    k=0.06
    sm.append([p[0]+(r[0]-p[0])*k,p[1]+(r[1]-p[1])*k,z])
json.dump({'years':ys,'raw':raw,'smooth':sm},open('./cam_year.json','w'))
for y in (-3300,-1500,0,1000,1500,1918,2024):
    i=min(range(len(ys)),key=lambda i:abs(ys[i]-y));print(y,[round(v,2) for v in sm[i]],'raw z',round(raw[i][2],2))
print('Z0',round(Z0,2),'zmax',round(max(r[2] for r in sm),2))
try:
    import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
    f,ax=plt.subplots(figsize=(8,3));ax.plot(ys,[r[2] for r in raw],lw=.8,label='cible');ax.plot(ys,[r[2] for r in sm],label='lissé');ax.axhline(Z0,ls='--',c='gray');ax.set_xlabel('année');ax.set_ylabel('zoom');ax.legend();f.tight_layout();f.savefig('zoom-curve.png',dpi=110);print('plot ok')
except Exception as e:print('noplot',e)
