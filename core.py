"""UI-independent state, persistence and link validation."""
from __future__ import annotations

import json
import math
import os
import random
from pathlib import Path
import time
from urllib.parse import urlparse

AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma'}
MODES = ('auto', 'idle', 'daydream', 'listen', 'spin', 'eat', 'quiet')


def cloud_url(value: str) -> str:
    value = value.strip()
    p = urlparse(value)
    if p.scheme not in ('http', 'https') or p.username or p.password or p.port not in (None, 80, 443):
        raise ValueError('请粘贴完整的网易云歌曲或歌单链接（https://…）。')
    if (p.hostname or '').lower() not in {'music.163.com', 'y.music.163.com', '163cn.tv'}:
        raise ValueError('请使用 music.163.com、y.music.163.com 或 163cn.tv 的网易云链接。')
    return value


class Store:
    def __init__(self, path: Path, modes=None):
        self.path = path
        self.warning = ''
        self.data = dict(size=280, topmost=True, volume=55, tracks=[], links=[],
                         mode='auto', loop=0, focus=25, rest=5, reminders=False,
                         interval=60, sound=True, bubbles=True, drive=True,
                         system_audio=False, music_source='local', cloud_target='', edge_hide=True)
        try:
            loaded = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(loaded, dict):
                raise ValueError('设置格式不正确')
            self.data.update({k: v for k, v in loaded.items() if k in self.data or k == 'position'})
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            self.warning = '设置文件无法读取，本次使用默认设置。'
        for key, default, low, high in [('size', 280, 180, 480), ('volume', 55, 0, 100),
                                       ('focus', 25, 1, 180), ('rest', 5, 1, 60),
                                       ('interval', 60, 1, 240), ('loop', 0, 0, 2)]:
            v = self.data[key]
            self.data[key] = max(low, min(high, v)) if type(v) is int else default
        for key, default in [('topmost', True), ('reminders', False), ('sound', True), ('bubbles', True),
                             ('drive', True), ('system_audio', False), ('edge_hide', True)]:
            if type(self.data[key]) is not bool:
                self.data[key] = default
        if self.data['mode'] == 'guitar':
            self.data['mode'] = 'spin'
        if self.data['mode'] == 'expect':
            self.data['mode'] = 'auto'
        if self.data['mode'] not in (set(MODES) | set(modes or ())):
            self.data['mode'] = 'auto'
        if self.data['music_source'] not in ('local', 'cloud'):
            self.data['music_source'] = 'local'
        if not isinstance(self.data['cloud_target'], str):
            self.data['cloud_target'] = ''
        if not isinstance(self.data['tracks'], list):
            self.data['tracks'] = []
        self.data['tracks'] = list(dict.fromkeys(t for t in self.data['tracks'] if isinstance(t, str)))
        links = self.data['links'] if isinstance(self.data['links'], list) else []
        self.data['links'] = []
        for item in links:
            try:
                if isinstance(item, dict) and isinstance(item.get('name'), str):
                    self.data['links'].append({'name': item['name'][:100], 'url': cloud_url(item['url'])})
            except (ValueError, TypeError, KeyError):
                pass
        pos = self.data.get('position')
        if not (isinstance(pos, list) and len(pos) == 2 and all(type(v) is int for v in pos)):
            self.data.pop('position', None)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, self.path)


class Pomodoro:
    """Uses monotonic deadlines; UI updates never determine elapsed time."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.phase = 'idle'
        self.deadline = None
        self.paused = False
        self.saved = 0.0

    def start(self, phase, seconds):
        if phase not in ('focus', 'rest') or seconds <= 0:
            raise ValueError('Invalid timer')
        self.phase, self.paused = phase, False
        self.saved = float(seconds)
        self.deadline = self.clock() + seconds

    def remaining(self):
        if self.phase == 'idle':
            return 0
        return max(0, math.ceil(self.saved if self.paused else self.deadline - self.clock()))

    def toggle_pause(self):
        if self.phase == 'idle':
            return
        if self.paused:
            self.deadline = self.clock() + self.saved
        else:
            self.saved = max(0.0, self.deadline - self.clock())
        self.paused = not self.paused

    def stop(self):
        self.phase, self.deadline, self.paused, self.saved = 'idle', None, False, 0.0

    def poll(self):
        if self.phase != 'idle' and not self.paused and self.remaining() == 0:
            phase = self.phase
            self.stop()
            return phase
        return None


class Animation:
    def __init__(self, clock=time.monotonic, rng=None):
        self.clock = clock
        self.rng = rng or random.Random()
        self.mode = 'auto'
        self.playing = False
        self.follow_music = True
        self.focus = False
        self.temporary = None
        self.until = 0
        self.interaction_started = clock()
        self.loop_seconds = {'spin': .7}
        self.action_rules = {
            'daydream':dict(weights={'daily':50},hold=(4,8),cooldown=20),
            'spin':dict(weights={'music':1},cycles=(3,6),cooldown=60)}
        self.entered_at = clock()
        self.suspended = False
        self._context = None
        self._auto = 'idle'
        self._deadline = float('inf')
        self._config = None
        self._raw_music = False
        self._raw_since = clock()
        self._stable_music = False
        self._interacted = False
        self._cooldowns = {}
        self._last_burst = None
        self._pending = None

    def reset_auto(self):
        self._context = None
        self._pending = None

    def configure_actions(self, packs):
        self.action_rules = {key:rule for key,rule in self.action_rules.items()
                             if key in ('daydream','spin')}
        self.loop_seconds = {'spin':.7}
        for key,pack in packs.items():
            self.action_rules[key] = dict(weights=pack.weights,cycles=pack.cycles,
                                          cooldown=pack.cooldown)
            self.loop_seconds[key] = pack.duration
        self.reset_auto()

    def set_suspended(self, value):
        if self.suspended != value:
            self.suspended = value
            self.reset_auto()

    def elapsed(self):
        return max(0., self.clock()-self.entered_at)

    def _observe_music(self, now):
        raw = bool(self.playing)
        if raw != self._raw_music:
            self._raw_music, self._raw_since = raw, now
        if now-self._raw_since >= (1.0 if raw else 1.2):
            self._stable_music = raw

    def _baseline(self, context):
        return 'listen' if context.startswith('music') else 'idle'

    def _rest(self, context, now):
        self._context = context
        self._pending = None
        self._auto = self._baseline(context)
        self.entered_at = now
        low,high = (45,90) if context=='music' else (30,60)
        self._deadline = float('inf') if context.endswith('focus') else now+self.rng.uniform(low,high)

    def _burst(self, now):
        pool = [(key,rule['weights'].get(self._context,0)) for key,rule in self.action_rules.items()
                if rule['weights'].get(self._context,0)>0]
        pool = [(key,weight) for key,weight in pool if self._cooldowns.get(key,0)<=now]
        if len(pool)>1:
            pool = [(key,weight) for key,weight in pool if key != self._last_burst]
        if not pool:
            self._deadline = now+5
            return
        state = self.rng.choices([x[0] for x in pool],[x[1] for x in pool])[0]
        self._auto = state
        self._last_burst = state
        self.entered_at = now
        rule=self.action_rules[state]
        if 'hold' in rule:
            duration = self.rng.uniform(*rule['hold'])
        else:
            minimum,maximum = rule['cycles']
            duration = self.loop_seconds[state]*self.rng.randint(minimum,maximum)
        self._deadline = now+duration
        # Include the burst itself so cooldown counts from its planned end.
        self._cooldowns[state] = self._deadline+rule['cooldown']

    def interact(self, state, seconds=3):
        self.interaction_started = self.clock()
        self.temporary, self.until = state, self.interaction_started + seconds
        self._interacted = True

    def state(self):
        now = self.clock()
        self._observe_music(now)
        config = (self.mode,self.follow_music,self.focus)
        if config != self._config:
            self._config = config
            self.entered_at = now
            self.reset_auto()
        if self.temporary and now < self.until:
            return self.temporary
        self.temporary = None
        if self._interacted:
            self._interacted = False
            self.reset_auto()
        if self.mode == 'quiet':
            return 'idle'
        if self.mode != 'auto':
            return self.mode
        context = 'music' if self._stable_music and self.follow_music else 'daily'
        if self.focus:
            context += '_focus'
        if self.suspended:
            return self._baseline(context)
        if self._context is None:
            self._rest(context,now)
        elif context != self._context:
            # Automatic context changes finish the current clip loop first.
            cycle = self.loop_seconds.get(self._auto)
            if cycle and self._auto != self._baseline(self._context):
                if not self._pending or self._pending[0]!=context:
                    boundary = self.entered_at+math.ceil((now-self.entered_at)/cycle)*cycle
                    self._pending = (context,min(boundary,self._deadline))
                if now >= self._pending[1]:
                    self._rest(context,now)
                else:
                    return self._auto
            else:
                self._rest(context,now)
        else:
            self._pending = None
        if now >= self._deadline:
            if self._auto != self._baseline(context):
                self._rest(context,now)
            else:
                self._burst(now)
        return self._auto
