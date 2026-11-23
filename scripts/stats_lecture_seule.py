"""Lecture seule des statistiques YouTube et Instagram (aucun envoi, jetons jamais affiches)."""
import sys, json, requests
from pathlib import Path
sys.path.insert(0, 'scripts/tales')
S = Path('var/project/tales/secrets')
ST = Path('var/project/tales/state')
ids = {'1': '0Gy0lhwRbk8', '2': 'IqF_01ZmzuQ', '3': 'UyYT2u3W088', '4': 'hS4nCp4d37Q', '5': 'WNzQFKyfhB8', '6': 'cpu49amCCa0'}
import upload_youtube_scheduled as y
s = requests.Session()
tok = y.load_token(S / 'youtube-token.json', s)
s.headers['Authorization'] = 'Bearer ' + tok['token']
r = s.get(y.API + 'videos', params={'part': 'statistics,status', 'id': ','.join(ids.values())}, timeout=60)
print('YT http', r.status_code)
by = {i['id']: i for i in r.json().get('items', [])}
for k, v in ids.items():
    i = by.get(v)
    if i:
        st = i['statistics']; print('YT conte', k, v, i['status']['privacyStatus'], 'vues', st.get('viewCount'), 'likes', st.get('likeCount'), 'com', st.get('commentCount'))
    else:
        print('YT conte', k, v, 'introuvable')
try:
    import instagram_unified as ig
    cfg = ig.load(S / 'instagram/unified-client.json'); t = ig.load(S / 'instagram/unified-token.json')
    perms = ig.inspect_token(cfg, t['access_token'])['permissions']
    print('IG permissions:', ','.join(perms))
    uid = t['user_id']
    m = ig.api(cfg, uid + '/media', t['access_token'], {'fields': 'id,timestamp,caption,like_count,comments_count,media_type,permalink', 'limit': 20})
    for x in m.get('data', []):
        print('IG', x.get('timestamp'), x.get('like_count'), x.get('comments_count'), (x.get('caption') or '')[:40].replace('\n', ' '), x.get('permalink'))
    if 'instagram_manage_insights' in perms:
        print('IG insights dispo')
except Exception as e:
    print('IG erreur', type(e).__name__, str(e)[:200])
