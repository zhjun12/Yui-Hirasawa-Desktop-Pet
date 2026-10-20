"""Local-only audio features. No recording files and no microphone input."""
import math
import time
import numpy as np
from PySide6.QtCore import QThread, Signal


class AudioFeatures:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.energy = 0.0
        self.smooth = 0.0
        self.floor = .004
        self.last_onset = -100.0
        self.last_time = clock()

    def feed(self, samples, rate=48000):
        now = self.clock()
        data = np.asarray(samples, dtype=np.float32)
        data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
        rms = float(np.sqrt(np.mean(np.square(np.clip(data, -1, 1))))) if data.size else 0.0
        dt = max(.001, min(.3, now - self.last_time))
        self.last_time = now
        previous = self.smooth
        attack = .045 if rms > previous else .24
        self.smooth += (rms - self.smooth) * (1 - math.exp(-dt / attack))
        self.floor += (rms - self.floor) * (1 - math.exp(-dt / 2.5))
        onset = rms > max(.012, previous * 1.55, self.floor * 1.4) and now - self.last_onset > .24
        if onset:
            self.last_onset = now
        # Energy response, not an asserted BPM estimate.
        level = min(1.0, math.sqrt(max(0, self.smooth - .0015)) * 3.0)
        self.energy = level
        return {'level': level, 'onset': onset, 'rms': rms, 'time': now}


class SystemAudio(QThread):
    features = Signal(object)
    status = Signal(str)

    def run(self):
        import pyaudiowpatch as pa
        extractor = AudioFeatures()
        last_notice = None
        while not self.isInterruptionRequested():
            audio, stream = None, None
            try:
                audio = pa.PyAudio()
                device = audio.get_default_wasapi_loopback()
                if not device.get('isLoopbackDevice'):
                    raise RuntimeError('所选设备不是系统输出回环，已拒绝采集。')
                rate = int(device['defaultSampleRate'])
                channels = min(2, int(device['maxInputChannels']))
                if channels < 1:
                    raise RuntimeError('当前输出设备不可用。')
                stream = audio.open(format=pa.paFloat32, channels=channels, rate=rate,
                    input=True, input_device_index=device['index'], frames_per_buffer=1024)
                message = '正在分析系统声音：' + device['name']
                if message != last_notice:
                    self.status.emit(message)
                    last_notice = message
                device_check = time.monotonic() + 2
                while not self.isInterruptionRequested():
                    raw = stream.read(1024, exception_on_overflow=False)
                    samples = np.frombuffer(raw, dtype=np.float32)
                    self.features.emit(extractor.feed(samples, rate))
                    if time.monotonic() >= device_check:
                        device_check = time.monotonic() + 2
                        if audio.get_default_wasapi_loopback()['index'] != device['index']:
                            break
            except Exception as exc:
                message = '系统声音暂不可用，稍后重连：' + str(exc)
                if message != last_notice:
                    self.status.emit(message)
                    last_notice = message
                for _ in range(10):
                    if self.isInterruptionRequested():
                        break
                    self.msleep(100)
            finally:
                if stream:
                    try:
                        stream.stop_stream()
                        stream.close()
                    except Exception:
                        pass
                if audio:
                    audio.terminate()


class MotionEnvelope:
    def __init__(self):
        self.phase = 0.0
        self.level = 0.0
        self.target = 0.0
        self.onset = 0.0
        self.last = time.monotonic()

    def update(self, now, active, level, responsive=True):
        dt = min(.1, max(0, now - self.last))
        self.last = now
        self.target = (.28 + .72 * level) if active else 0.0
        if not responsive:
            self.target = .38
        tau = .18 if self.target > self.level else .45
        self.level += (self.target - self.level) * (1 - math.exp(-dt / tau))
        self.onset *= math.exp(-dt / .13)
        self.phase += dt * (2.0 + .45 * level) * min(1, self.level * 3)
        return self.phase, self.level, self.onset
