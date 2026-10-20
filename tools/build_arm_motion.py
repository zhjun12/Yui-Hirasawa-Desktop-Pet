"""Matte a short user-supplied video action, retaining its original drawn poses.

Pose-guided GrabCut is applied to video frames, not generative redrawing. All
coordinates are in the 960x540 analysis view. Only a single closed cycle inside
71s-72s is exported, with a fixed half-body crop and common anchor.
"""
import json
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'output/arm-reference/frames'
OUTPUT = ROOT / 'assets/arm-spin'
OUTPUT.mkdir(parents=True, exist_ok=True)

# head center, guitar body center, supporting wrist, headstock, swing elbow/wrist
POSES = {
    0: ((470, 94), (466, 225), (605, 155), (677, 144), (491, 132), (540, 129)),
    2: ((470, 93), (465, 222), (602, 153), (677, 137), (449, 79), (486, 43)),
    5: ((450, 91), (452, 220), (597, 138), (674, 110), (418, 86), (420, 34)),
    7: ((450, 99), (450, 224), (591, 125), (663, 91), (407, 108), (396, 63)),
    10: ((451, 109), (447, 233), (586, 120), (657, 79), (410, 120), (395, 78)),
    12: ((451, 108), (447, 233), (586, 119), (656, 81), (404, 127), (376, 97)),
    15: ((447, 109), (450, 239), (589, 124), (663, 89), (388, 174), (350, 167)),
    18: ((452, 108), (453, 234), (596, 136), (670, 99), (407, 205), (372, 240)),
    19: ((459, 103), (457, 229), (602, 138), (674, 107), (423, 193), (421, 238)),
    20: ((467, 100), (461, 229), (606, 143), (677, 107), (439, 180), (465, 218)),
}

def line(mask, points, value, width):
    cv2.polylines(mask, [np.asarray(points, np.int32)], False, value, width, cv2.LINE_8)
    for point in points:
        cv2.circle(mask, tuple(map(int, point)), width // 2, value, -1)

def make_frame(index):
    path = INPUT / f'frame-{index:02d}.png'
    image = cv2.imread(str(path))
    if image is None:
        raise RuntimeError(f'Missing reference frame {index}')
    pose_key = max(k for k in POSES if k <= index)
    head, body, wrist, tip, elbow, hand = POSES[pose_key]
    nominal = np.zeros(image.shape[:2], np.uint8)
    cv2.ellipse(nominal, head, (36, 43), 0, 0, 360, 255, -1)
    torso = np.array([(440,127),(482,123),(512,171),(537,214),(566,251),
        (557,267),(539,277),(505,284),(473,279),(433,282),(423,266),(429,219),(440,180)], np.int32)
    cv2.fillPoly(nominal, [torso], 255)
    cv2.ellipse(nominal, body, (43, 52), 25, 0, 360, 255, -1)
    line(nominal, [(head[0] + 15, 139), (535, wrist[1] - 2), wrist], 255, 22)
    line(nominal, [(head[0] - 20, 146), elbow, hand], 255, 21)
    line(nominal, [(body[0] + 4, body[1] - 17), tip], 255, 19)
    line(nominal, [(tip[0] - 23, tip[1] + 6), tip], 255, 30)
    line(nominal, [(455, 277), (453, 305)], 255, 28)
    line(nominal, [(523, 266), (551, 305)], 255, 32)

    mask = np.full(image.shape[:2], cv2.GC_BGD, np.uint8)
    expanded = cv2.dilate(nominal, np.ones((13, 13), np.uint8))
    mask[expanded > 0] = cv2.GC_PR_BGD
    mask[nominal > 0] = cv2.GC_PR_FGD
    sure = np.zeros_like(nominal)
    cv2.ellipse(sure, head, (23, 31), 0, 0, 360, 255, -1)
    cv2.fillPoly(sure, [np.array([(451,145),(476,145),(499,174),(514,216),
        (495,261),(448,266),(444,210)], np.int32)], 255)
    cv2.ellipse(sure, body, (27, 37), 25, 0, 360, 255, -1)
    line(sure, [(head[0] + 15, 139), (535, wrist[1] - 2), wrist], 255, 7)
    line(sure, [(head[0] - 20, 146), elbow, hand], 255, 6)
    line(sure, [(body[0] + 4, body[1] - 17), tip], 255, 6)
    mask[sure > 0] = cv2.GC_FGD

    # The crop excludes all classroom furniture and lower legs consistently.
    x, y, width, height = 326, 12, 380, 288
    small = image[y:y+height, x:x+width].copy()
    small_mask = mask[y:y+height, x:x+width].copy()
    cv2.grabCut(small, small_mask, None, np.zeros((1,65)), np.zeros((1,65)), 4, cv2.GC_INIT_WITH_MASK)
    alpha = np.where((small_mask == cv2.GC_FGD) | (small_mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    # Remove isolated background specks while retaining the connected character.
    count, labels, stats, _ = cv2.connectedComponentsWithStats(alpha, 8)
    if count > 1:
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        alpha[labels != largest] = 0
    alpha = cv2.GaussianBlur(alpha, (3,3), .45)
    rgba = cv2.cvtColor(small, cv2.COLOR_BGR2BGRA)
    rgba[:, :, 3] = alpha
    rgba[alpha == 0, :3] = 0
    cv2.imwrite(str(OUTPUT / f'{index:02d}.png'), rgba)
    return rgba

frames = [make_frame(i) for i in range(21)]
manifest = dict(name='呆唯 · 手臂大回旋', fps=30, frame_count=21,
    duration=.7, source_interval=[71, 71.7], reference_interval=[71,72],
    source='user-supplied 892734230-1-208.mp4', crop='half-body',
    method='original video poses, pose-guided foreground matting; no redrawing')
(OUTPUT / 'motion.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
preview = np.full((288*2, 380*3, 3), 245, np.uint8)
for tile, index in enumerate([0,2,5,10,15,18]):
    fg = frames[index]
    alpha = fg[:,:,3:4].astype(np.float32) / 255
    composite = (fg[:,:,:3] * alpha + 245 * (1-alpha)).astype(np.uint8)
    r, c = divmod(tile, 3)
    preview[r*288:(r+1)*288, c*380:(c+1)*380] = composite
cv2.imwrite(str(ROOT / 'output/arm-reference/matte-preview.jpg'), preview)
print(json.dumps(manifest, ensure_ascii=False))
