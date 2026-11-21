#!/usr/bin/env python3
"""Word-level subtitle alignment for a tale production.

Runs faster-whisper with word timestamps on each sentence take
(voix/phrases/phrase-NN.wav, one known sentence per file), and places the
resulting word times at the phrase's timeline position from voix/phrases.json
(the same positions the montage and the YABBE voice track already use).
Per-sentence forced alignment on short clips avoids the timestamp drift of a
single long transcription pass.

Subtitle chunks are built from real word times: a chunk starts when its first
word is spoken and ends 0.12 s after its last word. Chunks are capped at
--max-chars characters and at most 2 display lines of --max-line-chars
(wrapping itself is a renderer concern: yabbe_project.py rebuild-subs wraps
for YABBE text clips, the montage wraps for ASS).

Writes <production_dir>/subtitle-events.json (same {start, end, text} shape
the montage and yabbe_project.py already consume); the previous file is kept
once as subtitle-events-weighted.json. Per-phrase whisper results are cached
in voix/whisper-cache/ so re-runs only redo missing phrases.

Needs: faster-whisper (see whisper-venv on the host).
"""
import argparse, difflib, json, re, subprocess, unicodedata
from pathlib import Path


def norm(w):
    w = unicodedata.normalize('NFKD', w.lower())
    w = ''.join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9']", '', w)


def join_fr(tokens):
    """Join display tokens the French way: no space after an apostrophe."""
    out = ''
    for t in tokens:
        if out and not out.endswith("'") and not out.endswith('’'):
            out += ' '
        out += t
    return out


def freest_gpu():
    import subprocess
    try:
        out = subprocess.run(
            ['nvidia-smi', '--query-gpu=index,memory.used', '--format=csv,noheader,nounits'],
            capture_output=True, text=True).stdout
        rows = [(int(l.split(',')[0]), int(l.split(',')[1])) for l in out.strip().splitlines()]
        return min(rows, key=lambda r: r[1])[0]
    except Exception:
        return 0


def speech_bounds(path):
    """(onset, end) of actual speech in a take, from silence detection."""
    r = subprocess.run(['ffmpeg', '-i', str(path), '-af',
                        'silencedetect=noise=-35dB:d=0.12', '-f', 'null', '-'],
                       capture_output=True, text=True)
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                                'format=duration', '-of', 'csv=p=0', str(path)],
                               capture_output=True, text=True).stdout.strip())
    starts = [float(m) for m in re.findall(r'silence_start: ([\d.]+)', r.stderr)]
    ends = [float(m) for m in re.findall(r'silence_end: ([\d.]+)', r.stderr)]
    onset = ends[0] if starts and starts[0] < 0.05 and ends else 0.0
    end = starts[-1] if starts and (not ends or ends[-1] < starts[-1]) else dur
    if ends and starts and ends[-1] > starts[-1]:
        end = dur  # last detected event was a silence_end: speech runs to EOF
    return onset, end, dur


def phrase_words(model, path, sentence):
    """Whisper word times for one phrase file + alignment onto the known
    sentence. Returns (raw whisper words, [(exp_idx, word_idx)], n_exp)."""
    segs, _ = model.transcribe(str(path), language='fr', beam_size=5,
                               word_timestamps=True, condition_on_previous_text=False,
                               initial_prompt=sentence)
    words = [{'start': w.start, 'end': w.end, 'word': w.word}
             for s in segs for w in (s.words or [])]
    exp = sentence.split()
    sm = difflib.SequenceMatcher(a=[norm(t) for t in exp],
                                 b=[norm(w['word']) for w in words], autojunk=False)
    pairs = []
    for tag, a0, a1, b0, b1 in sm.get_opcodes():
        if tag == 'equal':
            pairs += [(a0 + k, b0 + k) for k in range(a1 - a0)]
        else:
            pairs += [(a0 + k, b0 + k) for k in range(min(a1 - a0, b1 - b0))]
    return words, pairs, len(exp)


def token_times(exp, words, pairs, file_dur):
    """Per-token (start, end): whisper times on matched tokens, linear
    interpolation across unmatched runs between matched anchors; the run
    before the first anchor starts at 0, after the last ends at file_dur."""
    times = {ai: (words[bi]['start'], words[bi]['end']) for ai, bi in pairs}
    out = []
    anchors = sorted(times)
    for i in range(len(exp)):
        if i in times:
            out.append(times[i])
            continue
        prev = max([a for a in anchors if a < i], default=None)
        nxt = min([a for a in anchors if a > i], default=None)
        lo_t, lo_i = (times[prev][1], prev) if prev is not None else (0.0, -1)
        hi_t, hi_i = (times[nxt][0], nxt) if nxt is not None else (file_dur, len(exp))
        f = (i - lo_i) / (hi_i - lo_i)
        t = lo_t + (hi_t - lo_t) * f
        out.append((t, t))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('production_dir')
    ap.add_argument('--model', default='medium')
    ap.add_argument('--max-chars', type=int, default=48)
    ap.add_argument('--max-line-chars', type=int, default=26)
    ap.add_argument('--device', default='cuda')
    args = ap.parse_args()
    root = Path(args.production_dir)
    phrases = json.loads((root / 'voix' / 'phrases.json').read_text())
    cache_dir = root / 'voix' / 'whisper-cache'
    cache_dir.mkdir(exist_ok=True)

    from faster_whisper import WhisperModel
    kw = {} if args.device == 'cpu' else {'device_index': freest_gpu()}
    model = WhisperModel(args.model, device=args.device,
                         compute_type='int8' if args.device == 'cpu' else 'float16', **kw)

    events = []
    total_ok = total_exp = 0
    for pi, p in enumerate(phrases, start=1):
        cache = cache_dir / ('phrase-%02d.json' % pi)
        if cache.exists():
            d = json.loads(cache.read_text())
            words, pairs, n_exp = d['words'], [tuple(x) for x in d['pairs']], d['n_exp']
        else:
            words, pairs, n_exp = phrase_words(model, root / p['file'], p['sentence'])
            cache.write_text(json.dumps({'n_exp': n_exp, 'words': words, 'pairs': pairs},
                                        ensure_ascii=False))
        n_ok = len(pairs)
        total_ok += n_ok
        total_exp += n_exp
        exp = p['sentence'].split()
        on, off, fdur = speech_bounds(root / p['file'])
        tt = token_times(exp, words, pairs, fdur)
        # sanity against the energy bounds: whisper timestamps are only
        # trusted when both ends of the sentence land on the real speech span;
        # otherwise shift (constant offset) or rescale them onto it
        w0, w1 = tt[0][0], tt[-1][1]
        fix = 'trusted'
        if not (-0.2 <= w0 - on <= 0.6 and abs(w1 - off) <= 0.9):
            d = on - w0
            if abs((w1 + d) - off) <= 0.9:
                tt = [(a + d, b + d) for a, b in tt]
                fix = 'shift %+.2fs' % d
            else:
                if w1 - w0 < 0.3:  # collapsed whisper span: even spread
                    tt = [(on + (off - on) * i / max(1, len(exp) - 1),
                           on + (off - on) * i / max(1, len(exp) - 1))
                          for i in range(len(exp))]
                    fix = 'even-spread'
                else:
                    k = (off - on) / (w1 - w0)
                    tt = [(on + (a - w0) * k, on + (b - w0) * k) for a, b in tt]
                    fix = 'rescale x%.2f' % k
        words = [{'tok': tok, 'start': tt[i][0], 'end': tt[i][1]}
                 for i, tok in enumerate(exp)]
        t0 = p['start']
        # chunk the sentence's words: <= max-chars, break preferred after , ; :
        toks, chunks = [], []
        for w in words:
            cand = toks + [w]
            if toks and len(join_fr([x['tok'] for x in cand])) > args.max_chars:
                chunks.append(toks)
                toks = [w]
            else:
                toks = cand
            if re.search(r"[,;:]$", w['tok']) and \
               len(join_fr([x['tok'] for x in toks])) >= 14:
                chunks.append(toks)
                toks = []
        if toks:
            chunks.append(toks)
        ph_events = []
        for ci, ch in enumerate(chunks):
            text = join_fr([x['tok'] for x in ch])
            # 2-line display check at render width
            lines, cur = [], ''
            for t in text.split(' '):
                c = (cur + ' ' + t).strip()
                if cur and len(c) > args.max_line_chars:
                    lines.append(cur)
                    cur = t
                else:
                    cur = c
            lines.append(cur)
            assert len(lines) <= 2, 'chunk needs >2 lines: %s' % text
            st = t0 + ch[0]['start']
            if ci + 1 < len(chunks):  # stay up until the next chunk's word
                en = t0 + chunks[ci + 1][0]['start'] - 0.04
            else:  # phrase-final: stay until the speech really ends, plus tail
                en = t0 + off + 0.35
            assert en >= t0 + ch[-1]['end'] - 0.05, \
                'chunk ends before its last word: %s' % text
            ph_events.append({'start': round(st, 3), 'end': round(en, 3),
                              'text': text})
        events += ph_events
        print('phrase %02d: %d/%d tokens, %d chunk(s), %.3f -> %.3f (%s)'
              % (pi, n_ok, n_exp, len(chunks), ph_events[0]['start'],
                 ph_events[-1]['end'], fix), flush=True)
    print('tokens aligned: %d/%d (%.1f%%)' % (total_ok, total_exp, 100.0*total_ok/total_exp))
    assert total_ok >= 0.7 * total_exp, 'alignment too poor - inspect'

    events.sort(key=lambda e: e['start'])
    for n in range(1, len(events)):
        if events[n - 1]['end'] > events[n]['start'] - 0.04:
            events[n - 1]['end'] = round(events[n]['start'] - 0.04, 3)
        assert events[n]['start'] >= events[n - 1]['start'], 'non-monotonic'

    dest = root / 'subtitle-events.json'
    bak = root / 'subtitle-events-weighted.json'
    if dest.exists() and not bak.exists():
        import shutil
        shutil.copy2(dest, bak)
    dest.write_text(json.dumps(events, ensure_ascii=False, indent=1))
    print('WROTE', dest, len(events), 'chunks,',
          events[0]['start'], '->', events[-1]['end'])


if __name__ == '__main__':
    main()
