#!/usr/bin/env python3
"""Publication unique d'un conte valide : YouTube + Instagram + brouillon TikTok.

  publish_conte.py DIR --at 2026-11-24T19:00                       -> PLAN seulement (rien n'est envoye)
  publish_conte.py DIR --at ... --execute --go-evidence "message de Malo ..."

Garde-fous : approved.json (cree par `launcher.py approve`) doit exister et son sha256 doit
etre celui du master ; --at doit etre dans le futur (heure de Paris) ; --execute exige
--go-evidence (citation du feu vert de Malo pour CETTE heure et ces plateformes).
Aucune publication sans cela. Les textes sont generes depuis conte.json (credit musique,
mention IA, licence CC BY ajoutes automatiquement).
- YouTube : upload prive + publishAt (YouTube publie lui-meme). Journal anti-doublon.
- Instagram : derive faststart AAC 112k + cover 9:16, mini-serveur + tunnel temporaires, conteneur
  cree maintenant, publication a l'heure par un processus detache (attend l'heure exacte).
- TikTok : processus detache a l'heure +10 s, envoi en brouillon (boite de reception), Malo finalise.
Apres publication : `publish_conte.py DIR --cleanup` arrete serveur/tunnel et supprime les medias temporaires.
"""
import argparse, hashlib, json, os, re, shlex, subprocess, sys, time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TALES = REPO / 'var' / 'project' / 'tales'
PARIS = ZoneInfo('Europe/Paris')
YT_CHANNEL = 'UC4WiTuKuhFMPmHETWVclfww'
PORT = 8791
SERVER = TALES / 'productions' / 'conte02-cheval' / 'publication' / 'temporary-two-media-server.py'


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def sh(cmd, **kw):
    print('RUN', cmd if isinstance(cmd, str) else ' '.join(map(str, cmd)), flush=True)
    return subprocess.run(cmd, check=True, text=True, **kw)


def texts(c):
    pub, mu = c['publication'], c['music']
    footer = ('Images animées et narration créées avec l\'aide de l\'intelligence artificielle.\n\n'
              'Musique : "%s" de %s (incompetech.com).\n'
              'Licence Creative Commons Attribution 4.0 : https://creativecommons.org/licenses/by/4.0/\n'
              'Musique raccourcie, volume ajusté et fondus ajoutés pour cette vidéo.' % (mu['title'], mu['artist']))
    caption = '%s\n\n%s\n\n%s\n\n%s' % (pub['caption'], 'Un nouveau conte chaque jour : suis-nous pour ne pas le manquer !',
                                       pub['hashtags'], footer)
    yt = '%s\n\nUn nouveau conte chaque jour : abonne-toi pour ne pas le manquer !\n\nOrigine : %s\n\n%s\n' % (
        pub['youtube_description'], c.get('origin_short', c.get('origin', '')), footer)
    return caption, yt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dir')
    ap.add_argument('--at', help="heure de Paris, ex. 2026-11-24T19:00")
    ap.add_argument('--platforms', default='youtube,instagram,tiktok')
    ap.add_argument('--execute', action='store_true')
    ap.add_argument('--go-evidence', default='')
    ap.add_argument('--cleanup', action='store_true')
    a = ap.parse_args()
    prod = Path(a.dir).resolve()
    pubdir = prod / 'publication'
    if a.cleanup:
        pubdir.mkdir(exist_ok=True)
        st = json.loads((pubdir / 'publish-state.json').read_text()) if (pubdir / 'publish-state.json').exists() else {}
        for pid in st.get('pids_to_stop', []):
            subprocess.call(['kill', str(pid)])
        if st.get('host'):
            subprocess.call(['rm', '-rf', st['host']])
        print('nettoyage fait (serveur, tunnel, medias temporaires)')
        return 0
    c = json.loads((prod / 'conte.json').read_text())
    ap_json = prod / 'approved.json'
    if not ap_json.exists():
        sys.exit("REFUS: pas d'approved.json (la video n'a pas ete validee par Malo via launcher.py approve)")
    appr = json.loads(ap_json.read_text())
    master = prod / appr['master']
    if sha(master) != appr['sha256']:
        sys.exit('REFUS: le master a change depuis la validation')
    if not a.at:
        sys.exit('--at requis (heure de Paris)')
    when = datetime.fromisoformat(a.at).replace(tzinfo=PARIS)
    if when <= datetime.now(PARIS):
        sys.exit('REFUS: --at est dans le passe')
    plats = [x for x in a.platforms.split(',') if x]
    utc = when.astimezone(ZoneInfo('UTC')).strftime('%Y-%m-%dT%H:%M:%SZ')
    caption, yt_desc = texts(c)
    print('PLAN: %s master=%s sha=%s heure=%s Paris (%s) plateformes=%s' % (c['id'], master.name, appr['sha256'][:12], when, utc, plats))
    print('--- legende ---\n' + caption + '\n--- fin ---')
    if not a.execute:
        print('(plan seulement: ajouter --execute --go-evidence "..." apres feu vert explicite de Malo)')
        return 0
    if len(a.go_evidence.strip()) < 10:
        sys.exit('REFUS: --go-evidence requis (citation du feu vert de Malo pour cette heure et ces plateformes)')
    pubdir.mkdir(exist_ok=True)
    state = {'at': a.at, 'platforms': plats, 'go_evidence': a.go_evidence, 'master': master.name, 'sha256': appr['sha256']}
    (pubdir / 'caption.txt').write_text(caption)
    (pubdir / 'youtube-metadata.json').write_text(json.dumps({
        'title': c['publication']['title'], 'description': yt_desc, 'defaultLanguage': 'fr', 'defaultAudioLanguage': 'fr'},
        ensure_ascii=False, indent=1))
    (prod / 'publication-caption-tiktok.txt').write_text(caption)
    wait = 'while [ $(TZ=Europe/Paris date +%%Y%%m%%d%%H%%M%%S) -lt %s ]; do sleep 1; done' % when.strftime('%Y%m%d%H%M%S')
    wait10 = 'while [ $(TZ=Europe/Paris date +%%Y%%m%%d%%H%%M%%S) -lt %s ]; do sleep 1; done' % datetime.fromtimestamp(when.timestamp() + 10, PARIS).strftime('%Y%m%d%H%M%S')

    if 'youtube' in plats:
        sh([sys.executable, str(HERE / 'upload_youtube_scheduled.py'), str(master), '--metadata', str(pubdir / 'youtube-metadata.json'),
            '--token', str(TALES / 'secrets' / 'youtube-token.json'), '--channel-id', YT_CHANNEL,
            '--journal', str(TALES / 'state' / (c['id'] + '-youtube.json')), '--visibility', 'private', '--made-for-kids', 'no',
            '--publish-at', utc, '--upload'])
        state['youtube_journal'] = c['id'] + '-youtube.json'

    if 'instagram' in plats:
        reel = pubdir / 'instagram-faststart.mp4'
        cover = pubdir / 'cover.jpg'
        sh(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-i', str(master), '-c:v', 'copy', '-c:a', 'aac', '-b:a', '112k', '-ar', '48000',
            '-movflags', '+faststart', str(reel)])
        sh(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-ss', '2.5', '-i', str(master), '-frames:v', '1', str(pubdir / 'frame.png')])
        sh(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-i', str(pubdir / 'frame.png'), '-filter_complex',
            '[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,gblur=sigma=40[bg];[0:v]scale=720:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2',
            '-q:v', '2', str(cover)])
        igs = [sys.executable, str(HERE / 'instagram_unified.py'), '--state-dir', str(TALES / 'state' / 'instagram-unified')]
        base = ['--video', str(reel), '--cover', str(cover), '--caption-file', str(pubdir / 'caption.txt'), '--ai-generated', 'yes', '--share-to-feed', 'yes']
        plan = json.loads(subprocess.check_output(igs + ['plan'] + base, text=True))
        rnd = os.urandom(8).hex()
        host = TALES / 'instagram-media' / ('host-%s-%s' % (c['id'], rnd))
        host.mkdir(parents=True)
        for src, name in ((reel, 'reel-%s.mp4' % rnd), (cover, 'cover-%s.jpg' % rnd)):
            (host / name).write_bytes(src.read_bytes())
        srv = subprocess.Popen([sys.executable, str(SERVER), str(host)], stdout=open(pubdir / 'server.log', 'w'), stderr=subprocess.STDOUT, start_new_session=True)
        tun = subprocess.Popen(['/usr/bin/cloudflared', 'tunnel', '--config', '/dev/null', '--url', 'http://127.0.0.1:%d' % PORT, '--protocol', 'http2', '--no-autoupdate'],
                               stdout=open(pubdir / 'tunnel.log', 'w'), stderr=subprocess.STDOUT, start_new_session=True)
        state.update(host=str(host), pids_to_stop=[srv.pid, tun.pid])
        (pubdir / 'publish-state.json').write_text(json.dumps(state, indent=1))
        url = None
        for _ in range(60):
            m = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', (pubdir / 'tunnel.log').read_text())
            if m:
                url = m.group(0)
                break
            time.sleep(1)
        if not url:
            sys.exit('tunnel indisponible: rien cree sur Instagram (YouTube deja programme si demande)')
        time.sleep(3)
        import urllib.request
        for name, local in (('reel-%s.mp4' % rnd, reel), ('cover-%s.jpg' % rnd, cover)):
            h = hashlib.sha256(urllib.request.urlopen(url + '/' + name, timeout=60).read()).hexdigest()
            if h != sha(local):
                sys.exit('sha256 servi different pour ' + name)
        sh(igs + ['create'] + base + ['--video-url', url + '/reel-%s.mp4' % rnd, '--cover-url', url + '/cover-%s.jpg' % rnd,
                                      '--execute', '--confirm-plan', plan['plan_sha256']])
        journal = REPO / plan['journal'] if not Path(plan['journal']).is_absolute() else Path(plan['journal'])
        for _ in range(40):
            stt = json.loads(subprocess.check_output(igs + ['status', '--journal', str(journal)], text=True).splitlines()[-1])
            if stt.get('container_status') == 'FINISHED':
                break
            time.sleep(10)
        else:
            sys.exit('conteneur Instagram pas FINISHED, rien publie')
        script = pubdir / 'arm-instagram.sh'
        script.write_text('#!/bin/bash\ncd %s\n%s\necho "start $(date -Is)"\n%s\necho "end $(date -Is)"\n' % (
            shlex.quote(str(REPO)), wait, ' '.join(shlex.quote(x) for x in igs + ['publish', '--journal', str(journal), '--execute', '--confirm-plan', plan['plan_sha256']])))
        script.chmod(0o755)
        subprocess.Popen([str(script)], stdout=open(pubdir / 'arm-instagram.log', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        state['instagram_journal'] = str(journal)

    if 'tiktok' in plats:
        script = pubdir / 'arm-tiktok.sh'
        script.write_text('#!/bin/bash\ncd %s\n%s\necho "start $(date -Is)"\nPYTHONPATH=%s %s %s %s\necho "end $(date -Is)"\n' % (
            shlex.quote(str(TALES)), wait10, shlex.quote(str(REPO / 'src')), shlex.quote(str(REPO / '.venv' / 'bin' / 'python')),
            shlex.quote(str(HERE / 'tiktok_inbox_send.py')), shlex.quote(str(master))))
        script.chmod(0o755)
        subprocess.Popen([str(script)], stdout=open(pubdir / 'arm-tiktok.log', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    (pubdir / 'publish-state.json').write_text(json.dumps(state, indent=1))
    print('ARME: %s a %s Paris. Verifier apres l\'heure, puis --cleanup.' % (plats, when))
    return 0


if __name__ == '__main__':
    sys.exit(main())
