import sys, json, requests
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, 'src')
from video_publisher import tiktok_inbox as t
S = 'var/project/tales/secrets/'
tok = t.load_token(S + 'tiktok-client.json', S + 'tiktok-token.json')
print('scopes:', tok.get('scope'))
print('compte:', t.user_info(tok).get('display_name'))
r = requests.post(t.API + 'video/list/?fields=id,create_time,title,duration,view_count,like_count,comment_count,share_count',
                  json={'max_count': 20}, headers={'Authorization': 'Bearer ' + tok['access_token']}, timeout=60, allow_redirects=False)
b = r.json()
print('http', r.status_code, 'code', b.get('error', {}).get('code'))
for v in (b.get('data') or {}).get('videos', []):
    d = datetime.fromtimestamp(v['create_time'], ZoneInfo('Europe/Paris'))
    print(d.strftime("%d/%m %H:%M:%S"), v.get("duration"), "v", v.get("view_count"), "l", v.get("like_count"), "c", v.get("comment_count"), "s", v.get("share_count"), (v.get('title') or v.get('video_description') or '')[:60].replace('\n', ' '))
