"""Explicit local bootstrap only. Never prints the key, tokens or ciphertext.

Requires authenticated GitHub CLI and an already-created production environment.
The owner must approve this configuration step separately from running videos.
"""
import argparse
import base64
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from cryptography.fernet import Fernet
from video_publisher.production_config import (STATE_REPOSITORY, ACTIONS_ENVIRONMENT, STATE_KEY_SECRET)
from video_publisher.durable_state import StateCodec, empty_state
from video_publisher.daily_runner import parse_grant
from video_publisher.tiktok_inbox import private_json


def gh(*args, payload=None):
    result=subprocess.run(['gh',*args],input=payload,capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError('Opération GitHub refusée; aucun détail privé affiché')
    return result.stdout


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--grant-file',type=Path,required=True)
    parser.add_argument('--youtube-token',type=Path,default=Path('secrets/youtube-token.json'))
    parser.add_argument('--tiktok-token',type=Path,default=Path('secrets/tiktok-token.json'))
    parser.add_argument('--confirm-bootstrap',action='store_true')
    args=parser.parse_args()
    if not args.confirm_bootstrap:
        raise ValueError('Confirmation de bootstrap requise; aucune modification')
    if not shutil.which('gh'):
        raise ValueError('GitHub CLI doit être installé et connecté avant cette étape')
    account=json.loads(gh('api','user'))
    if account.get('login')!='maalls':
        raise ValueError('Compte GitHub différent; arrêt')
    repo=json.loads(gh('api','repos/'+STATE_REPOSITORY))
    if repo.get('private') is not True or repo.get('full_name')!=STATE_REPOSITORY:
        raise ValueError('Dépôt privé attendu non confirmé')
    contents=json.loads(gh('api','repos/'+STATE_REPOSITORY+'/contents'))
    if not isinstance(contents,list) or not any(item.get('name')=='README.md' for item in contents):
        raise ValueError('README initial requis; aucune création de dépôt implicite')
    if any(item.get('name')=='state.enc' for item in contents):
        raise ValueError('État déjà existant; ne jamais le remplacer par un bootstrap')
    raw=json.loads(args.grant_file.read_text())
    grant=parse_grant(raw)
    # Bootstrap is configuration only. Activation is a separate reviewed change.
    if grant.youtube_enabled or grant.tiktok_enabled or grant.costs_confirmed:
        raise ValueError('Bootstrap exige plateformes et coûts non activés')
    state=empty_state();state['grant']=raw
    for platform,path,expected in [('youtube',args.youtube_token,grant.youtube_account),
                                   ('tiktok',args.tiktok_token,grant.tiktok_account)]:
        if not expected:
            raise ValueError('Identifiants des deux comptes requis pour bootstrap')
        value=json.loads(path.read_text())
        if not value.get('refresh_token'):
            raise ValueError('Jeton incomplet')
        if platform=='tiktok' and value.get('open_id')!=expected:
            raise ValueError('Compte TikTok différent')
        state['tokens'][platform]={'account':expected,'value':value}
    key_path=Path('secrets/production-state-key')
    key_path.parent.mkdir(exist_ok=True)
    key=Fernet.generate_key()
    # Exclusive: never overwrite a retained key if a prior bootstrap was interrupted.
    fd=os.open(key_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(key)
    encrypted=StateCodec(key).encode(state)
    # CLI reads sensitive values via stdin, not shell arguments/history/logs.
    gh('secret','set',STATE_KEY_SECRET,'--repo','maalls/video-publisher',
       '--env',ACTIONS_ENVIRONMENT,payload=key.decode())
    payload=json.dumps({'message':'Initialize encrypted state','branch':'main',
                        'content':base64.b64encode(encrypted).decode()})
    response=json.loads(gh('api','repos/'+STATE_REPOSITORY+'/contents/state.enc',
                           '--method','PUT','--input','-',payload=payload))
    import hashlib
    expected_sha=hashlib.sha1(b'blob '+str(len(encrypted)).encode()+b'\0'+encrypted).hexdigest()
    if response.get('content',{}).get('sha')!=expected_sha:
        raise RuntimeError('Résultat incertain; conserver la clé locale, ne pas relancer')
    print('État privé initialisé chiffré; clé transférée au secret de production. Aucun envoi activé.')
    print('Conserver secrets/production-state-key privé pour récupération. Ne pas partager ce fichier.')


if __name__=='__main__':
    try:main()
    except Exception:
        print('Bootstrap arrêté. Conserver les fichiers privés; vérifier GitHub avant toute relance.',file=sys.stderr)
        raise SystemExit(1) from None
