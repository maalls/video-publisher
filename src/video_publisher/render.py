from pathlib import Path
import subprocess
from .audio import duration
from .visuals import card, thumbnail


def run(args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def srt_time(t):
    ms = round(t*1000)
    return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"


def render(script, audio, folder: Path, day, demo=False, width=1080, music=None):
    if width % 18:
        raise ValueError("La largeur doit être un multiple de 18 pour le ratio 9:16")
    height = width*16//9
    durations = [max(6.25, duration(p)) for p in audio]
    if sum(durations) > 90:
        raise ValueError("Voix trop longue (>90 s), ajuster le prompt ou le débit après écoute")
    elapsed = 0.; timeline = []; subtitles = []; segments = []
    for i, (item, voice, seconds) in enumerate(zip(script["horoscopes"], audio, durations)):
        image = folder / f"card-{i:02}.png"
        card(item, i, day, image, demo)
        segment = folder / f"segment-{i:02}.mp4"
        run(["-loop", "1", "-framerate", "25", "-i", str(image), "-i", str(voice),
             "-vf", f"scale={width}:{height},format=yuv420p", "-af", "apad",
             "-t", f"{seconds:.3f}", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "23", "-c:a", "aac", "-ar", "48000", "-ac", "2",
             "-threads", "2", str(segment)])
        actual = duration(segment)
        timeline.append({"sign": item["sign"], "start": round(elapsed, 3), "duration": actual})
        subtitles.append(f"{i+1}\n{srt_time(elapsed)} --> {srt_time(elapsed+actual)}\n"
                         f"{item['sign']} : {item['text']}\n")
        elapsed += actual
        segments.append(segment)
    concat = folder / "concat.txt"
    concat.write_text("".join(f"file '{p.name}'\n" for p in segments), encoding="utf-8")
    joined = folder / "assembled.mp4"
    run(["-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(joined)])
    final = folder / "video.mp4"
    if music:
        run(["-i", str(joined), "-stream_loop", "-1", "-i", str(music),
             "-filter_complex", "[1:a]volume=0.08[m];[0:a][m]amix=inputs=2:duration=first[a]",
             "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
             "-movflags", "+faststart", str(final)])
    else:
        run(["-i", str(joined), "-c", "copy", "-movflags", "+faststart", str(final)])
    (folder / "subtitles.srt").write_text("\n".join(subtitles), encoding="utf-8")
    thumbnail(day, folder / "thumbnail.png")
    return timeline
