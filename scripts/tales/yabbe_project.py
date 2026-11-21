#!/usr/bin/env python3
"""Build or update a YABBE project from a tale production directory.

Automatic pipeline step, run after the montage: places every scene segment
on a video track (overlap + opacity-keyframe crossfades, NOT YABBE
transitions which render a black frame at the cut), the narration as
PER-SENTENCE clips on a voice track at their original timeline positions
(from voix/phrases.json, written by split_narration.py; falls back to the
single narration-complete.wav when phrases are absent), the music ducked
on its own track, and the subtitles as editable text clips.

Usage:
  yabbe_project.py build PRODUCTION_DIR --name "Conte 5 v2" [--api http://127.0.0.1:8000/api]
  yabbe_project.py update-voice PRODUCTION_DIR --project p_XXXX [--api ...]

build prints the new project id. update-voice replaces only the clips on
the voice track of an existing project (other edits are preserved) and is
a no-op when voix/phrases.json is missing.
"""
import argparse, json, urllib.parse, urllib.request
from pathlib import Path

INTRO = 1.0


def api(base, method, path, body=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method)
    if data is not None:
        req.add_header('Content-Type', 'application/octet-stream' if raw is not None else 'application/json')
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def upload(base, pid, path):
    a = api(base, 'POST', '/projects/%s/media?filename=%s' % (pid, urllib.parse.quote(path.name)),
            raw=path.read_bytes())
    return a['id']


def seg_durations(root):
    import subprocess
    out = []
    for i in range(1, 100):
        p = root / 'segments' / ('seg-%02d.mp4' % i)
        if not p.exists():
            break
        r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                            '-of', 'csv=p=0', str(p)], capture_output=True, text=True)
        out.append(float(r.stdout.strip()))
    return out


def voice_clips(root, assets, track_id, total):
    """One clip per sentence at its original timeline position (phrases.json),
    or the single narration file when the split step did not run."""
    ph = root / 'voix' / 'phrases.json'
    if ph.exists():
        clips = []
        for j, p in enumerate(json.loads(ph.read_text())):
            clips.append({'id': 'c_ph%02d' % j, 'track_id': track_id, 'type': 'audio',
                          'asset_id': assets[p['file'].split('/')[-1]], 'start': p['start'],
                          'duration': p['duration'], 'in_point': 0.0, 'volume': 1.0})
        return clips
    return [{'id': 'c_voice', 'track_id': track_id, 'type': 'audio',
             'asset_id': assets['narration-complete.wav'], 'start': 0.0,
             'duration': total, 'in_point': 0.0, 'volume': 1.0}]


def build(args):
    root = Path(args.production_dir)
    durs = seg_durations(root)
    assert durs, 'no segments/seg-NN.mp4 - run the montage first'
    total = sum(durs) - 0.5 * (len(durs) - 1)
    proj = api(args.api, 'POST', '/projects', body={'name': args.name})
    pid = proj['id']

    files = [root / 'segments' / ('seg-%02d.mp4' % (i + 1)) for i in range(len(durs))]
    ph = root / 'voix' / 'phrases.json'
    if ph.exists():
        files += [root / p['file'] for p in json.loads(ph.read_text())]
    else:
        files.append(root / 'voix' / '..' / 'narration-complete.wav')
        files[-1] = root / 'narration-complete.wav'
    music = next((root / 'musique').glob('*.mp3'))
    files.append(music)
    assets = {f.name: upload(args.api, pid, f) for f in files}
    print('uploaded', len(assets), 'assets')

    clips, pos = [], 0.0
    tv = 'TRACK_VIDEO'
    for i, d in enumerate(durs):
        c = {'id': 'c_seg%02d' % (i + 1), 'track_id': tv, 'type': 'video',
             'asset_id': assets['seg-%02d.mp4' % (i + 1)], 'start': round(pos, 6),
             'duration': d, 'in_point': 0.0}
        if i > 0:  # crossfade = overlap + opacity ramp (YABBE transitions render a black frame)
            c['keyframes'] = {'opacity': [{'t': 0.0, 'v': 0.0, 'ease': 'linear'},
                                          {'t': 0.5, 'v': 1.0, 'ease': 'linear'}]}
        clips.append(c)
        pos += d - (0.5 if i < len(durs) - 1 else 0.0)

    events = json.loads((root / 'subtitle-events.json').read_text())
    for j, e in enumerate(events):
        clips.append({'id': 'c_sub%02d' % j, 'track_id': 'TRACK_TEXT', 'type': 'text',
                      'start': round(e['start'], 6), 'duration': round(e['end'] - e['start'], 6),
                      'text': {'content': e['text'], 'font': 'DejaVu Sans', 'size': 34,
                               'color': '#ffffff', 'stroke_color': '#000000', 'stroke_width': 2,
                               'align': 'center'},
                      'transform': {'x': 0.0, 'y': 315.0, 'scale': 1.0}})
    clips += voice_clips(root, assets, 'TRACK_VOICE', total)
    clips.append({'id': 'c_music', 'track_id': 'TRACK_MUSIC', 'type': 'audio',
                  'asset_id': assets[music.name], 'start': 0.0, 'duration': total,
                  'in_point': 0.0, 'volume': args.music_volume, 'fade_in': 1.5, 'fade_out': 3.0})

    proj = api(args.api, 'GET', '/projects/%s' % pid)
    seq = proj['sequences'][0]
    seq['settings'] = {'width': args.width, 'height': args.height, 'fps': args.fps, 'background': '#000000'}
    t1, t2, ta = seq['tracks'][0], seq['tracks'][1], seq['tracks'][2]
    t1.update(name='Sous-titres')
    t2.update(name='Scenes')
    ta.update(name='Voix')
    tm = {'id': 't_music', 'kind': 'audio', 'name': 'Musique', 'muted': False, 'hidden': False, 'locked': False}
    seq['tracks'] = [t1, t2, ta, tm]
    idmap = {'TRACK_TEXT': t1['id'], 'TRACK_VIDEO': t2['id'], 'TRACK_VOICE': ta['id'], 'TRACK_MUSIC': 't_music'}
    for c in clips:
        c['track_id'] = idmap[c['track_id']]
    seq['clips'] = clips
    api(args.api, 'PUT', '/projects/%s' % pid, body=proj)
    print('BUILD DONE', pid, len(clips), 'clips, total', round(total, 3))


def update_voice(args):
    root = Path(args.production_dir)
    ph = root / 'voix' / 'phrases.json'
    if not ph.exists():
        print('no voix/phrases.json - run split_narration.py first; nothing changed')
        return
    proj = api(args.api, 'GET', '/projects/%s' % args.project)
    seq = proj['sequences'][0]
    voice_track = next(t for t in seq['tracks'] if t['kind'] == 'audio' and 'voix' in t['name'].lower()
                       or t['kind'] == 'audio' and t['id'] != 't_music')
    assets = {p['file'].split('/')[-1]: upload(args.api, args.project, root / p['file'])
              for p in json.loads(ph.read_text())}
    total = sum(c['duration'] for c in seq['clips'] if c['type'] == 'video')  # unused, kept simple
    new = voice_clips(root, assets, voice_track['id'], 0.0)
    seq['clips'] = [c for c in seq['clips'] if c['track_id'] != voice_track['id']] + new
    api(args.api, 'PUT', '/projects/%s' % args.project, body=proj)
    print('VOICE TRACK UPDATED:', len(new), 'sentence clips on', voice_track['name'],
          'from', new[0]['start'], 'to', round(new[-1]['start'] + new[-1]['duration'], 3))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    pb = sub.add_parser('build')
    pb.add_argument('production_dir')
    pb.add_argument('--api', default='http://127.0.0.1:8000/api')
    pb.add_argument('--name', required=True)
    pb.add_argument('--width', type=int, default=704)
    pb.add_argument('--height', type=int, default=832)
    pb.add_argument('--fps', type=float, default=24.0)
    pb.add_argument('--music-volume', type=float, default=0.12)
    pu = sub.add_parser('update-voice')
    pu.add_argument('production_dir')
    pu.add_argument('--api', default='http://127.0.0.1:8000/api')
    pu.add_argument('--project', required=True)
    args = ap.parse_args()
    (build if args.cmd == 'build' else update_voice)(args)


if __name__ == '__main__':
    main()
