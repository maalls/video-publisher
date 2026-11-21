#!/usr/bin/env python3
import json,time,urllib.request,uuid,copy
from pathlib import Path
ROOT=Path('/home/instinct/video-publisher/var/project/tales/productions/conte05-grue-reconnaissante')
API='http://127.0.0.1:8188'
SRC=Path('/home/malo/ComfyUI/output/contes/conte05')
NEG='photorealistic, 3D, sudden camera movement, extra limbs, deformed face, extra legs, duplicate characters, human child, morphing, text, captions, oversaturated colors, jerky motion'
# name, base workflow, length(frames), seed, source image (None = keep base image), motion prompt (None = keep)
ANIMS=[
('10-marche-repair2','anim-10-marche.workflow.json',137,20260721,'10-marche-repair2','The woodcutter holds up the rolled bolt of fine silver-white cloth with both hands, the merchant hands him a small coin pouch, blurred villagers shift softly in the background, snow falling gently. No glowing orb, no ball of light anywhere. Camera still. Preserve the exact reference composition and style.'),
('11-curiosite-long','anim-11-curiosite.workflow.json',205,20260722,None,None),
('07-revelation-long','anim-07-revelation.workflow.json',177,20260723,None,None),
('12-adieux-repair2','anim-12-adieux.workflow.json',245,20260724,'12-adieux-repair2','The white crane faces the woodcutter, looking at him with a gentle melancholy gaze, blinking slowly once, its head tilting slightly, snow falling softly between them, the woodcutter faces her, deeply moved, breathing visibly. Both stay in place. Camera still. Preserve the exact reference composition and style.'),
]
def call(path,data=None):
 req=urllib.request.Request(API+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=90) as r:return json.load(r)
def upload(local,remote):
 b=uuid.uuid4().hex.encode()
 body=b'--'+b+b'\r\nContent-Disposition: form-data; name="image"; filename="'+remote.encode()+b'"\r\nContent-Type: image/png\r\n\r\n'+Path(local).read_bytes()+b'\r\n--'+b+b'\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n--'+b+b'--\r\n'
 req=urllib.request.Request(API+'/upload/image',data=body,headers={'Content-Type':'multipart/form-data; boundary='+b.decode()})
 with urllib.request.urlopen(req,timeout=120) as r:return json.load(r)
def run_one(name,p):
 journal=ROOT/('anim-'+name+'.receipt.json')
 if journal.exists():
  r=json.loads(journal.read_text())
  if r.get('outputs'):return r['outputs']
  if not r.get('prompt_id'):raise RuntimeError('Unknown submission intent, no retry '+name)
 else:
  journal.write_text(json.dumps({'phase':'intent'}))
  response=call('/prompt',{'prompt':p})
  r={'phase':'submitted','prompt_id':response['prompt_id']};journal.write_text(json.dumps(r))
 (ROOT/('anim-'+name+'.workflow.json')).write_text(json.dumps(p,ensure_ascii=False,indent=2))
 print('anim-'+name,r['prompt_id'],flush=True)
 for _ in range(480):
  h=call('/history/'+r['prompt_id']).get(r['prompt_id'])
  if h:
   if h.get('status',{}).get('status_str')=='error':raise RuntimeError(str(h['status']))
   r.update(phase='done',outputs=h.get('outputs',{}));journal.write_text(json.dumps(r));print('anim-'+name,'DONE',flush=True);return r['outputs']
  time.sleep(15)
 raise RuntimeError('Timeout, keep journal '+name)
if __name__=='__main__':
 for name,base,length,seed,img,motion in ANIMS:
  w=json.loads((ROOT/base).read_text())
  w['55']['inputs']['length']=length
  w['3']['inputs']['seed']=seed
  if img:
   upload(SRC/(img+'_00001_.png'),'conte05-%s.png'%img)
   w['56']['inputs']['image']='conte05-%s.png'%img
  if motion:
   w['6']['inputs']['text']=motion
  w['7']['inputs']['text']=NEG
  w['58']['inputs']['filename_prefix']='contes/conte05/anim-'+name
  try:
   run_one(name,w)
  except RuntimeError as e:
   if length>121 and 'out of memory' in str(e).lower():
    print(name,'OOM at',length,'frames, retry at 121',flush=True)
    w['55']['inputs']['length']=121
    run_one(name+'-121f',w)
   else: raise
 print('ALL DONE',flush=True)
