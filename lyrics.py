"""Local lyrics, timestamp parsing, and atomic song-specific bindings."""
import bisect
import hashlib
import json
import math
import os
from pathlib import Path
import re

STAMP=re.compile(r'\[(\d{1,3}):([0-5]?\d)(?:[.:](\d{1,3}))?\]')


def song_key(source, title='', artist='', album='', path=''):
    identity=['local',os.path.normcase(os.path.abspath(path))] if source=='local' and path else [source,title.strip(),artist.strip(),album.strip()]
    return hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()


def parse_lyrics(text):
    text=text.lstrip('\ufeff')
    found=re.search(r'\[offset:([+-]?\d+)\]',text,re.I)
    offset=max(-60000,min(60000,int(found[1]))) if found else 0
    timed=[];plain=[]
    for line in text.splitlines():
        stamps=list(STAMP.finditer(line))
        content=STAMP.sub('',line).strip()
        if stamps:
            for stamp in stamps:
                fraction=(stamp[3] or '').ljust(3,'0')
                milliseconds=int(stamp[1])*60000+int(stamp[2])*1000+int(fraction or '0')
                timed.append((milliseconds,content))
        elif content and not re.fullmatch(r'\[[a-zA-Z]+:.*\]',content):
            plain.append(content)
    timed.sort(key=lambda item:item[0])
    # Keep translations at the same timestamp together.
    grouped=[]
    for stamp,line in timed:
        if grouped and grouped[-1][0]==stamp:
            if line and line not in grouped[-1][1].split('\n'):
                grouped[-1][1]+=('\n' if grouped[-1][1] else '')+line
        else:
            grouped.append([stamp,line])
    if not grouped and not plain:
        raise ValueError('歌词文件没有可显示的内容')
    return dict(lines=grouped,plain=plain,offset_ms=offset)


def lyric_index(document, seconds):
    if seconds is None or not math.isfinite(seconds):
        return -1
    times=[line[0] for line in document.get('lines',[])]
    return bisect.bisect_right(times,seconds*1000+document.get('offset_ms',0))-1


class LyricsLibrary:
    def __init__(self, folder):
        self.folder=Path(folder)

    def _path(self, key):
        if not re.fullmatch(r'[a-f0-9]{64}',key):
            raise ValueError('歌曲标识无效')
        return self.folder/f'{key}.json'

    def save(self,key,document):
        destination=self._path(key)
        self.folder.mkdir(parents=True,exist_ok=True)
        temp=destination.with_suffix('.tmp')
        temp.write_text(json.dumps(document,ensure_ascii=False),encoding='utf-8')
        os.replace(temp,destination)

    def load(self,key):
        try:
            value=json.loads(self._path(key).read_text(encoding='utf-8'))
            if not isinstance(value,dict) or not isinstance(value.get('lines'),list) or not isinstance(value.get('plain'),list):
                return None
            if len(value['lines'])>20000 or any(not isinstance(row,list) or len(row)!=2 or type(row[0]) is not int or not isinstance(row[1],str) for row in value['lines']):
                return None
            if any(not isinstance(line,str) for line in value['plain']): return None
            if type(value.get('offset_ms')) is not int: return None
            return value
        except (OSError,ValueError,TypeError):
            return None

    def import_file(self,key,path):
        path=Path(path)
        if path.stat().st_size>2*1024*1024:
            raise ValueError('歌词文件过大，请使用小于 2 MB 的 LRC 或 TXT')
        raw=path.read_bytes()
        text=None
        for encoding in ('utf-8-sig','utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'gb18030'):
            try:
                text=raw.decode(encoding);break
            except UnicodeError:
                continue
        if text is None: raise ValueError('无法识别歌词编码，请保存为 UTF-8')
        document=parse_lyrics(text)
        self.save(key,document)
        return document
