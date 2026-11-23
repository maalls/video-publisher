#!/usr/bin/env python3
"""Split a tale's single-take narration into per-sentence audio clips.

Automatic pipeline step: no TTS regeneration, no manual cutting. For each
voix/voix-NN.wav take, silences are detected with ffmpeg; the longest
(n-1) silences become the split points between the n sentences of that
segment (sentence count comes from narration.json, so breath pauses and
comma gaps never split a sentence). Each sentence clip keeps its ORIGINAL
position on the montage timeline (intro offset + cumulative take offset +
span start), so a consumer (e.g. yabbe_project.py) can place every sentence
independently while the overall timing stays identical to the master.

Usage: split_narration.py PRODUCTION_DIR [--intro 1.0] [--noise -35] [--min-silence 0.15]

Writes voix/phrases/phrase-NN.wav and voix/phrases.json:
  [{"file", "segment", "sentence", "text", "start", "duration"}, ...]
"""
import argparse, json, re, subprocess, sys
from pathlib import Path


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def duration(path):
    r = run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'csv=p=0', str(path)])
    return float(r.stdout.strip())


def silences(path, noise_db, min_sil):
    r = run(['ffmpeg', '-i', str(path), '-af',
             f'silencedetect=noise={noise_db}dB:d={min_sil}', '-f', 'null', '-'])
    starts = [float(m.group(1)) for m in re.finditer(r'silence_start: ([\d.]+)', r.stderr)]
    ends = [(float(m.group(1)), float(m.group(2)))
            for m in re.finditer(r'silence_end: ([\d.]+) \| silence_duration: ([\d.]+)', r.stderr)]
    return list(zip(starts, [e[0] for e in ends]))  # (sil_start, sil_end)


def sentences_of(text):
    parts = [x.strip() for x in re.split(r'(?<=[.!?…]) ', text) if x.strip()]
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('production_dir')
    ap.add_argument('--intro', type=float, default=1.0,
                    help='seconds of frozen intro before the voice starts (montage grammar)')
    ap.add_argument('--noise', type=float, default=-35.0)
    ap.add_argument('--min-silence', type=float, default=0.15)
    a = ap.parse_args()
    root = Path(a.production_dir)
    segs = json.loads((root / 'narration.json').read_text())['segments']
    out_dir = root / 'voix' / 'phrases'
    out_dir.mkdir(parents=True, exist_ok=True)

    phrases = []
    take_offset = 0.0
    n_done = 0
    for si, text in enumerate(segs, start=1):
        take = root / 'voix' / ('voix-%02d.wav' % si)
        assert take.exists(), take
        dur = duration(take)
        sents = sentences_of(text)
        sils = silences(take, a.noise, a.min_silence)
        # leading/trailing silences only trim the take; they never split sentences
        lead = next((s for s in sils if s[0] < 0.05), None)
        trail = next((s for s in sils if s[1] > dur - 0.05), None)
        inner = [s for s in sils if s is not lead and s is not trail]
        need = len(sents) - 1
        chosen = []
        if need > 0:
            assert len(inner) >= need, \
                f'{take.name}: {len(inner)} inner silences for {len(sents)} sentences - lower --noise or --min-silence'
            # estimated boundary per sentence: text-length-weighted share of the
            # take (same formula as the montage subtitles), then snap each
            # estimate to the closest real silence, in order
            ws = [len(s) + sum(s.count(c) * 5 for c in '.?!,:;') for s in sents]
            est = [dur * sum(ws[:k]) / sum(ws) for k in range(1, len(sents))]
            chosen = []
            pool = list(inner)
            for e in est:
                best = min(pool, key=lambda s: abs((s[0] + s[1]) / 2 - e))
                pool.remove(best)
                chosen.append(best)
            chosen.sort()
        bounds = []
        prev = lead[1] if lead else 0.0
        for s_start, s_end in chosen:
            bounds.append((prev, s_start))
            prev = s_end
        bounds.append((prev, trail[0] if trail else dur))
        assert len(bounds) == len(sents), (take.name, bounds, sents)
        for (span_s, span_e), sent in zip(bounds, sents):
            n_done += 1
            out = out_dir / ('phrase-%02d.wav' % n_done)
            r = run(['ffmpeg', '-y', '-v', 'error', '-ss', '%.6f' % span_s, '-t', '%.6f' % (span_e - span_s),
                     '-i', str(take), '-c:a', 'pcm_s16le', str(out)])
            assert r.returncode == 0, r.stderr
            phrases.append({'file': str(out.relative_to(root)), 'segment': si,
                            'sentence': sent, 'start': round(a.intro + take_offset + span_s, 6),
                            'duration': round(span_e - span_s, 6)})
        take_offset += dur
    (root / 'voix' / 'phrases.json').write_text(json.dumps(phrases, ensure_ascii=False, indent=2))
    print('SPLIT DONE', len(phrases), 'phrases,',
          'timeline', phrases[0]['start'], '->', round(phrases[-1]['start'] + phrases[-1]['duration'], 3))


if __name__ == '__main__':
    main()
