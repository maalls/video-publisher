import os
import subprocess
from pathlib import Path
from .core import required


def duration(path: Path) -> float:
    return float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)], text=True).strip())


def synthesize(items: list[dict], folder: Path, demo: bool) -> list[Path]:
    client = None
    if not demo:
        from google.cloud import texttospeech
        required("GOOGLE_APPLICATION_CREDENTIALS")
        voice_name = os.environ.get("TTS_VOICE", "fr-FR-Wavenet-A")
        if not voice_name.startswith("fr-FR-Wavenet-"):
            raise ValueError("Seules les voix fr-FR-Wavenet sont autorisées par cette configuration")
        client = texttospeech.TextToSpeechClient()
    paths = []
    for i, item in enumerate(items):
        path = folder / f"voice-{i:02}.wav"
        if not path.exists():
            if demo:
                subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "anullsrc=r=24000:cl=mono", "-t", "6.25", "-y", str(path)], check=True)
            else:
                narration = f"{item['sign']}. {item['text']}"
                response = client.synthesize_speech(
                    input=texttospeech.SynthesisInput(text=narration),
                    voice=texttospeech.VoiceSelectionParams(language_code="fr-FR", name=voice_name),
                    audio_config=texttospeech.AudioConfig(
                        audio_encoding=texttospeech.AudioEncoding.LINEAR16, speaking_rate=1.12),
                    retry=None, timeout=60)
                path.write_bytes(response.audio_content)
        paths.append(path)
    return paths
