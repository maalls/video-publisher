#!/usr/bin/env python3
import json,time,urllib.request
from pathlib import Path
ROOT=Path('/home/instinct/video-publisher/var/project/tales/productions/conte05-grue-reconnaissante')
API='http://127.0.0.1:8188'
STYLE='Lyrical hand-drawn 2D animated folk-tale illustration, delicate irregular pencil contours, pale translucent watercolor washes on softly grained cream paper, simplified expressive faces, elegant graphic shapes, snow-covered Japanese mountain village, soft indigo, pale silver-blue and warm lantern amber accents palette. Tender atmospheric Japanese winter landscape, no photorealism, no glossy 3D, no thick black ink, no cel-shaded anime, no letters or text, no border. Vertical composition 704 by 832 pixels. '
REF_MAN='Use the reference as the fixed visual identity and illustration style for the same woodcutter character: kind young Japanese man, gentle oval face, warm dark brown eyes, black hair in a small topknot, indigo-blue work kimono with grey-beige sash. Keep his exact design, colors and proportions. '
SCENES=[
('10-marche-repair2','A small snowy morning market square in a Japanese mountain village, a few wooden stalls with awnings. The young woodcutter in his indigo kimono holds up a rolled bolt of fine silver-white cloth with a soft pearly sheen with both hands, an older merchant in a dark brown kimono hands him a small coin pouch, two or three blurred villagers in winter clothes admiring in the background. Warm morning light, gentle falling snow, lively but peaceful mood. The woodcutter is the clear main subject, the cloth is clearly ordinary woven fabric with a subtle sheen, no glowing orb, no floating ball of light, no moon, no text.',20260711),
('12-adieux-repair2','Sad tender farewell scene at the open cottage door at grey dawn. The elegant white crane with a small red crown stands in the snow just outside the door, wings folded, its body and head turned toward the woodcutter, facing him directly and looking into his eyes with a gentle melancholy gaze. The young woodcutter stands a few steps away in the snow facing the crane, hands at his sides, sad grateful expression. The two characters face each other, both fully visible. Soft falling snow, pale blue dawn light, warm lantern glow from inside, no text.',20260712),
]
def call(path,data=None):
 req=urllib.request.Request(API+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=90) as r:return json.load(r)
def prompt(text,seed,prefix):
 enc={'clip':['2',0],'prompt':REF_MAN+STYLE+text,'vae':['3',0],'image1':['12',0]}
 neg={'clip':['2',0],'prompt':'','vae':['3',0],'image1':['12',0]}
 return {'1':{'class_type':'UNETLoader','inputs':{'unet_name':'qwen_image_edit_2511_fp8mixed.safetensors','weight_dtype':'default'}},'2':{'class_type':'CLIPLoader','inputs':{'clip_name':'qwen_2.5_vl_7b_fp8_scaled.safetensors','type':'qwen_image','device':'default'}},'3':{'class_type':'VAELoader','inputs':{'vae_name':'qwen_image_vae.safetensors'}},'4':{'class_type':'ModelSamplingAuraFlow','inputs':{'model':['1',0],'shift':3.1}},'5':{'class_type':'CFGNorm','inputs':{'model':['4',0],'strength':1}},'6':{'class_type':'TextEncodeQwenImageEditPlus','inputs':enc},'7':{'class_type':'TextEncodeQwenImageEditPlus','inputs':neg},'8':{'class_type':'EmptySD3LatentImage','inputs':{'width':704,'height':832,'batch_size':1}},'9':{'class_type':'KSampler','inputs':{'model':['5',0],'positive':['6',0],'negative':['7',0],'latent_image':['8',0],'seed':seed,'steps':40,'cfg':4,'sampler_name':'euler','scheduler':'simple','denoise':1}},'10':{'class_type':'VAEDecode','inputs':{'samples':['9',0],'vae':['3',0]}},'11':{'class_type':'SaveImage','inputs':{'images':['10',0],'filename_prefix':prefix}},'12':{'class_type':'LoadImage','inputs':{'image':'conte05-bucheron-reference.png'}}}
def run_one(name,text,seed):
 journal=ROOT/(name+'.receipt.json')
 p=prompt(text,seed,'contes/conte05/'+name)
 if journal.exists():
  r=json.loads(journal.read_text())
  if r.get('outputs'):return r['outputs']
  if not r.get('prompt_id'):raise RuntimeError('Unknown submission intent, no retry '+name)
 else:
  journal.write_text(json.dumps({'phase':'intent'}))
  response=call('/prompt',{'prompt':p})
  r={'phase':'submitted','prompt_id':response['prompt_id']};journal.write_text(json.dumps(r))
 (ROOT/(name+'.workflow.json')).write_text(json.dumps(p,ensure_ascii=False,indent=2))
 print(name,r['prompt_id'],flush=True)
 for _ in range(240):
  h=call('/history/'+r['prompt_id']).get(r['prompt_id'])
  if h:
   if h.get('status',{}).get('status_str')=='error':raise RuntimeError(str(h['status']))
   r.update(phase='done',outputs=h.get('outputs',{}));journal.write_text(json.dumps(r));print(name,'DONE',flush=True);return r['outputs']
  time.sleep(5)
 raise RuntimeError('Timeout, keep journal '+name)
if __name__=='__main__':
 for name,text,seed in SCENES:
  run_one(name,text,seed)
 print('ALL DONE',flush=True)
