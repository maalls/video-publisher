#!/usr/bin/env python3
"""Manual YouTube upload with expected-channel check and durable no-repeat journal.
No generation, scheduler, or implicit publication. Requires explicit --upload.
"""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
import requests

API = 'https://www.googleapis.com/youtube/v3/'


def private_json(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.youtube-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''): h.update(block)
    return h.hexdigest()


def checked(response):
    if not response.ok:
        code = str(response.status_code)
        try:
            reason = response.json().get('error', {}).get('errors', [{}])[0].get('reason', '')
            if re.fullmatch(r'[A-Za-z_]{1,80}', reason): code += ':' + reason
        except (ValueError, AttributeError, IndexError): pass
        raise RuntimeError('API refusal ' + code)
    return response


def load_token(path, session):
    token = json.loads(Path(path).read_text())
    expiry = token.get('expiry')
    refresh = not token.get('token')
    if expiry:
        dt = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        refresh = refresh or dt <= datetime.now(timezone.utc) + timedelta(seconds=120)
    if refresh:
        required = ['refresh_token', 'client_id', 'client_secret']
        if not all(token.get(k) for k in required): raise ValueError('OAuth refresh fields missing')
        # Fixed Google endpoint, never a URL supplied by a local token file.
        response = checked(session.post('https://oauth2.googleapis.com/token', data={
            'grant_type': 'refresh_token', **{k: token[k] for k in required}}, timeout=60))
        updated = response.json()
        token['token'] = updated['access_token']
        if updated.get('refresh_token'): token['refresh_token'] = updated['refresh_token']
        token['expiry'] = (datetime.now(timezone.utc) + timedelta(seconds=int(updated['expires_in']))).isoformat().replace('+00:00', 'Z')
        private_json(path, token)
    return token


def verify_channel(session, channel):
    data = checked(session.get(API + 'channels', params={'part':'id,snippet','mine':'true'}, timeout=60)).json()
    items = data.get('items', [])
    if [x['id'] for x in items] != [channel]: raise ValueError('OAuth channel mismatch')
    return {'channel_id': channel, 'channel_name': items[0].get('snippet',{}).get('title','')}


def read_video(session, video_id):
    data = checked(session.get(API + 'videos', params={'part':'snippet,status,processingDetails,player','id':video_id}, timeout=60)).json()
    if len(data.get('items',[])) != 1: raise RuntimeError('Uploaded video not readable yet; do not re-upload')
    return data['items'][0]


def run(args, session=None):
    session = session or requests.Session()
    video = args.video.resolve(strict=True)
    if video.suffix.lower() != '.mp4' or video.stat().st_size <= 0: raise ValueError('MP4 required')
    metadata = json.loads(args.metadata.read_text(encoding='utf-8'))
    if set(metadata) != {'title','description','defaultLanguage','defaultAudioLanguage'}: raise ValueError('Unexpected metadata keys')
    if not metadata['title'] or len(metadata['title']) > 100: raise ValueError('Invalid title')
    if len(metadata['description'].encode()) > 5000: raise ValueError('Description too long')
    sha = digest(video)
    existing = json.loads(args.journal.read_text()) if args.journal.exists() else None
    if existing and (existing.get('sha256') != sha or existing.get('channel_id') != args.channel_id):
        raise ValueError('Journal belongs to another file or channel')
    token = load_token(args.token, session)
    session.headers.update({'Authorization':'Bearer ' + token['token']})
    identity = verify_channel(session, args.channel_id)
    if existing:
        if not existing.get('video_id'):
            raise RuntimeError('Previous upload uncertain; inspect Studio, never repeat automatically')
        actual = read_video(session, existing['video_id'])
        existing['actual'] = actual
        private_json(args.journal, existing)
        print(json.dumps({'mode':'existing-status-only', **identity,'video_id':existing['video_id'],
                          'status':actual.get('status'), 'processing':actual.get('processingDetails'),
                          'title':actual.get('snippet',{}).get('title'), 'player':actual.get('player')},ensure_ascii=False))
        return existing
    requested = {'privacyStatus':args.visibility,'selfDeclaredMadeForKids':args.made_for_kids == 'yes'}
    if args.publish_at:
        when = datetime.fromisoformat(args.publish_at.replace('Z','+00:00'))
        if when.tzinfo is None or when <= datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError('Scheduled publication must be at least five minutes in the future, explicit timezone')
        if args.visibility != 'private': raise ValueError('Scheduled publication requires private visibility')
        requested['publishAt'] = when.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
    plan = {**identity,'sha256':sha,'bytes':video.stat().st_size,'snippet':metadata,'status':requested}
    if not args.upload:
        print(json.dumps({'mode':'preflight-only',**plan},ensure_ascii=False)); return plan
    # Intent reserved exclusively before init; ambiguous writes cannot be retried.
    args.journal.parent.mkdir(parents=True, exist_ok=True)
    receipt = {**plan, 'stage':'init-intent'}
    fd = os.open(args.journal, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd,'w') as f: json.dump(receipt,f); f.flush(); os.fsync(f.fileno())
    init = checked(session.post('https://www.googleapis.com/upload/youtube/v3/videos',
        params={'uploadType':'resumable','part':'snippet,status'},
        headers={'X-Upload-Content-Type':'video/mp4','X-Upload-Content-Length':str(video.stat().st_size)},
        json={'snippet':metadata,'status':requested},timeout=60,allow_redirects=False))
    location = init.headers.get('Location','')
    parts = urlsplit(location)
    if parts.scheme != 'https' or parts.hostname != 'www.googleapis.com' or parts.port not in (None,443) or parts.username or parts.password:
        raise RuntimeError('Unrecognized resumable destination; no video bytes sent')
    pending = args.journal.with_suffix('.resumable-secret.json')
    private_json(pending,{'url':location})
    receipt['stage']='put-intent'; private_json(args.journal,receipt)
    with video.open('rb') as stream:
        result = checked(session.put(location,data=stream,headers={'Content-Type':'video/mp4',
            'Content-Length':str(video.stat().st_size)},timeout=300,allow_redirects=False)).json()
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', result.get('id','')): raise RuntimeError('Missing video id; do not retry')
    receipt.update(stage='uploaded', video_id=result['id'], returned_status=result.get('status'))
    private_json(args.journal, receipt)
    pending.unlink(missing_ok=True)
    actual = read_video(session,result['id']); receipt['actual']=actual
    receipt['verified'] = (actual.get('status',{}).get('privacyStatus') == args.visibility and
                           actual.get('status',{}).get('selfDeclaredMadeForKids') == requested['selfDeclaredMadeForKids'] and
                           actual.get('snippet',{}).get('title') == metadata['title'] and
                           actual.get('snippet',{}).get('description') == metadata['description'])
    if args.publish_at:
        receipt['verified'] = receipt['verified'] and actual.get('status',{}).get('publishAt') == requested['publishAt']
    receipt['stage']='verified' if receipt['verified'] else 'uploaded-needs-review'
    private_json(args.journal,receipt)
    print(json.dumps({'video_id':result['id'],'verified':receipt['verified'],'status':actual.get('status'),
                      'processing':actual.get('processingDetails'),'player':actual.get('player')},ensure_ascii=False))
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('video',type=Path); p.add_argument('--metadata',required=True,type=Path)
    p.add_argument('--token',required=True,type=Path);p.add_argument('--channel-id',required=True)
    p.add_argument('--journal',required=True,type=Path)
    p.add_argument('--visibility',required=True,choices=['public','private','unlisted'])
    p.add_argument('--made-for-kids',required=True,choices=['yes','no'])
    p.add_argument('--upload',action='store_true')
    p.add_argument('--publish-at',default=None,help='ISO8601 native YouTube scheduled visibility, requires private')
    try: run(p.parse_args())
    except (ValueError,OSError,KeyError,RuntimeError,requests.RequestException) as e:
        # Do not print raw HTTP errors: resumable URLs and tokens are secrets.
        safe = str(e) if type(e) is RuntimeError or type(e) is ValueError else type(e).__name__
        print('Stopped:',safe);raise SystemExit(1)

if __name__=='__main__':main()
