"""Voix du conte via l'API Gemini TTS (REST, sans SDK), une seule prise pour tout le texte.

Cle : fichier JSON {"api_key": "..."} dans var/project/tales/secrets/gemini-tts.json (hors Git :
/var/ est dans .gitignore). Le fichier doit appartenir a l'utilisateur qui lance le lanceur et ne pas
etre lisible par le groupe/les autres (chmod 600). La cle n'est jamais affichee, jamais ecrite dans un
journal ni dans une URL (elle passe dans l'en-tete x-goog-api-key) ; les messages d'erreur ne la contiennent pas.
Modele par defaut : gemini-3.8-flash-tts (doc ai.google.dev/gemini-api/docs/speech-generation, Interactions API).
Cout estime ~0,03 $ par conte (ordre de grandeur deja constate avec la meme voix).
"""
import base64, json, os, stat, urllib.error, urllib.request
from pathlib import Path

URL = 'https://generativelanguage.googleapis.com/v1beta/interactions'
DEFAULT_MODEL = 'gemini-3.8-flash-tts'
KEY_FILE = Path(os.environ.get('GEMINI_TTS_KEY_FILE') or (Path(__file__).resolve().parents[2] / 'var' / 'project' / 'tales' / 'secrets' / 'gemini-tts.json'))


class TTSError(RuntimeError):
    pass


def load_key(path=KEY_FILE):
    path = Path(path)
    if not path.is_file():
        raise TTSError('fichier de cle absent: %s' % path)
    st = path.stat()
    if st.st_uid != os.getuid():
        raise TTSError('le fichier de cle doit appartenir a l\'utilisateur courant: %s' % path)
    if st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise TTSError('permissions trop larges sur %s (attendu 600)' % path)
    try:
        key = json.loads(path.read_text())['api_key']
    except (ValueError, KeyError):
        raise TTSError('format attendu: {"api_key": "..."} dans %s' % path) from None
    if not isinstance(key, str) or len(key) < 20:
        raise TTSError('api_key vide ou trop courte dans %s' % path)
    return key


def request_body(text, voice, style, model):
    ann = {'type': 'speech_metadata'}
    if style:
        ann['style'] = style
    return {'model': model,
            'input': [{'type': 'user_input', 'content': [{'type': 'text', 'text': text, 'annotations': [ann]}]}],
            'response_format': {'type': 'audio'},
            'generation_config': {'speech_config': [{'voice': voice}]}}


def find_audio(obj):
    """Premier champ 'data' base64 d'un bloc audio (steps[].content[].data)."""
    if isinstance(obj, dict):
        if obj.get('type') == 'audio' and isinstance(obj.get('data'), str):
            return obj['data']
        for v in obj.values():
            r = find_audio(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_audio(v)
            if r:
                return r
    return None


def synthesize(text, out_wav, voice='Sadaltager', style='', model=DEFAULT_MODEL, key=None, timeout=300):
    key = key or load_key()
    req = urllib.request.Request(URL, data=json.dumps(request_body(text, voice, style, model)).encode(), method='POST',
                                 headers={'Content-Type': 'application/json', 'x-goog-api-key': key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise TTSError('Gemini TTS HTTP %d (%s)' % (e.code, e.reason)) from None
    except (urllib.error.URLError, ValueError, TimeoutError) as e:
        raise TTSError('Gemini TTS indisponible (%s)' % type(e).__name__) from None
    b64 = find_audio(data)
    if not b64:
        raise TTSError('reponse Gemini TTS sans audio')
    raw = base64.b64decode(b64)
    if raw[:4] != b'RIFF':
        raise TTSError('audio inattendu (pas un WAV)')
    Path(out_wav).write_bytes(raw)
    return Path(out_wav)
