"""Windows media sessions and explicit CloudMusic-window fallback.

No global media keys, injection, login, or HTTP service. Commands stay on their
selected session/window. Metadata access runs off the GUI thread.
"""
import asyncio
import ctypes
from ctypes import wintypes
import queue
from PySide6.QtCore import QThread, Signal


def cloud_windows():
    import psutil
    user = ctypes.windll.user32
    result = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    def visit(hwnd, unused):
        name = ctypes.create_unicode_buffer(128)
        user.GetClassNameW(hwnd, name, 128)
        if name.value != 'OrpheusBrowserHost':
            return True
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            if psutil.Process(pid.value).name().lower() != 'cloudmusic.exe':
                return True
        except (psutil.Error, OSError):
            return True
        title = ctypes.create_unicode_buffer(user.GetWindowTextLengthW(hwnd) + 1)
        user.GetWindowTextW(hwnd, title, len(title))
        if title.value:
            result.append({'hwnd': int(hwnd), 'pid': pid.value, 'title': title.value})
        return True
    callback = callback_type(visit)
    user.EnumWindows(callback, 0)
    return result


def window_command(hwnd, command):
    if not any(item['hwnd'] == hwnd for item in cloud_windows()):
        raise RuntimeError('网易云窗口已关闭，请重新连接。')
    number = {'toggle': 14, 'next': 11, 'previous': 12}.get(command)
    if number is None:
        raise RuntimeError('兼容模式不支持这个操作。')
    user = ctypes.windll.user32
    user.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
        wintypes.LPARAM, wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
    user.SendMessageTimeoutW.restype = wintypes.LPARAM
    result = ctypes.c_size_t()
    if not user.SendMessageTimeoutW(hwnd, 0x0319, hwnd, number << 16, 2, 750, ctypes.byref(result)):
        raise RuntimeError('网易云未响应控制请求。')
    return bool(result.value)


class MediaBridge(QThread):
    snapshot = Signal(object)
    feedback = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.commands = queue.Queue()
        self.loop = None
        self.wake = None

    def request(self, target, command, position=None):
        self.commands.put((target, command, position))
        self.refresh()

    def refresh(self):
        if self.loop and self.wake:
            try:
                self.loop.call_soon_threadsafe(self.wake.set)
            except RuntimeError:
                pass

    def stop(self):
        self.requestInterruption()
        self.refresh()

    def run(self):
        from winrt.runtime import init_apartment, uninit_apartment, ApartmentType
        try:
            init_apartment(ApartmentType.MULTI_THREADED)
            asyncio.run(self.monitor())
        except Exception as exc:
            self.snapshot.emit({'sessions': [], 'error': f'系统媒体连接失败：{exc}'})
        finally:
            self.loop = self.wake = None
            uninit_apartment()

    async def monitor(self):
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
        self.loop, self.wake = asyncio.get_running_loop(), asyncio.Event()
        manager, error = None, ''
        async def acquire():
            return await Manager.request_async()
        try:
            manager = await asyncio.wait_for(acquire(), 5)
        except Exception as exc:
            error = f'系统媒体会话暂不可用：{exc}'
        token = None
        if manager:
            token = manager.add_sessions_changed(lambda *_: self.refresh())
        try:
            while not self.isInterruptionRequested():
                rows, objects = [], {}
                if manager:
                    try:
                        for session in manager.get_sessions():
                            appid = session.source_app_user_model_id
                            info = session.get_playback_info()
                            controls = info.controls
                            async def metadata():
                                return await session.try_get_media_properties_async()
                            props = await asyncio.wait_for(metadata(), 2)
                            timeline = session.get_timeline_properties()
                            position = timeline.position.total_seconds()
                            duration = timeline.end_time.total_seconds()
                            row = dict(id=appid, label=appid, kind='smtc', title=props.title,
                                artist=props.artist, playing=(True if int(info.playback_status) == 4 else
                                    False if int(info.playback_status) in (3, 5) else None),
                                status=int(info.playback_status), position=position, duration=duration,
                                can_toggle=controls.is_play_pause_toggle_enabled or
                                           controls.is_play_enabled or controls.is_pause_enabled,
                                native_toggle=controls.is_play_pause_toggle_enabled,
                                can_play=controls.is_play_enabled, can_pause=controls.is_pause_enabled,
                                can_next=controls.is_next_enabled, can_previous=controls.is_previous_enabled,
                                can_seek=controls.is_playback_position_enabled)
                            rows.append(row)
                            objects[appid] = session
                        error = ''
                    except Exception as exc:
                        error = f'读取系统媒体会话失败：{exc}'
                # Window title is metadata only: it cannot establish playback state.
                has_cloud = any('cloudmusic' in r['id'].lower() or 'netease' in r['id'].lower() for r in rows)
                if not has_cloud:
                    windows = cloud_windows()
                    if windows:
                        window = windows[0]
                        title, separator, artist = window['title'].rpartition(' - ')
                        rows.append(dict(id='netease-window', label='网易云 · 兼容窗口控制', kind='window',
                            title=title if separator else window['title'], artist=artist if separator else '',
                            playing=None, status=None, position=0, duration=0, hwnd=window['hwnd'],
                            can_toggle=True, can_next=True, can_previous=True, can_seek=False))
                while not self.commands.empty():
                    target, command, position = self.commands.get_nowait()
                    row = next((r for r in rows if r['id'] == target), None)
                    try:
                        if not row:
                            raise RuntimeError('目标播放器已断开。')
                        if row['kind'] == 'window':
                            accepted = window_command(row['hwnd'], command)
                            self.feedback.emit('已向网易云窗口发送控制请求；客户端未提供播放状态确认。'
                                               if accepted else '网易云窗口未确认支持该命令。')
                        else:
                            session = objects[target]
                            method = {'toggle': session.try_toggle_play_pause_async,
                                      'next': session.try_skip_next_async,
                                      'previous': session.try_skip_previous_async}.get(command)
                            if command == 'toggle' and not row['native_toggle']:
                                method = session.try_pause_async if row['playing'] else session.try_play_async
                            if command == 'seek':
                                if not row['can_seek'] or position is None:
                                    raise RuntimeError('播放器不支持进度控制。')
                                async def seek():
                                    return await session.try_change_playback_position_async(int(position * 10_000_000))
                                success = await asyncio.wait_for(seek(), 2)
                            elif method and row.get('can_' + command, False):
                                async def control():
                                    return await method()
                                success = await asyncio.wait_for(control(), 2)
                            else:
                                raise RuntimeError('播放器未启用该控制。')
                            self.feedback.emit('播放器已接受控制。' if success else '播放器未接受控制，请在客户端重试。')
                    except Exception as exc:
                        self.feedback.emit(str(exc))
                self.snapshot.emit({'sessions': rows, 'error': error})
                self.wake.clear()
                try:
                    await asyncio.wait_for(self.wake.wait(), 1)
                except asyncio.TimeoutError:
                    pass
        finally:
            if token is not None:
                manager.remove_sessions_changed(token)
