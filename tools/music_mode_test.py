"""Native acceptance for the approved transparent music-pet surface."""
import json
from pathlib import Path
import sys
import wave as wave_audio
from tempfile import TemporaryDirectory
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent
from PySide6.QtGui import QEnterEvent,QMouseEvent
from app import Controller,ROOT,STYLE


class FakeMedia:
    def __init__(self): self.commands=[]
    def request(self,*args): self.commands.append(args)
    def stop(self): pass
    def isRunning(self): return False


app=QApplication([]);app.setQuitOnLastWindowClosed(False)
app.setStyleSheet(STYLE)
with TemporaryDirectory(dir=ROOT) as temp:
    root=Path(temp);c=Controller(app,root/'settings.json',services=False);c.media=FakeMedia()
    try:
        original=c.pet.pos()
        row=dict(id='cloudmusic.exe',label='网易云',kind='smtc',title='放课后的练习曲',artist='播放器测试',
            album='本地测试',playing=True,status=4,position=2.,duration=180.,can_toggle=True,
            can_next=True,can_previous=True,can_seek=True)
        snapshot=dict(sessions=[row],error='',cloud_running=True)
        c.media_snapshot(snapshot);QTest.qWait(350)
        assert c.music_state.active and c.music.isVisible() and not c.pet.isVisible()
        assert c.music.testAttribute(Qt.WA_TranslucentBackground)
        assert not c.music.mask().isEmpty() and not c.music.mask().contains(QPoint(c.music.width()-1,1))
        assert c.music.actor.pixmap() and not c.music.actor.pixmap().isNull()
        assert c.music.current.text()==row['title'] and c.music.following.text()==row['artist']
        QTest.mouseDClick(c.music.current,Qt.LeftButton)
        assert not c.music.dialog.isVisible()
        assert c.music.current.y()>=c.music.actor.geometry().bottom()
        assert c.music.current.font().pixelSize()==13 and c.music.following.font().pixelSize()==10
        assert all(button.geometry().right()<c.music.actor.x() for button in c.music.buttons)
        QTest.mouseClick(c.music.next,Qt.LeftButton)
        assert c.media.commands[-1]==('cloudmusic.exe','next',None)
        QTest.mouseClick(c.music.play,Qt.LeftButton)
        assert c.media.commands[-1]==('cloudmusic.exe','toggle',None)
        assert row['playing'] is True
        button=c.music.next
        QApplication.sendEvent(button,QEnterEvent(QPointF(10,10),QPointF(10,10),QPointF(button.mapToGlobal(QPoint(10,10)))))
        positions=[QPoint(item.pos()) for item in c.music.buttons];wave=c.music.effect_time
        QTest.qWait(180)
        assert positions==[item.pos() for item in c.music.buttons] and c.music.effect_time>wave
        QApplication.sendEvent(button,QEvent(QEvent.Leave))
        QTest.qWait(250)
        assert positions!=[item.pos() for item in c.music.buttons]
        count=len(c.media.commands);center=button.rect().center();global_point=button.mapToGlobal(center)
        QTest.mousePress(button,Qt.LeftButton,pos=center)
        move=QMouseEvent(QEvent.MouseMove,QPointF(center+QPoint(30,20)),QPointF(global_point+QPoint(30,20)),Qt.NoButton,Qt.LeftButton,Qt.NoModifier)
        QApplication.sendEvent(button,move)
        QTest.mouseRelease(button,Qt.LeftButton,pos=button.rect().center())
        assert len(c.media.commands)==count and 'next' in c.store.data['music_bubbles']
        c.music.reset_bubbles()
        lyrics=root/'demo.lrc'
        lyrics.write_text('[00:01]今天从这一页开始\n[00:03]和唯一起慢慢练习\n[00:05]休息一下再出发',encoding='utf-8')
        c.music.document=c.music.library.import_file(c.music.key,lyrics);c.music.populate_lyrics();c.music.refresh()
        assert c.music.current.text()==row['title'] and c.music.following.text()==row['artist']
        assert c.music.last_lyric is None
        c.music.lyrics_enabled=True;c.music.refresh()
        assert c.music.current.text()=='今天从这一页开始'
        row['position']=4;c.music.refresh();assert c.music.current.text()=='和唯一起慢慢练习'
        c.music.offset.setValue(1500);assert c.music.current.text()=='休息一下再出发'
        c.set_mode('sing_guitar');QTest.qWait(80)
        c.music.lyrics_enabled=False;c.music.refresh()
        c.music.grab().save(str(ROOT/'output/music-pet-native.png'))
        c.music.lyrics_enabled=True
        c.set_mode('auto')
        row['duration']=0;c.music.refresh()
        assert c.music.last_lyric==-1 and '未提供进度' in c.music.dialog.hint.text()
        c.music.open_lyrics();c.music.dialog.lines.setCurrentRow(1)
        assert c.music.current.text()=='和唯一起慢慢练习'
        c.music.dialog.hide()
        row['title']='另一首测试曲';c.music.refresh()
        assert c.music.document is None and '暂无歌词' in c.music.current.text()
        c.music.lyrics_enabled=False;c.music.refresh()
        assert c.music.current.text()==row['title'] and c.music.following.text()==row['artist']
        row['artist']='';c.music.refresh();assert c.music.following.text()==''
        row['title']='很长的歌名'*50;c.music.refresh()
        assert c.music.current.toolTip()==row['title'] and c.music.current.text().endswith('…')
        row['title']='另一首测试曲';row['artist']='播放器测试';c.music.refresh()
        row['playing']=False;c.media_snapshot(snapshot)
        assert c.music_state.active and c.music.head.text=='已暂停'
        wave=c.music.effect_time;QTest.qWait(100);assert c.music.effect_time==wave
        for edge in ('left','right','top','bottom'):
            c.dock.target_screen=c.music.screen();c.dock.collapse(edge);QTest.qWait(300)
            assert c.dock.label.isVisible() and not c.music.isVisible() and not c.pet.isVisible()
            assert not c.pet.animation_timer.isActive()
            c.dock.restore(animated=False)
            assert c.music.isVisible() and not c.pet.isVisible() and c.pet.animation_timer.isActive()
        c.set_topmost(False);assert not c.pet.isVisible() and c.music.isVisible()
        c.start_timer('focus');c.music.refresh();assert '专注' in c.music.timer_label.text()
        c.leave_music_mode();assert c.pet.isVisible() and not c.music.isVisible() and c.pet.pos()==original
        c.media_snapshot(snapshot);assert not c.music_state.active
        c.dock.collapse('right');QTest.qWait(300);c.enter_music_mode()
        assert c.dock.hidden and c.dock.label.isVisible() and not c.music.isVisible()
        c.dock.restore(animated=False);assert c.music.isVisible() and not c.pet.isVisible()
        c.leave_music_mode();assert c.pet.pos()==original
        c.stop_timer();c.enter_music_mode()
        for size in (180,480,280):
            c.set_size(size);c.music.refresh_avatar()
            assert c.music.actor.width()==size and not c.music.mask().isEmpty()
        c.music_state.seen=True
        with patch('app.time.monotonic',return_value=100): c.observe_music_client({'cloud_running':False})
        with patch('app.time.monotonic',return_value=109): c.observe_music_client({'cloud_running':False})
        assert not c.music_state.active
        audio=root/'本地同步测试.wav'
        with wave_audio.open(str(audio),'wb') as sample:
            sample.setnchannels(1);sample.setsampwidth(2);sample.setframerate(22050)
            sample.writeframes(b'\0\0'*22050*5)
        c.audio.setMuted(True);c.add_tracks([audio]);c.play(0);QTest.qWait(400)
        c.enter_music_mode();c.music.document=c.music.library.import_file(c.music.key,lyrics)
        c.music.lyrics_enabled=True
        c.music.populate_lyrics();c.player.setPosition(1400);QTest.qWait(200);c.music.refresh()
        assert c.music.current.text()=='今天从这一页开始' and c.music.song['position'] is not None
        c.music.lyrics_enabled=False;c.music.refresh()
        assert c.music.current.text()==audio.stem and c.music.following.text()=='' and c.music.last_lyric is None
        c.toggle_active();QTest.qWait(100)
        assert c.music.head.text=='已暂停' or not c.animation.playing
        report=dict(auto_enter=True,transparent_surface=True,actor_not_duplicated=True,
            mv_lyrics_below=True,small_left_bubbles=True,targeted_controls=True,no_fake_playback=True,
            bubble_hover_freezes=True,bubble_leave_resumes=True,bubble_drag_without_skip=True,
            bubble_positions_saved=True,head_effect_stops_on_pause=True,lyrics_sync=True,
            offset_saved=True,no_timeline_manual_selection=True,song_change_clears_lyrics=True,
            four_edge_restore=True,hidden_entry_stays_hidden=True,study_continues=True,
            original_position_restored=True,manual_suppression=True,three_sizes=True,client_exit_returns_pet=True,
            real_local_audio_lyrics=True,song_title_and_artist=True,lyrics_hidden_by_default=True,
            no_lyrics_on_double_click=True,long_title_elided=True,missing_artist_cleared=True)
        (ROOT/'output/music-mode-check.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report),flush=True)
    finally:c.quit()
