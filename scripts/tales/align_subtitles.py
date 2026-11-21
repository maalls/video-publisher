#!/usr/bin/env python3
"""Word-level subtitle alignment for a tale production.

Method: one whisper pass with word timestamps over the RENDERED audio (the
exported video's own soundtrack, or narration-complete.wav), then a forced
alignment of the known narration sentences onto the recognised word stream,
sentence by sentence, each confined to a window between the previous
sentence's end and the next sentence's expected start (+margin). Windowing
keeps local mis-hearings from cascading across the video, while the single
global pass avoids the timestamp drift of separate per-clip transcriptions.

Subtitle chunks start at the real first word and stay displayed until the
next chunk's first word (-0.04 s); the last chunk of a sentence stays until
the last word ends +0.35 s tail. Chunks are capped at --max-chars characters
and 2 display lines of --max-line-chars (wrapping is a renderer concern:
yabbe_project.py rebuild-subs wraps for YABBE, the montage wraps for ASS).

Writes <production_dir>/subtitle-events.json ({start, end, text}); the
previous file is kept once as subtitle-events-prev.json. The whisper word
stream is cached in voix/whisper-global-<audiohash>.json.

Fails loudly when a sentence's first words are not heard in the audio
(missing TTS words -> regenerate the take).
"""
import argparse, difflib, hashlib, json, re, subprocess, unicodedata
from pathlib import Path


def norm(w):
    w = unicodedata.normalize('NFKD', w.lower())
    w = ''.join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9']", '', w)


def join_fr(tokens):
    out = ''
    for t in tokens:
        if out and not out.endswith("'") and not out.endswith('’'):
            out += ' '
        out += t
    return out


def freest_gpu():
    try:
        out = subprocess.run(
            ['nvidia-smi', '--query-gpu=index,memory.used', '--format=csv,noheader,nounits'],
            capture_output=True, text=True).stdout
        rows = [(int(l.split(',')[0]), int(l.split(',')[1])) for l in out.strip().splitlines()]
        return min(rows, key=lambda r: r[1])[0]
    except Exception:
        return 0


def whisper_words(audio, cache):
    if cache.exists():
        d = json.loads(cache.read_text())
        print('whisper cache hit:', cache.name)
        return d
    from faster_whisper import WhisperModel
    model = WhisperModel('medium', device='cpu', compute_type='int8')
    segs, _ = model.transcribe(str(audio), beam_size=5,
                               word_timestamps=True, condition_on_previous_text=False,
                               initial_prompt=None)
    words = [{'start': w.start, 'end': w.end, 'word': w.word}
             for s in segs for w in (s.words or [])]
    cache.write_text(json.dumps(words, ensure_ascii=False))
    return words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('production_dir')
    ap.add_argument('--audio', default=None,
                    help='rendered audio/video to align on (default: narration-complete.wav)')
    ap.add_argument('--max-chars', type=int, default=48)
    ap.add_argument('--max-line-chars', type=int, default=26)
    ap.add_argument('--margin', type=float, default=4.0)
    args = ap.parse_args()
    root = Path(args.production_dir)
    audio = Path(args.audio) if args.audio else root / 'narration-complete.wav'
    assert audio.exists(), audio
    phrases = json.loads((root / 'voix' / 'phrases.json').read_text())
    sentences = [p['sentence'] for p in phrases]

    h = hashlib.sha1((str(audio) + str(audio.stat().st_mtime)).encode()).hexdigest()[:10]
    stream = whisper_words(audio, root / 'voix' / ('whisper-global-%s.json' % h))
    print('word stream: %d words, %.2f -> %.2f s'
          % (len(stream), stream[0]['start'], stream[-1]['end']))

    events = []
    cursor = 0.0
    total_ok = total_exp = 0
    for si, sentence in enumerate(sentences):
        exp = sentence.split()
        nxt = (phrases[si + 1]['start'] + args.margin) if si + 1 < len(phrases) \
            else stream[-1]['end'] + 1.0
        win = [w for w in stream if cursor - 0.30 <= w['start'] < nxt]
        assert win, 'no words in window for sentence %d' % (si + 1)
        sm = difflib.SequenceMatcher(a=[norm(t) for t in exp],
                                     b=[norm(w['word']) for w in win], autojunk=False)
        pairs = []
        for tag, a0, a1, b0, b1 in sm.get_opcodes():
            if tag == 'equal':
                pairs += [(a0 + k, b0 + k) for k in range(a1 - a0)]
            else:
                pairs += [(a0 + k, b0 + k) for k in range(min(a1 - a0, b1 - b0))]
        times = {ai: (win[bi]['start'], win[bi]['end']) for ai, bi in pairs}
        first_heard = min(times, default=10**9)
        assert first_heard <= 1, (
            'sentence %d starts in the text but not in the audio - regenerate '
            'the take for: %r') % (si + 1, sentence)
        matched = [i for i in range(len(exp)) if i in times]
        total_ok += len(matched)
        total_exp += len(exp)
        # per-token times with linear interpolation across unmatched runs
        tt = {}
        anchors = sorted(times)
        for i in range(len(exp)):
            if i in times:
                tt[i] = times[i]
                continue
            prev = max([a for a in anchors if a < i], default=None)
            nx = min([a for a in anchors if a > i], default=None)
            lo_t, lo_i = (times[prev][1], prev) if prev is not None else (times[anchors[0]][0], anchors[0])
            hi_t, hi_i = (times[nx][0], nx) if nx is not None else (times[anchors[-1]][1], anchors[-1])
            f = (i - lo_i) / max(1, hi_i - lo_i)
            tt[i] = (lo_t + (hi_t - lo_t) * f,) * 2
        words = [{'tok': exp[i], 'start': tt[i][0], 'end': tt[i][1]} for i in range(len(exp))]
        # chunk: <= max-chars; break after , ; : when long enough or at a real pause
        toks, chunks = [], []
        for j, w in enumerate(words):
            cand = toks + [w]
            if toks and len(join_fr([x['tok'] for x in cand])) > args.max_chars:
                chunks.append(toks)
                toks = [w]
            else:
                toks = cand
            gap = words[j + 1]['start'] - w['end'] if j + 1 < len(words) else 0.0
            if re.search(r"[,;:]$", w['tok']) and toks and \
               (len(join_fr([x['tok'] for x in toks])) >= 12 or gap >= 0.35):
                chunks.append(toks)
                toks = []
        if toks:
            chunks.append(toks)
        for ci, ch in enumerate(chunks):
            text = join_fr([x['tok'] for x in ch])
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
            st = ch[0]['start']
            en = chunks[ci + 1][0]['start'] - 0.04 if ci + 1 < len(chunks) \
                else ch[-1]['end'] + 0.35
            assert en >= ch[-1]['end'] - 0.05, 'chunk ends before its last word: %s' % text
            events.append({'start': round(st, 3), 'end': round(en, 3), 'text': text})
        last = max(times[i][1] for i in anchors)
        cursor = last + 0.01
        print('sent %02d: %d/%d tokens, %d chunk(s), %.3f -> %.3f'
              % (si + 1, len(matched), len(exp), len(chunks),
                 events[-len(chunks)]['start'], events[-1]['end']), flush=True)
    print('tokens aligned: %d/%d (%.1f%%)' % (total_ok, total_exp, 100.0 * total_ok / total_exp))
    assert total_ok >= 0.75 * total_exp, 'alignment too poor - inspect'

    events.sort(key=lambda e: e['start'])
    for n in range(1, len(events)):
        if events[n - 1]['end'] > events[n]['start'] - 0.04:
            events[n - 1]['end'] = round(events[n]['start'] - 0.04, 3)

    dest = root / 'subtitle-events.json'
    old = json.loads(dest.read_text()) if dest.exists() else []
    bak = root / 'subtitle-events-prev.json'
    if old and not bak.exists():
        bak.write_text(json.dumps(old, ensure_ascii=False, indent=1))
    if old:
        ds = []
        for a, b in zip(old, events):
            ds.append(abs(a['start'] - b['start']))
        print('max |start change| vs previous events: %.3f s' % max(ds))
    dest.write_text(json.dumps(events, ensure_ascii=False, indent=1))
    print('WROTE', dest, len(events), 'chunks,', events[0]['start'], '->', events[-1]['end'])


if __name__ == '__main__':
    main()
