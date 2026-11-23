#!/usr/bin/env python3
"""Lanceur unique d'un conte anime : conte.json -> video master, puis arret.

  launcher.py check DIR                     valide conte.json, ne touche a rien
  launcher.py run DIR [--version v1] [--dry-run] [--only etape,etape] [--redo plan,plan]
  launcher.py status DIR
  launcher.py approve DIR --evidence "..."  fige le master valide (sha256) pour la publication

DIR = var/project/tales/productions/<id>/ (contient conte.json, voix/voix-NN.wav, musique).
Etapes (dans l'ordre) : check, voix, split, references, images, animations, sous-titres,
montage, qc, validation. Le lanceur S'ARRETE a "validation" : la publication ne part qu'apres
`approve` (voir publish_conte.py). Voix : le lanceur ne genere pas la voix (outil TTS de l'agent) ;
il verifie que voix/voix-NN.wav existe et s'arrete sinon, proprement.
--dry-run : valide, construit les workflows dans DIR/dry-run/, aucun appel ComfyUI ni ffmpeg.
Chaque etape est chronometree (steptimer -> timing.jsonl, timing-recap.md) et la duree de chaque
element ComfyUI est dans son reçu (champ seconds).
"""
import argparse, copy, hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import comfy_client as cc  # noqa: E402

COMFY_OUT = Path(os.environ.get('COMFY_OUTPUT', '/home/malo/ComfyUI/output'))
WHISPER_PY = os.environ.get('WHISPER_PY', '/home/instinct/whisper-venv/bin/python')
ENDCARD = HERE.parents[1] / 'var' / 'project' / 'tales' / 'endcard'
TEMPLATE = HERE / 'templates' / 'wan22_i2v.workflow.json'
NEG = ('photorealistic, 3D, sudden camera movement, extra limbs, deformed face, extra legs, duplicate characters, '
       'human child, morphing, text, captions, oversaturated colors, jerky motion')
KEEP = ' Camera still. Preserve the exact reference composition and style. No new characters, nobody else enters the frame.'
STAGES = ['check', 'voix', 'split', 'references', 'images', 'animations', 'sous-titres', 'montage', 'qc', 'validation']


class Stop(Exception):
    pass


def say(msg):
    print('[lanceur %s] %s' % (time.strftime('%H:%M:%S'), msg), flush=True)


# ---------------------------------------------------------------- conte.json
def load(prod):
    return json.loads((Path(prod) / 'conte.json').read_text())


def validate(c, prod):
    err = []
    for k in ('id', 'title', 'style', 'music', 'narration', 'plans', 'references', 'publication'):
        if k not in c:
            err.append('cle manquante: ' + k)
    if err:
        return err
    segs = c['narration'].get('segments') or []
    if not segs:
        err.append('narration.segments vide')
    keys = {r['key'] for r in c['references']}
    names = set()
    last = 0
    sentences = sum(len([x for x in __import__('re').split(r'(?<=[.!?…]) ', s) if x.strip()]) for s in segs)
    for i, p in enumerate(c['plans'], 1):
        for k in ('name', 'ref', 'image', 'motion', 'phrases'):
            if k not in p:
                err.append('plan %d: cle manquante %s' % (i, k))
        if p.get('name') in names:
            err.append('plan en double: ' + p.get('name', '?'))
        names.add(p.get('name'))
        if p.get('ref') not in keys:
            err.append('plan %s: reference inconnue %s' % (p.get('name'), p.get('ref')))
        ph = p.get('phrases') or [0, 0]
        if ph[0] != last + 1 or ph[1] < ph[0]:
            err.append('plan %s: phrases %s ne suivent pas le plan precedent (attendu debut %d)' % (p.get('name'), ph, last + 1))
        last = ph[1]
    if last != sentences:
        err.append('les plans couvrent %d phrases, la narration en compte %d' % (last, sentences))
    for r in c['references']:
        for k in ('key', 'prompt', 'identity'):
            if k not in r:
                err.append('reference %s: cle manquante %s' % (r.get('key'), k))
    if not (Path(prod) / c['music']['file']).exists():
        err.append('musique introuvable: ' + c['music']['file'])
    for k in ('title', 'youtube_description', 'caption', 'hashtags'):
        if k not in c['publication']:
            err.append('publication.%s manquant' % k)
    return err


def state_path(prod):
    return Path(prod) / 'launcher-state.json'


def load_state(prod):
    p = state_path(prod)
    return json.loads(p.read_text()) if p.exists() else {'variants': {}, 'stages': {}}


def save_state(prod, st):
    state_path(prod).write_text(json.dumps(st, indent=1, ensure_ascii=False))


def item(name, st, kind):
    n = st['variants'].get(kind + ':' + name, 0)
    return name if n == 0 else '%s-v%d' % (name, n)


# ------------------------------------------------------------------ chrono
CUR = {'prod': None}


def timed(label, fn, *a, **k):
    # journal de duree par script / par plan : une ligne debut, une ligne fin dans timing.jsonl
    prod = CUR['prod']
    if prod is None:
        return fn(*a, **k)
    timer(prod, 'start', label)
    rc = 'ok'
    try:
        return fn(*a, **k)
    except BaseException as e:
        rc = 'erreur %s' % type(e).__name__
        raise
    finally:
        timer(prod, 'end', label, rc)


def timer(prod, event, step, note=''):
    subprocess.call([sys.executable, str(HERE / 'steptimer.py'), str(prod), event, step] + (['--note', note] if note else []))


# --------------------------------------------------------------- workflows
def ref_text(c, key):
    r = next(x for x in c['references'] if x['key'] == key)
    return ('Use the reference as the fixed visual identity and illustration style for: %s '
            'Keep their exact design, colors and proportions. ' % r['identity'])


def image_workflow(text, seed, prefix, reffile=None, size=(704, 832)):
    enc = {'clip': ['2', 0], 'prompt': text}
    neg = {'clip': ['2', 0], 'prompt': ''}
    if reffile:
        enc.update(vae=['3', 0], image1=['12', 0])
        neg.update(vae=['3', 0], image1=['12', 0])
    w = {'1': {'class_type': 'UNETLoader', 'inputs': {'unet_name': 'qwen_image_edit_2511_fp8mixed.safetensors', 'weight_dtype': 'default'}},
         '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 'qwen_2.5_vl_7b_fp8_scaled.safetensors', 'type': 'qwen_image', 'device': 'default'}},
         '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'qwen_image_vae.safetensors'}},
         '4': {'class_type': 'ModelSamplingAuraFlow', 'inputs': {'model': ['1', 0], 'shift': 3.1}},
         '5': {'class_type': 'CFGNorm', 'inputs': {'model': ['4', 0], 'strength': 1}},
         '6': {'class_type': 'TextEncodeQwenImageEditPlus', 'inputs': enc},
         '7': {'class_type': 'TextEncodeQwenImageEditPlus', 'inputs': neg},
         '8': {'class_type': 'EmptySD3LatentImage', 'inputs': {'width': size[0], 'height': size[1], 'batch_size': 1}},
         '9': {'class_type': 'KSampler', 'inputs': {'model': ['5', 0], 'positive': ['6', 0], 'negative': ['7', 0], 'latent_image': ['8', 0],
                                                    'seed': seed, 'steps': 40, 'cfg': 4, 'sampler_name': 'euler', 'scheduler': 'simple', 'denoise': 1}},
         '10': {'class_type': 'VAEDecode', 'inputs': {'samples': ['9', 0], 'vae': ['3', 0]}},
         '11': {'class_type': 'SaveImage', 'inputs': {'images': ['10', 0], 'filename_prefix': prefix}}}
    if reffile:
        w['12'] = {'class_type': 'LoadImage', 'inputs': {'image': reffile}}
    return w


def anim_workflow(motion, seed, remote_image, prefix):
    w = copy.deepcopy(json.loads(TEMPLATE.read_text()))
    w['3']['inputs']['seed'] = seed
    w['6']['inputs']['text'] = motion
    w['7']['inputs']['text'] = NEG
    w['56']['inputs']['image'] = remote_image
    w['58']['inputs']['filename_prefix'] = prefix
    return w


def plan_items(c, st):
    """Liste (index, plan, image_item, anim_item, image_workflow_args...) pour l'etat courant."""
    out = []
    for i, p in enumerate(c['plans'], 1):
        out.append((i, p, item(p['name'], st, 'img'), item(p['name'], st, 'anim')))
    return out


def seed_for(base, i, variant):
    return base + i + 100 * variant


# ------------------------------------------------------------------ etapes
def stage_voix(c, prod):
    prod = Path(prod)
    n = len(c['narration']['segments'])
    narr = {k: c['narration'].get(k) for k in ('voice', 'voice_instructions')}
    narr.update(title=c['title'], origin=c.get('origin'), opening_question=c['narration'].get('opening_question'),
                segments=c['narration']['segments'])
    (prod / 'narration.json').write_text(json.dumps(narr, ensure_ascii=False, indent=1))
    (prod / 'voix').mkdir(exist_ok=True)

    def missing():
        return [i for i in range(1, n + 1) if not (prod / 'voix' / ('voix-%02d.wav' % i)).exists()]
    if not missing():
        return
    import gemini_tts as g
    take = prod / 'voix' / 'speech-take.wav'
    last = None
    for essai in range(1, 4):  # une prise tronquee ou infidele est refaite automatiquement (3 essais max)
        if not take.exists():
            try:
                creds = g.load_credentials()
            except g.TTSError as e:
                raise Stop('voix manquante (voix/voix-NN.wav) et pas de cle TTS exploitable: %s' % e)
            say('voix: prise Gemini TTS, essai %d/3 (%s, %s, %s)' % (essai, c['narration'].get('voice', 'Sadaltager'), creds[0], c['narration'].get('tts_model') or 'modele par defaut'))
            try:
                timed('script:gemini_tts.py', g.synthesize, '\n\n'.join(c['narration']['segments']), take, voice=c['narration'].get('voice', 'Sadaltager'),
                      style=c['narration'].get('voice_instructions', ''), model=c['narration'].get('tts_model'), creds=creds)
            except g.TTSError as e:
                raise Stop('TTS: %s' % e)
        try:
            run_py([str(HERE / 'cut_take.py'), str(prod)], python=WHISPER_PY)
        except subprocess.CalledProcessError:
            last = 'prise infidele au texte (essai %d)' % essai
            say(last)
            take.rename(prod / 'voix' / ('rejetee-essai%d.wav' % essai))
            (prod / 'voix' / 'take-words.json').unlink(missing_ok=True)  # le cache Whisper est lie a la prise rejetee
            continue
        break
    if missing():
        raise Stop('decoupe de la prise vocale impossible apres 3 essais: ' + str(last))


def stage_split(c, prod):
    run_py([str(HERE / 'split_narration.py'), str(prod)])


def run_py(args, python=None):
    say('RUN ' + ' '.join(args))
    timed('script:' + Path(args[0]).name, subprocess.run, [python or sys.executable] + args, check=True)


def stage_references(c, prod, st, dry):
    prod = Path(prod)
    chosen_p = prod / 'references-chosen.json'
    chosen = json.loads(chosen_p.read_text()) if chosen_p.exists() else {}
    for k, r in enumerate(c['references'], 1):
        name = 'ref-%s-a' % r['key']
        wf = image_workflow(c['style'] + ' ' + r['prompt'], r.get('seed', c.get('image_seed_base', 20260000) + 900 + k),
                            'contes/%s/%s' % (c['id'], name))
        if dry:
            (prod / 'dry-run').mkdir(exist_ok=True)
            (prod / 'dry-run' / (name + '.workflow.json')).write_text(json.dumps(wf, indent=1))
            continue
        out = timed('plan:' + name, cc.run_one, prod / (name + '.receipt.json'), wf, name, log=say)
        m = cc.first_file(out, '.png')
        chosen.setdefault(r['key'], {'filename': m['filename'], 'subfolder': m.get('subfolder', '')})
    if not dry:
        chosen_p.write_text(json.dumps(chosen, indent=1))
        for key, m in chosen.items():
            cc.upload(COMFY_OUT / m['subfolder'] / m['filename'], '%s-%s-reference.png' % (c['id'], key))


def stage_images(c, prod, st, dry):
    prod = Path(prod)
    for i, p, img, _ in plan_items(c, st):
        v = st['variants'].get('img:' + p['name'], 0)
        text = ref_text(c, p['ref']) + c['style'] + ' ' + p['image']
        wf = image_workflow(text, seed_for(c.get('image_seed_base', 20260620), i, v), 'contes/%s/%s' % (c['id'], img),
                            '%s-%s-reference.png' % (c['id'], p['ref']))
        if dry:
            (prod / 'dry-run').mkdir(exist_ok=True)
            (prod / 'dry-run' / (img + '.workflow.json')).write_text(json.dumps(wf, indent=1))
            continue
        timed('plan:' + img, cc.run_one, prod / (img + '.receipt.json'), wf, img, log=say)


def image_file(c, img):
    return COMFY_OUT / 'contes' / c['id'] / (img + '_00001_.png')


def stage_animations(c, prod, st, dry):
    prod = Path(prod)
    for i, p, img, an in plan_items(c, st):
        v = st['variants'].get('anim:' + p['name'], 0)
        remote = '%s-%s.png' % (c['id'], img)
        wf = anim_workflow(p['motion'] + KEEP, seed_for(c.get('anim_seed_base', 20260650), i, v), remote,
                           'contes/%s/anim-%s' % (c['id'], an))
        if dry:
            (prod / 'dry-run').mkdir(exist_ok=True)
            (prod / 'dry-run' / ('anim-' + an + '.workflow.json')).write_text(json.dumps(wf, indent=1))
            continue
        cc.upload(image_file(c, img), remote)
        timed('plan:anim-' + an, cc.run_one, prod / ('anim-' + an + '.receipt.json'), wf, 'anim-' + an, log=say)


def stage_soustitres(c, prod):
    import montage_generic as mg
    timed('script:montage_generic.narration', mg.narration, Path(prod), len(c['narration']['segments']))  # narration-complete.wav requis par l'alignement
    s = c.get('subtitles', {})
    run_py([str(HERE / 'align_subtitles.py'), str(prod), '--max-chars', str(s.get('max_chars', 52)),
            '--max-line-chars', str(s.get('max_line_chars', 30))], python=WHISPER_PY)


def stage_montage(c, prod, st, version):
    import montage_generic as mg
    prod = Path(prod)
    segs = prod / 'segments'
    if segs.exists() and list(segs.glob('seg-*.mp4')):
        segs.rename(prod / ('segments-avant-%s' % time.strftime('%Y%m%d-%H%M%S')))
    mg.narration(prod, len(c['narration']['segments']))
    master, wa = timed('script:montage_generic.py', mg.picture, prod, c, [an for _, _, _, an in plan_items(c, st)], version, COMFY_OUT, ENDCARD)
    return master


def probe(path, entries):
    return subprocess.check_output(['ffprobe', '-v', 'error'] + entries + ['-of', 'csv=p=0', str(path)], text=True).strip()


def stage_qc(c, prod, master):
    """Controles automatiques (ne remplacent pas la relecture de Malo)."""
    prod = Path(prod)
    import montage_generic as mg
    checks = []

    def chk(name, ok, detail=''):
        checks.append({'check': name, 'ok': bool(ok), 'detail': detail})
    w, h = probe(master, ['-select_streams', 'v:0', '-show_entries', 'stream=width,height']).split(',')
    chk('resolution 704x832', (w, h) == ('704', '832'), '%sx%s' % (w, h))
    chk('codecs h264+aac', probe(master, ['-show_entries', 'stream=codec_name']).split() == ['h264', 'aac'])
    d = mg.duration(master)
    chk('duree entre 45 et 180 s', 45 <= d <= 180, '%.1f s' % d)
    chk('taille master <= 64 Mo (limite TikTok proto)', master.stat().st_size <= 64_000_000, '%.1f Mo' % (master.stat().st_size / 1e6))
    ev = json.loads((prod / 'subtitle-events.json').read_text())
    bad = []
    for e in ev:
        try:
            mg.lines_of(e['text'])
        except AssertionError:
            bad.append(e['text'])
    chk('sous-titres: 2 lignes maximum', not bad, '%d evenements, %d en erreur' % (len(ev), len(bad)))
    chk('sous-titres: aucun trou > 4 s', all(b['start'] - a['end'] < 4 for a, b in zip(ev, ev[1:])))
    vol = subprocess.run(['ffmpeg', '-nostdin', '-i', str(master), '-af', 'volumedetect', '-f', 'null', '-'], capture_output=True, text=True).stderr
    mean = [float(x.split(':')[1].split()[0]) for x in vol.splitlines() if 'mean_volume' in x]
    chk('audio audible (moyenne > -40 dB)', mean and mean[0] > -40, '%s dB' % (mean[0] if mean else '?'))
    full = ' '.join(c['narration']['segments']).lower()
    chk('credit musique renseigne (ajoute automatiquement a la publication)', bool(c['music'].get('title') and c['music'].get('artist')))
    # planche contact : une image par ~9 s, pour relecture rapide
    sheet = prod / 'planche-contact.jpg'
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-i', str(master), '-vf', 'fps=1/8,scale=176:-2,tile=6x3', '-frames:v', '1', str(sheet)])
    chk('planche contact generee', sheet.exists())
    (prod / 'qc-report.json').write_text(json.dumps(checks, indent=1, ensure_ascii=False))
    for k in checks:
        say('QC %s %s %s' % ('OK ' if k['ok'] else 'ECHEC', k['check'], k['detail']))
    if not all(k['ok'] for k in checks):
        raise Stop('controle qualite en echec, voir qc-report.json')
    return checks


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def stage_validation(c, prod, master):
    prod = Path(prod)
    info = {'master': master.name, 'sha256': sha(master), 'bytes': master.stat().st_size, 'created': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    (prod / 'awaiting-validation.json').write_text(json.dumps(info, indent=1))
    say('ARRET: video prete pour relecture de Malo: %s (sha256 %s). Publication non lancee.' % (master.name, info['sha256'][:12]))
    return info


def cmd_approve(prod, evidence):
    prod = Path(prod)
    aw = json.loads((prod / 'awaiting-validation.json').read_text())
    master = prod / aw['master']
    if sha(master) != aw['sha256']:
        raise SystemExit('Le master a change depuis la validation demandee, refaire la relecture')
    if len(evidence.strip()) < 10:
        raise SystemExit("--evidence doit citer le message de Malo (date/heure, extrait)")
    ap = {**aw, 'approved_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'evidence': evidence}
    (prod / 'approved.json').write_text(json.dumps(ap, indent=1, ensure_ascii=False))
    say('Master approuve: %s' % aw['master'])


# -------------------------------------------------------------------- run
def cmd_run(prod, version, dry, only, redo):
    prod = Path(prod)
    CUR['prod'] = prod
    c = load(prod)
    st = load_state(prod)
    err = validate(c, prod)
    if err:
        for e in err:
            say('ERREUR conte.json: ' + e)
        raise SystemExit(2)
    say('conte.json valide: %s, %d plans' % (c['id'], len(c['plans'])))
    for name in redo:
        if name not in {p['name'] for p in c['plans']}:
            raise SystemExit('plan inconnu pour --redo: ' + name)
        for kind in ('img', 'anim'):
            st['variants'][kind + ':' + name] = st['variants'].get(kind + ':' + name, 0) + 1
        save_state(prod, st)
        say('plan %s: nouvelle variante (images et animation)' % name)
    todo = [s for s in STAGES if not only or s in only]
    master = None
    for s in todo:
        if s == 'check':
            continue
        if dry and s in ('voix', 'split', 'sous-titres', 'montage', 'qc', 'validation'):
            say('[dry-run] etape %s sautee (aurait lieu en vrai)' % s)
            continue
        say('== etape %s ==' % s)
        timer(prod, 'start', s + '-' + version)
        try:
            if s == 'voix':
                stage_voix(c, prod)
            elif s == 'split':
                stage_split(c, prod)
            elif s == 'references':
                stage_references(c, prod, st, dry)
            elif s == 'images':
                stage_images(c, prod, st, dry)
            elif s == 'animations':
                stage_animations(c, prod, st, dry)
            elif s == 'sous-titres':
                stage_soustitres(c, prod)
            elif s == 'montage':
                master = stage_montage(c, prod, st, version)
            elif s == 'qc':
                master = master or prod / ('%s-master-%s.mp4' % (c['id'], version))
                stage_qc(c, prod, master)
            elif s == 'validation':
                master = master or prod / ('%s-master-%s.mp4' % (c['id'], version))
                stage_validation(c, prod, master)
        except Stop as e:
            timer(prod, 'end', s + '-' + version, 'arret: %s' % e)
            say('ARRET a l\'etape %s: %s' % (s, e))
            return 3
        timer(prod, 'end', s + '-' + version)
        st['stages'][s] = time.strftime('%Y-%m-%dT%H:%M:%S')
        save_state(prod, st)
    if dry:
        say('[dry-run] workflows ecrits dans %s' % (prod / 'dry-run'))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for n in ('check', 'status', 'run', 'approve'):
        p = sub.add_parser(n)
        p.add_argument('dir')
        if n == 'run':
            p.add_argument('--version', default='v1')
            p.add_argument('--dry-run', action='store_true')
            p.add_argument('--only', default='')
            p.add_argument('--redo', default='')
        if n == 'approve':
            p.add_argument('--evidence', required=True)
    a = ap.parse_args()
    if a.cmd == 'check':
        c = load(a.dir)
        e = validate(c, a.dir)
        print('\n'.join(e) if e else 'OK')
        return 2 if e else 0
    if a.cmd == 'status':
        print(json.dumps(load_state(a.dir), indent=1))
        return 0
    if a.cmd == 'approve':
        cmd_approve(a.dir, a.evidence)
        return 0
    return cmd_run(a.dir, a.version, a.dry_run, [x for x in a.only.split(',') if x], [x for x in a.redo.split(',') if x])


if __name__ == '__main__':
    sys.exit(main())
