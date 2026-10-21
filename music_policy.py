"""Declarative music time shares, independent of individual animation assets."""
import json
import math
from collections import deque
from pathlib import Path


def validate_music_policy(value):
    if not isinstance(value,dict) or value.get('version')!=1:
        raise ValueError('听歌策略版本无效')
    actions=value.get('actions')
    if not isinstance(actions,dict) or not actions or len(actions)>100:
        raise ValueError('听歌策略需要 1～100 个动作')
    result={}
    for key,rule in actions.items():
        if not isinstance(key,str) or not key or not isinstance(rule,dict):
            raise ValueError('听歌动作设置无效')
        share=rule.get('share')
        if type(share) not in (int,float) or not math.isfinite(share) or not 0<share<=100:
            raise ValueError('时间占比必须为 0～100 之间的正数')
        normalized={'share':float(share)}
        if ('cycles' in rule)==('hold_seconds' in rule):
            raise ValueError('每个动作须指定循环次数或持续秒数之一')
        field='cycles' if 'cycles' in rule else 'hold_seconds'
        bounds=rule[field]
        if (not isinstance(bounds,list) or len(bounds)!=2 or
            any(type(n) not in (int,float) or not math.isfinite(n) for n in bounds) or
            not 0<bounds[0]<=bounds[1]<=120):
            raise ValueError('播放时长或循环范围无效')
        if field=='cycles' and any(type(n) is not int for n in bounds):
            raise ValueError('完整循环次数必须为整数')
        normalized[field]=list(bounds)
        cooldown=rule.get('cooldown_seconds',0)
        if type(cooldown) not in (int,float) or not math.isfinite(cooldown) or not 0<=cooldown<=3600:
            raise ValueError('听歌冷却时间无效')
        normalized['cooldown_seconds']=float(cooldown)
        group=rule.get('cooldown_group')
        if group is not None:
            if not isinstance(group,str) or not group or len(group)>80:
                raise ValueError('动作冷却分组无效')
            normalized['cooldown_group']=group
        result[key]=normalized
    normalized={'version':1,'actions':result,'allow_repeat':bool(value.get('allow_repeat',False))}
    if 'weak' in value:
        weak=value['weak']
        if not isinstance(weak,dict) or 'weak' in weak:
            raise ValueError('弱音乐策略无效')
        normalized['weak']=validate_music_policy(dict(weak,version=1))
    return normalized


class MusicIntensity:
    """Energy/onset heuristic with hysteresis; this does not estimate BPM."""
    def __init__(self):
        self.profile='normal'
        self.level=None
        self.last=None
        self.onsets=deque()
        self.candidate=None
        self.since=0.
        self.last_valid=None

    def update(self, now, level, onset=False):
        if self.last_valid is not None and now-self.last_valid>2:
            self.__init__()
        if level is None:
            if self.last_valid is None or now-self.last_valid>2:
                self.__init__()
            return self.profile
        self.last_valid=now
        dt=max(0.,min(1.,now-self.last)) if self.last is not None else 0.
        self.last=now
        self.level=float(level) if self.level is None else self.level+(float(level)-self.level)*(1-math.exp(-dt/2.))
        if onset:
            self.onsets.append(now)
        while self.onsets and self.onsets[0]<now-8:
            self.onsets.popleft()
        score=.65*self.level+.35*min(1.,len(self.onsets)/8.)
        desired=('weak' if score<.22 else 'normal') if self.profile=='normal' else ('normal' if score>.34 else 'weak')
        if desired==self.profile:
            self.candidate=None
        elif desired!=self.candidate:
            self.candidate=desired
            self.since=now
        elif now-self.since >= (6 if desired=='weak' else 4):
            self.profile=desired
            self.candidate=None
        return self.profile


def load_music_policy(path):
    return validate_music_policy(json.loads(Path(path).read_text(encoding='utf-8-sig')))
