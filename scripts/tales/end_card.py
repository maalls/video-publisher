#!/usr/bin/env python3
"""Append the standard "Les 1001 Contes" end card to a tale's YABBE project.

The end card is the closing grammar of every tale: after the last scene, a
short slide (channel logo + generic CTA text) with the spoken CTA on the
voice track, then a fade to black. Shared assets are built ONCE and cached
in var/project/tales/endcard/ (rebuild them there if the CTA text, voice or
logo ever changes):

  endcard.png   704x832 still (logo, "Les 1001 Contes", OUTRO_TEXT)
  endcard.mp4   the still as a 24 fps video (CARD_DUR seconds)
  outro-cta.wav spoken CTA (Gemini Sadaltager), trimmed with fades, 48 kHz

The step is idempotent: it does nothing when a clip id c_endcard exists.
It extends the music clip to the new end (the music fade-out then applies
at the new end), appends the CTA to narration-complete.wav and records the
outro in voix/phrases.json (flag "outro": true so subtitle alignment skips
it: the card itself carries the text, no subtitle clip is created).

Usage:
  end_card.py PRODUCTION_DIR --project p_XXXX [--api http://127.0.0.1:8000/api]
"""
import argparse, json, copy, urllib.request, urllib.parse, subprocess
from pathlib import Path

OUTRO_TEXT = 'Un nouveau conte chaque jour. Abonne-toi pour ne pas rater le prochain !'
ASSETS = Path(__file__).resolve().parents[2] / 'var' / 'project' / 'tales' / 'endcard'
CARD_DUR = 6.125          # card video length (s)
OUTRO_DELAY = 0.625       # CTA audio starts this far into the card
CARD_FADE_IN = 0.5
CARD_FADE_OUT = 1.0


def api(base, method, path, body=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method)
    if data is not None:
        req.add_header('Content-Type', 'application/octet-stream' if raw is not None else 'application/json')
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def duration(path):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                 '-of', 'csv=p=0', str(path)], capture_output=True, text=True).stdout.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('production_dir')
    ap.add_argument('--api', default='http://127.0.0.1:8000/api')
    ap.add_argument('--project', required=True)
    args = ap.parse_args()
    root = Path(args.production_dir)
    card_mp4, cta_wav = ASSETS / 'endcard.mp4', ASSETS / 'outro-cta.wav'
    assert card_mp4.exists() and cta_wav.exists(), 'build shared assets in %s first' % ASSETS

    proj = api(args.api, 'GET', '/projects/%s' % args.project)
    seq = [s for s in proj['sequences'] if s['id'] == proj['main_sequence_id']][0]
    if any(c['id'] == 'c_endcard' for c in seq['clips']):
        print('end card already present; nothing changed')
        return
    scene_track = next(t['id'] for t in seq['tracks'] if t['name'] == 'Scenes')
    voice_track = next(t['id'] for t in seq['tracks'] if t['name'] == 'Voix')
    scenes = [c for c in seq['clips'] if c['track_id'] == scene_track]
    last_scene = max(scenes, key=lambda c: c['start'] + c['duration'])
    card_start = last_scene['start'] + last_scene['duration']
    outro_dur = duration(cta_wav)
    outro_start = card_start + OUTRO_DELAY
    new_end = card_start + duration(card_mp4)
    assert outro_start + outro_dur <= new_end - 0.5, 'CTA audio does not fit the card'

    def upload(path):
        return api(args.api, 'POST', '/projects/%s/media?filename=%s'
                   % (args.project, urllib.parse.quote(path.name)), raw=path.read_bytes())['id']

    card_asset, cta_asset = upload(card_mp4), upload(cta_wav)

    def kf(t, v):
        return {'t': t, 'v': v, 'c': None, 'ease': 'linear', 'hi': None, 'ho': None, 'hm': None, 'ep': None}

    card = copy.deepcopy(last_scene)
    card.update({'id': 'c_endcard', 'asset_id': card_asset, 'start': card_start,
                 'duration': duration(card_mp4), 'in_point': 0.0})
    card['keyframes'] = {'opacity': [kf(0.0, 0.0), kf(CARD_FADE_IN, 1.0),
                                     kf(duration(card_mp4) - CARD_FADE_OUT, 1.0),
                                     kf(duration(card_mp4), 0.0)]}
    voice_ref = max([c for c in seq['clips'] if c['track_id'] == voice_track],
                    key=lambda c: c['start'])
    outro = copy.deepcopy(voice_ref)
    outro.update({'id': 'c_outro', 'asset_id': cta_asset, 'start': outro_start,
                  'duration': outro_dur, 'in_point': 0.0})
    outro['keyframes'] = {}
    music = [c for c in seq['clips'] if c['track_id'] == 't_music']
    if music:
        music[0]['duration'] = max(music[0]['duration'], new_end)
    seq['clips'].extend([card, outro])
    api(args.api, 'PUT', '/projects/%s' % args.project, body=proj)

    narr = root / 'narration-complete.wav'
    if narr.exists():
        backup = narr.with_suffix('.avant-outro.wav')
        if not backup.exists():
            backup.write_bytes(narr.read_bytes())
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(backup), '-i', str(cta_wav),
                        '-filter_complex',
                        '[0:a]apad[base];[1:a]adelay=%(d)d|%(d)d[o];'
                        '[base][o]amix=inputs=2:normalize=0,atrim=0:%(e).3f,apad=whole_dur=%(e).3f'
                        % {'d': int(outro_start * 1000), 'e': new_end},
                        '-ar', '48000', str(narr)], check=True)
    ph = root / 'voix' / 'phrases.json'
    if ph.exists():
        phrases = json.loads(ph.read_text())
        if not any(p.get('outro') for p in phrases):
            phrases.append({'file': str(cta_wav), 'segment': 0, 'sentence': OUTRO_TEXT,
                            'start': round(outro_start, 3), 'duration': round(outro_dur, 3),
                            'outro': True})
            ph.write_text(json.dumps(phrases, ensure_ascii=False, indent=1))
    print('END CARD ADDED: card %.3f-%.3f, CTA audio %.3f-%.3f, music extended to %.3f'
          % (card_start, new_end, outro_start, outro_start + outro_dur, new_end))


if __name__ == '__main__':
    main()
