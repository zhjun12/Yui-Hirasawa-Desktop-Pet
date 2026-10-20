"""Validated, data-driven animation packs shared by the app and importer."""
from bisect import bisect_right
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import struct

RESERVED={'auto','idle','daydream','listen','spin','eat','quiet','happy','guitar','expect'}


@dataclass
class ActionPack:
    id: str
    folder: Path
    info: dict
    files: tuple
    fps: float
    ends_ms: tuple
    duration: float
    weights: dict
    cycles: tuple
    cooldown: float
    manual_cycles: int

    @property
    def name(self): return self.info['name']

    @property
    def button_label(self): return self.info.get('button_label',self.name)

    def frame_index(self, seconds):
        ms=max(0.,seconds)*1000
        if self.info.get('loop',True):
            ms %= self.duration*1000
        return min(len(self.files)-1,bisect_right(self.ends_ms,ms))


def load_pack(folder):
    folder=Path(folder).resolve()
    info=json.loads((folder/'motion.json').read_text(encoding='utf-8-sig'))
    if not isinstance(info,dict) or info.get('schema_version',1)!=1:
        raise ValueError('动作格式版本不支持')
    key=info.get('id',folder.name)
    if not isinstance(key,str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}',key) or key in RESERVED:
        raise ValueError('动作 ID 无效或与内置动作重名')
    name=info.get('name')
    if not isinstance(name,str) or not name.strip() or len(name)>60:
        raise ValueError('动作名称应为 1～60 个字符')
    if type(info.get('loop',True)) is not bool: raise ValueError('loop 应为布尔值')
    if type(info.get('enabled',True)) is not bool: raise ValueError('enabled 应为布尔值')
    for field,limit in [('button_label',30),('bubble',160)]:
        if field in info and (not isinstance(info[field],str) or not 1<=len(info[field])<=limit):
            raise ValueError(f'{field} 文本长度无效')
    count=info.get('frame_count')
    if type(count) is not int or not 1<=count<=600:
        raise ValueError('动作帧数应为 1～600')
    fps=info.get('fps',30)
    if type(fps) not in (int,float) or not math.isfinite(fps) or not 1<=fps<=120:
        raise ValueError('动作帧率无效')
    names=info.get('frame_files',[f'{i:03d}.png' for i in range(count)])
    if not isinstance(names,list) or len(names)!=count or any(not isinstance(name,str) for name in names) or len(set(names))!=count:
        raise ValueError('帧文件列表无效')
    files=[]
    pixels=0
    for name in names:
        if not isinstance(name,str) or Path(name).name!=name or not name.lower().endswith('.png'):
            raise ValueError('帧文件必须是动作目录内的 PNG 文件')
        path=(folder/name).resolve()
        if path.parent!=folder or not path.is_file():
            raise ValueError(f'动作帧缺失或路径越界：{name}')
        with path.open('rb') as stream:
            header=stream.read(24)
        if len(header)<24 or header[:8]!=b'\x89PNG\r\n\x1a\n' or header[12:16]!=b'IHDR':
            raise ValueError(f'不是有效的 PNG：{name}')
        width,height=struct.unpack('>II',header[16:24])
        if not 1<=width<=1024 or not 1<=height<=1024:
            raise ValueError('单帧尺寸不得超过 1024×1024')
        pixels+=width*height
        if pixels>32000000:
            raise ValueError('动作解码体积过大，请缩小或拆分素材')
        files.append(path)
    durations=info.get('durations_ms',[1000/fps]*count)
    if not isinstance(durations,list) or len(durations)!=count:
        raise ValueError('帧时长数量与帧数不符')
    ends=[]
    total=0.
    for value in durations:
        if type(value) not in (int,float) or not math.isfinite(value) or not 5<=value<=30000:
            raise ValueError('帧时长必须为 5～30000 毫秒')
        total+=value
        ends.append(total)
    if total>60000:
        raise ValueError('单次动作最长 60 秒，请拆分素材')
    playback=info.get('playback',{})
    if not isinstance(playback,dict): raise ValueError('播放设置应为对象')
    weights=playback.get('weights',{'daily':10,'music':0})
    if not isinstance(weights,dict) or any(k not in ('daily','music') or
        type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1000 for k,v in weights.items()):
        raise ValueError('自动动作权重无效')
    cycles=playback.get('cycles',[1,2])
    if not isinstance(cycles,list) or len(cycles)!=2 or any(type(v) is not int for v in cycles) or not 1<=cycles[0]<=cycles[1]<=10:
        raise ValueError('循环次数无效')
    cooldown=playback.get('cooldown_seconds',90)
    if type(cooldown) not in (int,float) or not math.isfinite(cooldown) or not 0<=cooldown<=3600:
        raise ValueError('冷却时间无效')
    manual=playback.get('manual_cycles',2)
    if type(manual) is not int or not 1<=manual<=10:
        raise ValueError('手动循环次数无效')
    if not info.get('loop',True) and (cycles!=[1,1] or manual!=1):
        raise ValueError('单次动作应设置 cycles=[1,1] 和 manual_cycles=1')
    return ActionPack(key,folder,info,tuple(files),float(fps),tuple(ends),total/1000,
                      dict(weights),tuple(cycles),float(cooldown),manual)


def discover_packs(*roots):
    packs={}
    errors=[]
    for root in roots:
        root=Path(root)
        if not root.is_dir(): continue
        seen=set()
        for folder in sorted(root.iterdir()):
            if not folder.is_dir() or folder.name.startswith('.'): continue
            try:
                pack=load_pack(folder)
                if pack.id in seen: raise ValueError('同一目录中存在重复动作 ID')
                seen.add(pack.id)
                if pack.info.get('enabled',True) is False: continue
                packs[pack.id]=pack
            except (OSError,ValueError,TypeError,KeyError) as exc:
                errors.append(f'{folder.name}：{exc}')
    return packs,errors
