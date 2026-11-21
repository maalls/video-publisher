#!/usr/bin/env python3
"""Global realignment: full narration text vs all per-phrase whisper words
anchored at YABBE clip positions. Writes subtitle-events-new.json + report."""
import json, difflib, unicodedata, re

PROD = '/home/instinct/video-publisher/var/project/tales/productions/conte05-grue-reconnaissante'
MAXCH = 52
BREAK_MIN = 14

def norm(w):
    w = unicodedata.normalize('NFKD', w.lower())
    return re.sub(r'[^a-z0-9]', '', w)

phrases = json.load(open(PROD + '/voix/phrases.json'))
proj = json.load(open('/tmp/yabbe-proj.json'))
seq = [s for s in proj['sequences'] if s['id'] == proj['main_sequence_id']][0]
vc = sorted([c for c in seq['clips'] if c['track_id'] == 't_14e4834db5cb'], key=lambda c: c['start'])
assert len(vc) == len(phrases)

# 1. absolute whisper word stream
awords = []
for idx, clip in enumerate(vc):
    data = json.load(open('/tmp/pc/phrase-%02d.json' % (idx + 1)))
    for w in data['words']:
        if w['e'] <= w['s']:
            continue
        if not norm(w['w']):
            continue
        awords.append({'w': w['w'], 's': w['s'] + clip['start'], 'e': w['e'] + clip['start']})

# 2. expected token stream with sentence index
etoks = []  # (token, sentence_idx)
for si, ph in enumerate(phrases):
    for t in ph['sentence'].split():
        etoks.append((t, si))

wn = [norm(w['w']) for w in awords]
en = [norm(t) for t, _ in etoks]
sm = difflib.SequenceMatcher(a=wn, b=en, autojunk=False)
times = [None] * len(etoks)
matched = 0
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag == 'equal':
        matched += j2 - j1
        for k in range(j2 - j1):
            times[j1 + k] = (awords[i1 + k]['s'], awords[i1 + k]['e'])
for j in range(len(times)):
    if times[j] is None:
        prev = next((times[k] for k in range(j - 1, -1, -1) if times[k]), None)
        nxt = next((times[k] for k in range(j + 1, len(times)) if times[k]), None)
        if prev and nxt:
            mid = (prev[1] + nxt[0]) / 2
            times[j] = (mid, mid)
        elif prev:
            times[j] = (prev[1], prev[1] + 0.15)
        elif nxt:
            times[j] = (max(0.0, nxt[0] - 0.15), nxt[0])
        else:
            times[j] = (0.0, 0.15)
print('MATCHED %d/%d expected tokens' % (matched, len(etoks)))

# 3. chunk per sentence
events = []
sent_bounds = []
pos = 0
for si, ph in enumerate(phrases):
    n = len(ph['sentence'].split())
    sent_bounds.append((pos, pos + n))
    pos += n

for si, (a, b) in enumerate(sent_bounds):
    toks = [etoks[j][0] for j in range(a, b)]
    tt = [times[j] for j in range(a, b)]
    chunks, cur = [], 0
    i = 1
    while i < len(toks):
        if len(' '.join(toks[cur:i + 1])) > MAXCH:
            brk = None
            for k in range(i, cur, -1):
                part = ' '.join(toks[cur:k])
                if len(part) < BREAK_MIN:
                    continue
                if toks[k - 1].endswith((',', ';', ':', '?', '!', '…')):
                    brk = k
                    break
                if tt[k][0] - tt[k - 1][1] >= 0.35:
                    brk = k
                    break
            if brk is None:
                brk = i
            chunks.append((cur, brk))
            cur = brk
            i = brk + 1
        else:
            i += 1
    chunks.append((cur, len(toks)))
    if si == 0 and len(chunks) == 1:
        for k, t in enumerate(toks):
            if t.endswith(','):
                chunks = [(0, k + 1), (k + 1, len(toks))]
                break
    next_first = times[b][0] if b < len(times) else tt[-1][1] + 2.0
    for ci, (x, y) in enumerate(chunks):
        st = max(tt[x][0] - 0.05, vc[0]['start'] if si == 0 else 0.0)
        if ci + 1 < len(chunks):
            en = tt[chunks[ci + 1][0]][0] - 0.04
        else:
            en = min(tt[y - 1][1] + 0.35, next_first - 0.04)
        if en - st < 0.4:
            en = st + 0.4
        events.append({'start': round(st, 3), 'end': round(en, 3),
                       'text': ' '.join(toks[x:y]), 'sent': si + 1})
json.dump([{k: e[k] for k in ('start', 'end', 'text')} for e in events],
          open(PROD + '/subtitle-events-new.json', 'w'), ensure_ascii=False, indent=1)
for e in events:
    print('%6.2f %6.2f s%02d | %s' % (e['start'], e['end'], e['sent'], e['text'][:70]))
print('TOTAL', len(events))
