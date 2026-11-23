"""Montage generique d'un conte (port de conte06-montage.py, sans valeurs en dur).

Entrees dans le dossier de production : voix/voix-NN.wav, voix/phrases.json,
subtitle-events.json, clips d'animation (recus anim-<plan>.receipt.json), musique.
Plans, repartition des phrases par plan et musique viennent de conte.json.
Sorties : narration-complete.wav, picture-master.mp4, <id>-master-<version>.mp4,
<id>-whatsapp-<version>.mp4.
"""
import json, re, subprocess
from pathlib import Path

INTRO, OUTRO, FPS = 1.0, 1.5, 24
CARD_DUR, CARD_DELAY = 6.125, 0.625
STYLE_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 704
PlayResY: 832
WrapStyle: 0
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,34,&H00FFFFFF,&H000000FF,&H90000000,&H90000000,0,0,0,0,100,100,0,0,1,2.2,0,2,40,40,60,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def run(args):
    print('RUN', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), check=True)


def ff(args):
    run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', *args])


def duration(p):
    return float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                          '-of', 'csv=p=0', str(p)]))


def ts(t):
    return '%d:%02d:%05.2f' % (t // 3600, t // 60 % 60, t % 60)


def lines_of(g):
    shown = re.sub(r' ([?!:;])', '\u00a0' + r'\1', g)
    words = shown.split(' ')
    if len(shown) > 33:
        sp = min(range(1, len(words)), key=lambda j: max(len(' '.join(words[:j])), len(' '.join(words[j:]))) +
                 abs(len(' '.join(words[:j])) - len(' '.join(words[j:]))) * .2)
        lines = [' '.join(words[:sp]), ' '.join(words[sp:])]
    else:
        lines = [shown]
    assert len(lines) <= 2, (g, lines)
    return lines


def make_ass(root):
    ev = json.loads((root / 'subtitle-events.json').read_text())
    out = ['Dialogue: 0,%s,%s,Default,,0,0,0,,%s' % (ts(e['start']), ts(e['end']), '\\N'.join(lines_of(e['text'])))
           for e in ev]
    (root / 'sous-titres.ass').write_text(STYLE_ASS + '\n'.join(out) + '\n')


def clip_path(root, comfy_out, anim_item):
    r = json.loads((root / ('anim-' + anim_item + '.receipt.json')).read_text())
    for node in r['outputs'].values():
        for key in ('images', 'videos'):
            for m in node.get(key, []):
                if m['filename'].endswith('.mp4'):
                    return Path(comfy_out) / m.get('subfolder', '') / m['filename']
    raise KeyError(anim_item)


def narration(root, n_segments):
    wavs = [root / 'voix' / ('voix-%02d.wav' % i) for i in range(1, n_segments + 1)]
    args = []
    for p in wavs:
        args += ['-i', p]
    ff(args + ['-filter_complex', 'concat=n=%d:v=0:a=1,adelay=1000,apad=pad_dur=1.5' % n_segments,
               '-c:a', 'pcm_s16le', root / 'narration-complete.wav'])
    return duration(root / 'narration-complete.wav')


def picture(root, conte, anim_items, version, comfy_out, endcard_dir):
    cid = conte['id']
    n_seg = len(conte['narration']['segments'])
    wavs = [root / 'voix' / ('voix-%02d.wav' % i) for i in range(1, n_seg + 1)]
    voice_end = INTRO + sum(duration(p) for p in wavs)
    total = voice_end + OUTRO
    shots = [p['phrases'] for p in conte['plans']]
    n = len(shots)
    music = str(root / conte['music']['file'])
    endc = Path(endcard_dir)
    ph = json.loads((root / 'voix' / 'phrases.json').read_text())
    bnd = []
    for k in range(n - 1):
        last = ph[shots[k][1] - 1]
        nxt = ph[shots[k + 1][0] - 1]
        bnd.append((last['start'] + last['duration'] + nxt['start']) / 2)
    edges = [INTRO] + bnd + [voice_end]
    parts = [edges[i + 1] - edges[i] for i in range(n)]
    print('parts', [round(x, 2) for x in parts], flush=True)
    make_ass(root)
    segs = root / 'segments'
    segs.mkdir(exist_ok=True)
    for i, item in enumerate(anim_items):
        clip = clip_path(root, comfy_out, item)
        tail = INTRO if i == 0 else OUTRO if i == n - 1 else 0
        target = parts[i] + (.25 if i in (0, n - 1) else .5) + tail
        moving = target - tail
        vf = 'setpts=%.8f*PTS,minterpolate=fps=24:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1' % (
            moving / (duration(clip) - 1 / FPS))
        if i == 0:
            vf += ',tpad=start_mode=clone:start_duration=1'
        vf += ',tpad=stop_mode=clone:stop_duration=2,trim=duration=%.8f,setpts=PTS-STARTPTS' % target
        dest = segs / ('seg-%02d.mp4' % (i + 1))
        if not dest.exists():
            ff(['-i', clip, '-vf', vf, '-r', '24', '-fps_mode', 'cfr', '-t', target, '-an', '-c:v', 'libx264',
                '-crf', '18', '-pix_fmt', 'yuv420p', dest])
        if abs(duration(dest) - target) > .04:
            fixed = dest.with_name(dest.stem + '-cfr-fix.mp4')
            frames = round(target * FPS)
            ff(['-i', dest, '-vf', 'tpad=stop_mode=clone:stop_duration=1,fps=24,trim=end_frame=%d,setpts=N/(24*TB)' % frames,
                '-an', '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', fixed])
            dest.replace(dest.with_name(dest.stem + '-before-length-fix.mp4'))
            fixed.replace(dest)
        assert abs(duration(dest) - target) < .045, (dest, duration(dest), target)
    args = []
    for i in range(n):
        args += ['-i', segs / ('seg-%02d.mp4' % (i + 1))]
    args += ['-i', endc / 'endcard.mp4']
    filters, cum = [], INTRO
    for i in range(n - 1):
        cum += parts[i]
        left = '[0:v]' if i == 0 else '[x%d]' % i
        filters.append('%s[%d:v]xfade=transition=fade:duration=0.5:offset=%.8f[x%d]' % (left, i + 1, cum - .25, i + 1))
    filters.append('[x%d]subtitles=%s[s]' % (n - 1, root / 'sous-titres.ass'))
    filters.append('[%d:v]fps=24,fade=t=in:st=0:d=0.5,fade=t=out:st=%.8f:d=1[card]' % (n, CARD_DUR - 1))
    filters.append('[s][card]concat=n=2:v=1:a=0[v]')
    full = total + CARD_DUR
    ff(args + ['-filter_complex_threads', '1', '-filter_complex', ';'.join(filters), '-map', '[v]', '-an',
               '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', '-t', full, root / 'picture-master.mp4'])
    master = root / ('%s-master-%s.mp4' % (cid, version))
    ff(['-i', root / 'picture-master.mp4', '-i', root / 'narration-complete.wav', '-i', endc / 'outro-cta.wav', '-i', music,
        '-filter_complex',
        '[1:a]aformat=sample_rates=48000:channel_layouts=stereo,apad=whole_dur=%.8f[voice];'
        '[2:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay=%d|%d[cta];'
        '[3:a]aformat=sample_rates=48000:channel_layouts=stereo,aloop=loop=-1:size=2000000000,atrim=0:%.8f,'
        'asetpts=PTS-STARTPTS,volume=0.12,afade=t=in:d=1.5,afade=t=out:st=%.8f:d=3[music];'
        '[voice][cta][music]amix=inputs=3:duration=first:normalize=0[a]' % (
            full, int((total + CARD_DELAY) * 1000), int((total + CARD_DELAY) * 1000), full, full - 3),
        '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
        '-t', full, master])
    wa = root / ('%s-whatsapp-%s.mp4' % (cid, version))
    ff(['-i', master, '-c:v', 'libx264', '-b:v', '790k', '-maxrate', '900k', '-bufsize', '1800k', '-preset', 'slow',
        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k', '-movflags', '+faststart', wa])
    assert wa.stat().st_size <= 16000000
    return master, wa
