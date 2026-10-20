"""Extract original GIF timing and matte the animated foreground."""
import hashlib
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description='从用户提供的啃玉米 GIF 制作透明动作帧')
parser.add_argument('source', type=Path, help='原始 GIF 文件路径')
SOURCE = parser.parse_args().source.expanduser().resolve()
OUTPUT = ROOT / 'assets/corn'
OUTPUT.mkdir(parents=True, exist_ok=True)
gif = Image.open(SOURCE)
durations = []
preview = Image.new('RGB', (1000, 500), '#f7f6f0')
for index in range(gif.n_frames):
    gif.seek(index)
    durations.append(max(20, gif.info.get('duration', 100)))
    rgb = np.array(gif.convert('RGB'))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    mask = np.zeros(rgb.shape[:2], np.uint8)
    # Shared silhouette seed: hair, hand, corn and jacket. The artwork is cut
    # at the lower image edge; retain that original half-body composition.
    outline = np.array([(0,480),(52,372),(95,337),(96,291),(106,232),
        (117,175),(145,105),(194,61),(255,44),(292,52),(321,40),
        (345,65),(388,81),(431,91),(412,112),(443,152),(434,182),
        (455,220),(447,268),(438,294),(450,324),(434,346),
        (411,379),(403,435),(416,500),(0,500)], np.int32)
    cv2.fillPoly(mask, [outline], cv2.GC_PR_FGD)
    expanded = cv2.dilate((mask > 0).astype(np.uint8), np.ones((21,21), np.uint8))
    mask[(expanded > 0) & (mask == 0)] = cv2.GC_PR_BGD
    cv2.ellipse(mask, (268,207), (66,94), 0,0,360,cv2.GC_FGD,-1)
    cv2.ellipse(mask, (276,109), (76,39), 0,0,360,cv2.GC_FGD,-1)
    cv2.ellipse(mask, (313,339), (97,23), -8,0,360,cv2.GC_FGD,-1)
    cv2.ellipse(mask, (120,374), (39,23), -35,0,360,cv2.GC_FGD,-1)
    cv2.rectangle(mask,(130,430),(355,499),cv2.GC_FGD,-1)
    yy, xx = np.indices(mask.shape)
    hair = ((rgb[:,:,0].astype(float) > rgb[:,:,1]*1.35)
            & (rgb[:,:,1].astype(float) > rgb[:,:,2]*1.3)
            & (xx > 103) & (xx < 445) & (yy > 48) & (yy < 319)
            & (mask != cv2.GC_BGD))
    mask[hair] = cv2.GC_FGD
    cv2.grabCut(bgr, mask, None, np.zeros((1,65)), np.zeros((1,65)),5,cv2.GC_INIT_WITH_MASK)
    foreground = np.isin(mask, (cv2.GC_FGD,cv2.GC_PR_FGD)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(foreground)
    if count > 1:
        foreground = (labels == (1 + np.argmax(stats[1:,cv2.CC_STAT_AREA]))).astype(np.uint8)
    alpha = cv2.GaussianBlur(foreground.astype(np.float32),(3,3),.45)
    alpha = (alpha*255).astype(np.uint8)
    frame = Image.fromarray(np.dstack((rgb,alpha)))
    frame.save(OUTPUT / f'{index:02d}.png')
    thumb = frame.resize((250,250))
    preview.paste(thumb,(index*250,0),thumb)
    original = Image.fromarray(rgb).resize((250,250))
    preview.paste(original,(index*250,250))
manifest = dict(name='啃玉米', frame_count=gif.n_frames, durations_ms=durations,
                duration_ms=sum(durations), source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                source='user-supplied GIF', method='original GIF frames with foreground matting')
(OUTPUT/'motion.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
preview.save(ROOT/'output/corn-preview.png')
print(json.dumps(manifest,ensure_ascii=False,indent=2))
