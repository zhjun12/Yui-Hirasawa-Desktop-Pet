import json
from pathlib import Path
import tempfile
import unittest

from core import Animation, Pomodoro, Store, cloud_url


class CoreTests(unittest.TestCase):
    def test_pause_preserves_precise_remaining_and_finishes_once(self):
        now = [100.0]
        p = Pomodoro(lambda: now[0])
        p.start('focus', 60)
        now[0] += 14.5
        p.toggle_pause()
        now[0] += 100
        self.assertEqual(p.remaining(), 46)
        self.assertIsNone(p.poll())
        p.toggle_pause()
        now[0] += 45.5
        self.assertEqual(p.poll(), 'focus')
        self.assertIsNone(p.poll())
        self.assertEqual(p.phase, 'idle')

    def test_interaction_restores_fixed_action_even_with_music(self):
        now = [0.0]
        a = Animation(lambda: now[0])
        a.mode, a.playing = 'listen', True
        a.interact('eat', 3)
        self.assertEqual(a.state(), 'eat')
        now[0] = 4
        self.assertEqual(a.state(), 'listen')
        a.mode = 'auto'
        self.assertEqual(a.state(), 'listen')
        now[0] = 20
        self.assertEqual(a.state(), 'listen')
        a.playing, a.focus = False, True
        self.assertEqual(a.state(), 'listen')
        now[0] += 1.21
        self.assertEqual(a.state(), 'idle')

    def test_links_cannot_open_arbitrary_scheme_or_similar_domain(self):
        self.assertEqual(cloud_url(' https://music.163.com/#/playlist?id=123 '),
                         'https://music.163.com/#/playlist?id=123')
        for url in ['file:///C:/a.exe', 'https://music.163.com.example.com/',
                    'https://music.163.com@evil.test/', 'javascript:alert(1)',
                    'https://music.163.com:123/']:
            with self.assertRaises(ValueError):
                cloud_url(url)

    def test_store_recovers_corruption_and_roundtrips_unicode(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            path = Path(folder) / 'settings.json'
            path.write_text('{ broken', encoding='utf-8')
            store = Store(path)
            self.assertTrue(store.warning)
            store.data['tracks'] = ['E:/歌曲/ふわふわ時間.mp3']
            store.data['mode'] = 'listen'
            store.save()
            recovered = Store(path)
            self.assertEqual(recovered.data['tracks'], store.data['tracks'])
            self.assertEqual(recovered.data['mode'], 'listen')

    def test_store_validates_unexpected_shapes(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            path = Path(folder) / 'settings.json'
            path.write_text(json.dumps(dict(size='large', tracks=[1, 'a', 'a'],
                volume=-200, position=['x', 0], links=[{'name': 'bad', 'url': 'file:///a'}])), encoding='utf-8')
            store = Store(path)
            self.assertEqual(store.data['size'], 280)
            self.assertEqual(store.data['volume'], 0)
            self.assertEqual(store.data['tracks'], ['a'])
            self.assertEqual(store.data['links'], [])
            self.assertNotIn('position', store.data)


if __name__ == '__main__':
    unittest.main()
