#!/usr/bin/env python3
"""Coupe la prise unique voix/speech-take.wav en voix/voix-NN.wav (un par segment de narration).

A lancer avec le python de whisper (faster-whisper). Les mots de la prise sont alignes sur le
texte attendu (difflib), la coupe tombe au milieu du silence entre le dernier mot d'un segment
et le premier du suivant. Ecrit voix/segments-cuts.json. Usage : cut_take.py PRODUCTION_DIR
"""
import difflib, json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from align_subtitles import norm, whisper_words  # noqa: E402


def boundaries(segments, words):
    exp, seg_first = [], []
    for s in segments:
        seg_first.append(len(exp))
        exp += [norm(t) for t in s.split() if norm(t)]
    heard = [norm(w['word']) for w in words]
    sm = difflib.SequenceMatcher(a=exp, b=heard, autojunk=False)
    amap = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            amap[blk.a + k] = blk.b + k
    cuts = []
    for k in range(1, len(segments)):
        i = seg_first[k]
        prev = next((j for j in range(i - 1, -1, -1) if j in amap), None)
        nxt = next((j for j in range(i, len(exp)) if j in amap), None)
        if prev is None or nxt is None:
            raise SystemExit('alignement impossible a la frontiere %d' % k)
        end_prev = words[amap[prev]]['end']
        start_next = words[amap[nxt]]['start']
        cuts.append(round((end_prev + start_next) / 2, 3))
    ratio = sm.ratio()
    return cuts, ratio


def main():
    root = Path(sys.argv[1])
    narr = json.loads((root / 'narration.json').read_text())
    take = root / 'voix' / 'speech-take.wav'
    words = whisper_words(take, root / 'voix' / 'take-words.json')
    cuts, ratio = boundaries(narr['segments'], words)
    if ratio < 0.8:
        raise SystemExit('la prise ne correspond pas assez au texte (similarite %.2f), a reecouter' % ratio)
    total = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(take)]))
    edges = [0.0] + cuts + [total]
    for i in range(len(edges) - 1):
        subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-i', str(take), '-ss', str(edges[i]), '-to', str(edges[i + 1]),
                        '-c:a', 'pcm_s16le', str(root / 'voix' / ('voix-%02d.wav' % (i + 1)))], check=True)
    (root / 'voix' / 'segments-cuts.json').write_text(json.dumps({'cuts': cuts, 'similarity': round(ratio, 3)}))
    print('coupes', cuts, 'similarite %.2f' % ratio)


if __name__ == '__main__':
    main()
