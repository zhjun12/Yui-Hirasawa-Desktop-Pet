import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import cv2
import numpy as np
from PIL import Image,ImageDraw
from action_packs import load_pack,discover_packs
from action_pipeline import import_action,seconds,time_range
from core import Animation,Store

ROOT=Path(__file__).resolve().parents[1]


def sample(folder,key='wave'):
    folder.mkdir(parents=True,exist_ok=True)
    for index in range(2):
        image=Image.new('RGBA',(96,96),(0,0,0,0))
        ImageDraw.Draw(image).ellipse((20+index*5,20,65+index*5,80),fill='#8b633a')
        image.save(folder/f'{index:03d}.png')
    info=dict(schema_version=1,id=key,name='测试挥手',fps=10,frame_count=2,
              durations_ms=[80,140],playback=dict(weights=dict(daily=100),cycles=[1,2],
                                                cooldown_seconds=30,manual_cycles=2))
    (folder/'motion.json').write_text(json.dumps(info),encoding='utf-8')
    return folder


class PackTests(unittest.TestCase):
    def test_variable_frame_timing_and_wrap(self):
        with TemporaryDirectory(dir=ROOT) as temp:
            pack=load_pack(sample(Path(temp)/'wave'))
            self.assertEqual([pack.frame_index(t) for t in (0,.079,.08,.219,.221)],[0,0,1,1,0])
            self.assertAlmostEqual(pack.duration,.22)

    def test_missing_and_escaping_frame_rejected(self):
        with TemporaryDirectory(dir=ROOT) as temp:
            folder=sample(Path(temp)/'wave')
            (folder/'001.png').unlink()
            with self.assertRaisesRegex(ValueError,'缺失'): load_pack(folder)
            info=json.loads((folder/'motion.json').read_text())
            info['frame_files']=['000.png','../outside.png']
            (folder/'motion.json').write_text(json.dumps(info))
            with self.assertRaisesRegex(ValueError,'目录内'): load_pack(folder)

    def test_bad_pack_does_not_block_good_pack(self):
        with TemporaryDirectory(dir=ROOT) as temp:
            root=Path(temp)
            sample(root/'wave')
            (root/'broken').mkdir()
            (root/'broken/motion.json').write_text('{')
            packs,errors=discover_packs(root)
            self.assertEqual(list(packs),['wave'])
            self.assertEqual(len(errors),1)

    def test_new_id_is_scheduled_and_persisted_without_code_changes(self):
        with TemporaryDirectory(dir=ROOT) as temp:
            folder=Path(temp)
            pack=load_pack(sample(folder/'wave'))
            now=[1000.]
            class Rng:
                def uniform(self,a,b): return (a+b)/2
                def choices(self,items,weights): return ['wave']
                def randint(self,a,b): return a
            animation=Animation(lambda:now[0],Rng())
            animation.configure_actions({'wave':pack})
            self.assertEqual(animation.state(),'idle')
            now[0]+=45
            self.assertEqual(animation.state(),'wave')
            now[0]+=.221
            self.assertEqual(animation.state(),'idle')
            store=Store(folder/'settings.json',modes={'wave'})
            store.data['mode']='wave'
            store.save()
            self.assertEqual(Store(store.path,modes={'wave'}).data['mode'],'wave')


class PipelineTests(unittest.TestCase):
    def test_time_formats_and_invalid_ranges(self):
        self.assertEqual(seconds('1:51.2'),111.2)
        self.assertEqual(seconds('1:02:03.5'),3723.5)
        self.assertEqual(time_range('1:51.2～1:52.6'),(111.2,112.6))
        for value in (-1,True,'1:99','nonsense',float('nan')):
            with self.assertRaises(ValueError): seconds(value)
        with self.assertRaises(ValueError): time_range([5,2])

    def test_prepared_pack_gets_common_canvas_preview_and_install(self):
        with TemporaryDirectory(dir=ROOT) as temp:
            root=Path(temp)
            source=sample(root/'source')
            result=import_action(dict(id='wave',name='挥手',source=str(source),max_size=160),root,install=True)
            self.assertTrue(result['passed'])
            folder=Path(result['installed'])
            pack=load_pack(folder)
            self.assertEqual(pack.ends_ms,(80.,220.))
            qa=json.loads((folder/'qa.json').read_text(encoding='utf-8'))
            self.assertEqual(qa['output_padding'],20)
            self.assertTrue((folder/'preview.gif').is_file())
            self.assertTrue((folder/'contact.png').is_file())
            for file in pack.files:
                image=np.array(Image.open(file))
                self.assertFalse(np.any(image[:8,:,3]))
                self.assertFalse(np.any(image[-8:,:,3]))

    def test_gif_preserves_nonuniform_durations(self):
        with TemporaryDirectory(dir=ROOT) as temp:
            root=Path(temp)
            source=sample(root/'source')
            frames=[Image.open(source/f'{i:03d}.png').convert('RGBA') for i in range(2)]
            gif=root/'input.gif'
            frames[0].save(gif,save_all=True,append_images=frames[1:],duration=[80,140],disposal=2,loop=0)
            result=import_action(dict(id='wave',name='挥手',source=str(gif),max_size=160),root)
            self.assertEqual(load_pack(result['output']).ends_ms,(80.,220.))

    def test_head_crop_fails_without_installing(self):
        with TemporaryDirectory(dir=ROOT) as temp:
            root=Path(temp)
            image=Image.new('RGB',(160,120),'#f2aaa8')
            ImageDraw.Draw(image).ellipse((40,-20,120,80),fill='#906b40')
            image.save(root/'cropped.png')
            with self.assertRaisesRegex(ValueError,'原片头顶'):
                import_action(dict(id='wave',name='挥手',source=str(root/'cropped.png'),profile='yui_pink'),root,install=True)
            self.assertFalse((root/'actions/wave').exists())
            self.assertTrue(list((root/'output/action-imports').glob('*/qa.json')))

    def test_replacement_requires_flag_and_failed_copy_rolls_back(self):
        with TemporaryDirectory(dir=ROOT) as temp:
            root=Path(temp)
            source=sample(root/'source')
            job=dict(id='wave',name='挥手',source=str(source),max_size=160)
            original=import_action(job,root,install=True)
            path=Path(original['installed'])/'motion.json'
            before=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'同名动作'):
                import_action(job,root,install=True)
            self.assertEqual(path.read_bytes(),before)
            with patch('action_pipeline.shutil.copytree',side_effect=OSError('disk fail')):
                with self.assertRaisesRegex(ValueError,'disk fail'):
                    import_action(job,root,install=True,replace=True)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(load_pack(path.parent).id,'wave')

    def test_out_of_range_video_is_rejected(self):
        with TemporaryDirectory(dir=ROOT) as temp:
            root=Path(temp)
            source=root/'short.avi'
            writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'MJPG'),10,(160,120))
            self.assertTrue(writer.isOpened())
            for _ in range(5): writer.write(np.full((120,160,3),120,np.uint8))
            writer.release()
            with self.assertRaisesRegex(ValueError,'超出视频时长'):
                import_action(dict(id='wave',name='挥手',source=str(source),range=['1:51','1:52']),root)


if __name__=='__main__': unittest.main()
