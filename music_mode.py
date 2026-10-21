"""View lifecycle independent of playback, animation, and lyrics."""


class MusicModeState:
    def __init__(self):
        self.active=False
        self.suppressed=False
        self.seen=False
        self.absent_since=None
        self.offered=False
        self.cloud_owned=False

    def enter(self,cloud=False):
        self.active=True
        self.cloud_owned=cloud
        self.offered=False

    def leave(self,manual=True):
        self.active=False
        self.cloud_owned=False
        if manual:
            self.suppressed=True
            self.offered=False

    def observe(self,now,present,enabled,local_playing=False):
        if present is None:
            self.absent_since=None
            return None
        if present:
            self.absent_since=None
            if not self.seen:
                self.seen=True
                if enabled and not self.suppressed:
                    if local_playing:
                        self.offered=True
                        return 'offer'
                    return 'enter'
        elif self.seen:
            if self.absent_since is None: self.absent_since=now
            if now-self.absent_since>=8:
                should_exit=self.active and self.cloud_owned
                self.seen=False
                self.suppressed=False
                self.offered=False
                self.absent_since=None
                if should_exit: return 'exit'
        return None
