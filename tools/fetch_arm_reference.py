"""Fetch public metadata for the user-specified one-second animation reference."""
from pathlib import Path
import json
import requests
import sys

root = Path(__file__).resolve().parents[1]
output = root / 'output' / 'arm-reference'
output.mkdir(parents=True, exist_ok=True)
headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.bilibili.com/video/BV1324y1m7QC/'}
session = requests.Session()
session.trust_env = '--direct' not in sys.argv
view = session.get('https://api.bilibili.com/x/web-interface/view',
                    params={'bvid': 'BV1324y1m7QC'}, headers=headers, timeout=25)
view.raise_for_status()
data = view.json()
if data.get('code') != 0:
    raise RuntimeError(f'Public video metadata unavailable: {data.get("code")}, {data.get("message")}')
cid = data['data']['cid']
play = session.get('https://api.bilibili.com/x/player/playurl',
    params={'bvid': 'BV1324y1m7QC', 'cid': cid, 'qn': 32, 'fnval': 0}, headers=headers, timeout=25)
play.raise_for_status()
play_data = play.json()
(output / 'public-metadata.json').write_text(json.dumps(
    {'title': data['data']['title'], 'cid': cid, 'duration': data['data']['duration'], 'play': play_data},
    ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'title': data['data']['title'], 'duration': data['data']['duration'],
    'play_code': play_data.get('code'), 'has_public_video': bool(play_data.get('data', {}).get('durl'))}, ensure_ascii=False))
