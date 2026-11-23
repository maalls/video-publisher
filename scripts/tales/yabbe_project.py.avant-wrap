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


def retime_subtitles(events, phrases, segments):
    """Re-time subtitle events (text-length-weighted estimates from the montage)
    onto the REAL sentence spans measured by split_narration.py. Position inside
    a sentence is interpolated by character count."""
    by_seg = {}
    for p in phrases:
        by_seg.setdefault(p['segment'], []).append(p)
    # per segment: sentence -> (char_start, char_end, real_start, real_end)
    maps = {}
    for si, text in enumerate(segments, start=1):
        spans, cur = [], 0
        import re as _re
        for s in [x.strip() for x in _re.split(r'(?<=[.!?…]) ', text) if x.strip()]:
            i = text.index(s, cur)
            ph = by_seg[si][len(spans)]
            spans.append((i, i + len(s), ph['start'], ph['start'] + ph['duration']))
            cur = i + len(s)
        maps[si] = spans
    def t_of(si, pos):
        for c0, c1, t0, t1 in maps[si]:
            if pos <= c1:
                return t0 + (max(pos, c0) - c0) / max(1, c1 - c0) * (t1 - t0)
        return maps[si][-1][3]
    out, si, cur = [], 1, 0
    for e in events:
        text = e['text']
        while True:
            seg_text = segments[si - 1]
            try:
                i = seg_text.index(text[:12], cur)
                break
            except ValueError:
                si += 1
                cur = 0
        start, end = t_of(si, i), t_of(si, i + len(text) - 1)
        out.append({'start': round(start, 6), 'end': round(end, 6), 'text': text})
        cur = i + len(text)
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
    ph = root / 'voix' / 'phrases.json'
    if ph.exists():  # real sentence timings beat weighted estimates
        segments = json.loads((root / 'narration.json').read_text())['segments']
        events = retime_subtitles(events, json.loads(ph.read_text()), segments)
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


def update_subs(args):
    """Re-time the subtitle text clips of an existing project onto the real
    sentence spans (voix/phrases.json). Only text clips are touched."""
    root = Path(args.production_dir)
    ph = root / 'voix' / 'phrases.json'
    if not ph.exists():
        print('no voix/phrases.json - run split_narration.py first; nothing changed')
        return
    events = json.loads((root / 'subtitle-events.json').read_text())
    segments = json.loads((root / 'narration.json').read_text())['segments']
    real = retime_subtitles(events, json.loads(ph.read_text()), segments)
    proj = api(args.api, 'GET', '/projects/%s' % args.project)
    seq = proj['sequences'][0]
    subs = sorted([c for c in seq['clips'] if c['type'] == 'text'], key=lambda c: c['start'])
    assert len(subs) == len(real), (len(subs), len(real))
    for c, e in zip(subs, real):
        assert c['text']['content'] == e['text'], (c['text']['content'], e['text'])
        c['start'], c['duration'] = e['start'], round(e['end'] - e['start'], 6)
    api(args.api, 'PUT', '/projects/%s' % args.project, body=proj)
    print('SUBTITLES RETIMED:', len(real), 'clips on real sentence timings')


SUB_MAX_LINE = 26  # max chars per display line (fits 704px at DejaVu Sans 34)


def wrap_sub(text, max_line=SUB_MAX_LINE):
    """Wrap a subtitle for display: at most 2 lines of <= max_line chars,
    break at a word boundary, prefer breaking after a comma/semicolon."""
    if len(text) <= max_line:
        return text
    words = text.split(' ')
    best = None
    for j in range(1, len(words)):
        l1, l2 = ' '.join(words[:j]), ' '.join(words[j:])
        if len(l1) > max_line or len(l2) > max_line:
            continue
        pref = 0 if words[j - 1].endswith((',', ';', ':')) else 1
        score = (pref, abs(len(l1) - len(l2)))
        if best is None or score < best[0]:
            best = (score, l1, l2)
    if best is None:
        raise AssertionError('subtitle does not fit 2 lines: %s' % text)
    return best[1] + '\n' + best[2]


def rebuild_subs(args):
    """Rebuild every subtitle text clip from subtitle-events.json (word-level
    timings written by align_subtitles.py). Text clips are deleted and
    recreated; every other track is left untouched. The text style is copied
    from the first existing text clip when present."""
    root = Path(args.production_dir)
    events = json.loads((root / 'subtitle-events.json').read_text())
    proj = api(args.api, 'GET', '/projects/%s' % args.project)
    seq = proj['sequences'][0]
    subs = sorted([c for c in seq['clips'] if c['type'] == 'text'], key=lambda c: c['start'])
    if subs:
        template = subs[0]
        style, transform, track_id = template['text'], template['transform'], template['track_id']
    else:
        track_id = next(t['id'] for t in seq['tracks'] if t['kind'] != 'audio'
                        and 'sous' in t['name'].lower())
        style = {'content': '', 'font': 'DejaVu Sans', 'size': 34, 'color': '#ffffff',
                 'stroke_color': '#000000', 'stroke_width': 2, 'align': 'center'}
        transform = {'x': 0.0, 'y': 315.0, 'scale': 1.0}
    new = []
    for j, e in enumerate(events):
        st = dict(style)
        st['content'] = wrap_sub(e['text'])
        new.append({'id': 'c_sub%02d' % j, 'track_id': track_id, 'type': 'text',
                    'start': round(e['start'], 6), 'duration': round(e['end'] - e['start'], 6),
                    'in_point': 0.0, 'speed': 1.0, 'text': st,
                    'transform': dict(transform), 'keyframes': {}})
    seq['clips'] = [c for c in seq['clips'] if c['type'] != 'text'] + new
    api(args.api, 'PUT', '/projects/%s' % args.project, body=proj)
    print('SUBTITLES REBUILT:', len(new), 'clips on word-level timings,',
          new[0]['start'], '->', round(new[-1]['start'] + new[-1]['duration'], 3))


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
    ps = sub.add_parser('update-subs')
    ps.add_argument('production_dir')
    ps.add_argument('--api', default='http://127.0.0.1:8000/api')
    ps.add_argument('--project', required=True)
    pr = sub.add_parser('rebuild-subs')
    pr.add_argument('production_dir')
    pr.add_argument('--api', default='http://127.0.0.1:8000/api')
    pr.add_argument('--project', required=True)
    args = ap.parse_args()
    {'build': build, 'update-voice': update_voice, 'update-subs': update_subs,
     'rebuild-subs': rebuild_subs}[args.cmd](args)


if __name__ == '__main__':
    main()
