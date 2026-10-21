from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from lyrics import parse_lyrics,lyric_index,song_key,LyricsLibrary


class LyricsTests(unittest.TestCase):
    def test_multiple_timestamps_and_fraction_precision(self):
        doc=parse_lyrics('[ar:Someone]\n[00:01.5][01:02.05]同一句\n[00:02.123]第二句')
        self.assertEqual(doc['lines'],[[1500,'同一句'],[2123,'第二句'],[62050,'同一句']])

    def test_duplicate_timestamps_merge_translation(self):
        self.assertEqual(parse_lyrics('[00:01]Hello\n[00:01]你好')['lines'],[[1000,'Hello\n你好']])

    def test_offset_and_seek_recompute_current_line(self):
        doc=parse_lyrics('[offset:500]\n[00:01]一\n[00:05]二')
        self.assertEqual(lyric_index(doc,.5),0)
        self.assertEqual(lyric_index(doc,5),1)
        self.assertEqual(lyric_index(doc,0),-1)
        self.assertEqual(lyric_index(doc,None),-1)

    def test_plain_text_and_empty_rejection(self):
        self.assertEqual(parse_lyrics('第一行\n第二行')['plain'],['第一行','第二行'])
        with self.assertRaises(ValueError): parse_lyrics('[ar:Artist]\n')

    def test_song_bindings_distinguish_artist_album_and_local_paths(self):
        self.assertNotEqual(song_key('cloud','Song','A'),song_key('cloud','Song','B'))
        self.assertNotEqual(song_key('cloud','Song','A','Live'),song_key('cloud','Song','A','Studio'))
        self.assertNotEqual(song_key('local',path='one/song.mp3'),song_key('local',path='two/song.mp3'))

    def test_import_utf16_and_persist_without_changing_original(self):
        with TemporaryDirectory() as temp:
            folder=Path(temp);source=folder/'歌曲.lrc'
            raw='[00:01.0]测试'.encode('utf-16');source.write_bytes(raw)
            library=LyricsLibrary(folder/'bindings');key=song_key('cloud','测试')
            doc=library.import_file(key,source)
            self.assertEqual(library.load(key),doc);self.assertEqual(source.read_bytes(),raw)
            self.assertEqual(doc['lines'],[[1000,'测试']])

    def test_invalid_binding_is_ignored_and_path_traversal_is_rejected(self):
        with TemporaryDirectory() as temp:
            folder=Path(temp);library=LyricsLibrary(folder);key=song_key('cloud','测试')
            (folder/f'{key}.json').write_text('{bad')
            self.assertIsNone(library.load(key))
            with self.assertRaises(ValueError): library.save('../settings',{})
