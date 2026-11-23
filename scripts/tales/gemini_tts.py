"""Voix du conte : Gemini TTS, une seule prise pour tout le texte.

Deux sources d'identifiants, au choix (le fichier decide) :
1. Compte de service Google Cloud (defaut) : var/project/tales/private/tts-service-account.json
   (hors Git : /var/ est ignore ; proprietaire instinct, 600). Appel via Cloud Text-to-Speech
   (SDK google-cloud-texttospeech), modele gemini-2.5-flash-tts, voix Sadaltager, fr-FR,
   le style de lecture passe dans le champ `prompt`. Les modeles Gemini 3.8 ne sont pas
   disponibles via l'API Cloud Text-to-Speech (doc Google) : d'ou gemini-2.5-flash-tts.
2. Cle d'API Gemini : fichier JSON {"api_key": "..."} (GEMINI_TTS_KEY_FILE), appel REST
   Interactions API, modele gemini-3.8-flash-tts.
Les secrets ne sont jamais affiches, ni ecrits dans un journal ou une URL ; les erreurs ne les contiennent pas.
Le fichier doit appartenir a l'utilisateur courant et ne pas etre lisible par le groupe/les autres.
"""
import base64, json, os, stat, urllib.error, urllib.request
from pathlib import Path

TALES = Path(__file__).resolve().parents[2] / 'var' / 'project' / 'tales'
SA_FILE = TALES / 'secrets' / 'gemini-tts.json'  # cle API Gemini par defaut
URL = 'https://generativelanguage.googleapis.com/v1beta/interactions'
CLOUD_MODEL = 'gemini-2.5-flash-tts'
API_MODEL = 'gemini-3.8-flash-tts'
DEFAULT_MODEL = CLOUD_MODEL
MAX_BYTES = 4000  # limite Cloud TTS : 5000 octets texte + prompt


class TTSError(RuntimeError):
    pass


def credentials_path():
    return Path(os.environ.get('GEMINI_TTS_KEY_FILE') or SA_FILE)


def check_file(path):
    path = Path(path)
    if not path.is_file():
        raise TTSError('fichier d\'identifiants absent: %s' % path)
    st = path.stat()
    if st.st_uid != os.getuid():
        raise TTSError('le fichier doit appartenir a l\'utilisateur courant: %s' % path)
    if st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise TTSError('permissions trop larges sur %s (attendu 600)' % path)
    try:
        return json.loads(path.read_text())
    except ValueError:
        raise TTSError('JSON illisible: %s' % path) from None


def load_credentials(path=None):
    """Retourne ('service_account', chemin) ou ('api_key', cle)."""
    path = Path(path or credentials_path())
    d = check_file(path)
    if d.get('type') == 'service_account' and d.get('private_key') and d.get('client_email'):
        return 'service_account', path
    key = d.get('api_key')
    if isinstance(key, str) and len(key) >= 20:
        return 'api_key', key
    raise TTSError('format attendu: compte de service Google ou {"api_key": "..."} dans %s' % path)


def load_key(path=None):  # compatibilite
    kind, v = load_credentials(path)
    if kind != 'api_key':
        raise TTSError('le fichier contient un compte de service, pas une cle d\'API')
    return v


def request_body(text, voice, style, model):
    ann = {'type': 'speech_metadata'}
    if style:
        ann['style'] = style
    return {'model': model,
            'input': [{'type': 'user_input', 'content': [{'type': 'text', 'text': text, 'annotations': [ann]}]}],
            'response_format': {'type': 'audio'},
            'generation_config': {'speech_config': [{'voice': voice}]}}


def find_audio(obj):
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


def synth_api_key(text, out_wav, voice, style, model, key, timeout):
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
    return base64.b64decode(b64)


def synth_cloud(text, voice, style, model, sa_path, timeout):
    from google.cloud import texttospeech as tts
    from google.oauth2 import service_account
    try:
        creds = service_account.Credentials.from_service_account_file(
            str(sa_path), scopes=['https://www.googleapis.com/auth/cloud-platform'])
        client = tts.TextToSpeechClient(credentials=creds)
        resp = client.synthesize_speech(
            input=tts.SynthesisInput(text=text, prompt=style or None),
            voice=tts.VoiceSelectionParams(language_code='fr-FR', name=voice, model_name=model),
            audio_config=tts.AudioConfig(audio_encoding=tts.AudioEncoding.LINEAR16, sample_rate_hertz=24000),
            timeout=timeout)
    except Exception as e:  # le message d'erreur du SDK ne contient pas la cle privee
        raise TTSError('Cloud TTS: %s: %s' % (type(e).__name__, str(e)[:300])) from None
    return resp.audio_content


def synthesize(text, out_wav, voice='Sadaltager', style='', model=None, creds=None, timeout=300, key=None):
    if key is not None:
        creds = ('api_key', key)
    kind, value = creds or load_credentials()
    if kind == 'service_account':
        model = model or CLOUD_MODEL
        if len(text.encode()) + len((style or '').encode()) > MAX_BYTES:
            raise TTSError('texte trop long pour une requete Cloud TTS (%d octets max)' % MAX_BYTES)
        raw = synth_cloud(text, voice, style, model, value, timeout)
    else:
        raw = synth_api_key(text, out_wav, voice, style, model or API_MODEL, value, timeout)
    if raw[:4] != b'RIFF':
        raise TTSError('audio inattendu (pas un WAV)')
    Path(out_wav).write_bytes(raw)
    return Path(out_wav)
