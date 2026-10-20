"""Cancellable directory import. Workers never touch widgets or user settings."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import time
from PySide6.QtCore import QThread, Signal
from core import AUDIO_EXTENSIONS


def path_key(path):
    return os.path.normcase(os.path.abspath(os.path.normpath(str(path))))


@dataclass
class ImportResult:
    paths: list = field(default_factory=list)
    duplicates: int = 0
    unsupported: int = 0
    encrypted: int = 0
    inspected: int = 0
    errors: list = field(default_factory=list)
    failed: int = 0
    cancelled: bool = False

    def summary(self):
        state = '已取消，保留已发现结果' if self.cancelled else '导入完成'
        return (f'{state}：新增 {len(self.paths)} 首，重复 {self.duplicates} 首，'
                f'跳过 {self.unsupported} 项（其中加密文件 {self.encrypted}），读取失败 {self.failed} 项。')


class LibraryScanner(QThread):
    progress = Signal(int, int)
    result_ready = Signal(object)

    def __init__(self, roots, existing=(), parent=None, scan_dir=None):
        super().__init__(parent)
        self.roots = [str(x) for x in roots]
        self.existing = {path_key(x) for x in existing}
        self.scan_dir = scan_dir or os.scandir

    def run(self):
        result = ImportResult()
        seen = set(self.existing)
        pending = list(reversed(self.roots))
        last_update = 0
        def failure(path, exc):
            result.failed += 1
            if len(result.errors) < 30:
                result.errors.append(f'{path}: {exc}')
        while pending and not self.isInterruptionRequested():
            path = pending.pop()
            try:
                if os.path.islink(path):
                    result.unsupported += 1
                    continue
                if os.path.isdir(path):
                    try:
                        with self.scan_dir(path) as entries:
                            for entry in entries:
                                if self.isInterruptionRequested():
                                    break
                                try:
                                    if entry.is_symlink():
                                        result.unsupported += 1
                                    elif entry.is_dir(follow_symlinks=False):
                                        pending.append(entry.path)
                                    else:
                                        self._file(entry.path, seen, result)
                                except OSError as exc:
                                    failure(entry.path, exc)
                                if time.monotonic() - last_update > .1:
                                    self.progress.emit(result.inspected, len(result.paths))
                                    last_update = time.monotonic()
                    except OSError as exc:
                        failure(path, exc)
                else:
                    self._file(path, seen, result)
            except OSError as exc:
                failure(path, exc)
        result.cancelled = self.isInterruptionRequested()
        self.progress.emit(result.inspected, len(result.paths))
        self.result_ready.emit(result)

    @staticmethod
    def _file(path, seen, result):
        result.inspected += 1
        extension = Path(path).suffix.lower()
        if extension not in AUDIO_EXTENSIONS:
            result.unsupported += 1
            result.encrypted += extension in {'.ncm', '.uc', '.qmcflac', '.qmc0', '.kgm'}
            return
        try:
            if not os.path.isfile(path):
                raise FileNotFoundError('文件已不存在')
            if os.path.getsize(path) == 0:
                raise ValueError('空音频文件')
        except (OSError, ValueError) as exc:
            result.failed += 1
            if len(result.errors) < 30:
                result.errors.append(f'{path}: {exc}')
            return
        key = path_key(path)
        if key in seen:
            result.duplicates += 1
        else:
            seen.add(key)
            result.paths.append(os.path.abspath(path))
