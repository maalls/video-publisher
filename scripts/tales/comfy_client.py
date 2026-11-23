"""Petit client ComfyUI (stdlib) avec journal par element et mesure de duree.

Un element = un workflow soumis. Le journal <nom>.receipt.json garde l'intention,
le prompt_id et les sorties : jamais de double soumission (meme regle que les
anciens scripts conteNN-*.py). Attente par interrogation de /history toutes les
POLL secondes (2 s par defaut, contre 15 s avant) : ce n'est pas un evenement
WebSocket (la lib n'est pas installee), mais la mesure est precise a 2 s pres.
"""
import json, os, time, urllib.request, uuid
from pathlib import Path

API = os.environ.get('COMFY_API', 'http://127.0.0.1:8188')
POLL = float(os.environ.get('COMFY_POLL', '2'))


def call(path, data=None, api=None):
    req = urllib.request.Request((api or API) + path,
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def upload(local, remote, api=None):
    b = uuid.uuid4().hex.encode()
    body = (b'--' + b + b'\r\nContent-Disposition: form-data; name="image"; filename="' + remote.encode()
            + b'"\r\nContent-Type: image/png\r\n\r\n' + Path(local).read_bytes() + b'\r\n--' + b
            + b'\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n--' + b + b'--\r\n')
    req = urllib.request.Request((api or API) + '/upload/image', data=body,
                                 headers={'Content-Type': 'multipart/form-data; boundary=' + b.decode()})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def run_one(journal, workflow, label, timeout_s=3600, api=None, log=print):
    """Soumet (une seule fois) et attend. Retourne les sorties. Duree dans le journal."""
    journal = Path(journal)
    if journal.exists():
        r = json.loads(journal.read_text())
        if r.get('outputs'):
            return r['outputs']
        if not r.get('prompt_id'):
            raise RuntimeError('Intention de soumission inconnue, pas de reprise automatique: ' + label)
    else:
        journal.write_text(json.dumps({'phase': 'intent'}))
        resp = call('/prompt', {'prompt': workflow}, api)
        r = {'phase': 'submitted', 'prompt_id': resp['prompt_id'], 'submitted_at': time.time()}
        journal.write_text(json.dumps(r))
    journal.with_name(journal.name.replace('.receipt.json', '.workflow.json')).write_text(
        json.dumps(workflow, ensure_ascii=False, indent=2))
    log('%s soumis %s' % (label, r['prompt_id']))
    t0 = r.get('submitted_at', time.time())
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        h = call('/history/' + r['prompt_id'], api=api).get(r['prompt_id'])
        if h:
            if h.get('status', {}).get('status_str') == 'error':
                raise RuntimeError('ComfyUI erreur sur %s: %s' % (label, str(h['status'])[:300]))
            done = time.time()
            r.update(phase='done', outputs=h.get('outputs', {}), done_at=done, seconds=round(done - t0, 1))
            journal.write_text(json.dumps(r))
            log('%s termine en %.0f s' % (label, done - t0))
            return r['outputs']
        time.sleep(POLL)
    raise RuntimeError('Delai depasse, journal conserve: ' + label)


def first_file(outputs, ext):
    for node in outputs.values():
        for key in ('images', 'videos', 'gifs'):
            for m in node.get(key, []):
                if m['filename'].endswith(ext):
                    return m
    raise KeyError('aucune sortie ' + ext)
