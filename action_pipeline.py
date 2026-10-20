"""Decode -> foreground profile -> common canvas -> QA -> transactional action pack.

The importer interprets a declarative job, never executes code from a job/pack.
Visual character recognition remains a separate review when no head profile is supplied.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import uuid
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageSequence
from action_packs import load_pack,RESERVED

ROOT=Path(__file__).resolve().parent


def working_frame(image,job):
    maximum=int(job.get('working_max_size',960))
    if not 96<=maximum<=1920: raise ValueError('处理尺寸应为 96～1920 像素')
    factor=min(1.,maximum/max(image.shape[:2]))
    if factor<1:
        image=cv2.resize(image,(round(image.shape[1]*factor),round(image.shape[0]*factor)),interpolation=cv2.INTER_AREA)
    return image


def seconds(value):
    if type(value) in (int,float):
        number=float(value)
    elif isinstance(value,str) and re.fullmatch(r'\d+(?::\d{1,2}){0,2}(?:\.\d+)?',value.strip()):
        parts=value.strip().split(':')
        if any(float(part)>=60 for part in parts[1:]):
            raise ValueError('时间的秒/分钟部分不能大于等于 60')
        number=0.
        for part in parts: number=number*60+float(part)
    else:
        raise ValueError('时间格式应为秒数、分:秒或时:分:秒')
    if not math.isfinite(number) or number<0: raise ValueError('时间不能为负数或无限值')
    return number


def time_range(value):
    if isinstance(value,str):
        value=re.split(r'\s*[-～–—]\s*',value.strip())
    if not isinstance(value,(list,tuple)) or len(value)!=2:
        raise ValueError('时间段应为 [开始,结束] 或 1:51.2-1:52.6')
    start,end=map(seconds,value)
    if end<=start or end-start>60: raise ValueError('动作应为 0～60 秒的有效片段')
    return start,end


def component(mask):
    count,labels,stats,_=cv2.connectedComponentsWithStats(mask.astype(np.uint8),8)
    if count<=1: raise ValueError('没有识别到前景人物')
    return (labels==1+np.argmax(stats[1:,cv2.CC_STAT_AREA])).astype(np.uint8)*255


def decode(job):
    source=Path(job['source']).expanduser().resolve()
    if source.is_dir():
        pack=load_pack(source)
        frames=[working_frame(np.array(Image.open(path).convert('RGBA')),job) for path in pack.files]
        ends=(0.,)+pack.ends_ms
        return frames,[ends[i+1]-ends[i] for i in range(len(frames))],source
    if not source.is_file(): raise ValueError('素材文件不存在')
    if source.suffix.lower() in ('.gif','.png','.webp','.apng'):
        with Image.open(source) as image:
            frames=[]
            durations=[]
            for frame in ImageSequence.Iterator(image):
                frames.append(working_frame(np.array(frame.convert('RGBA')),job))
                durations.append(max(10,float(frame.info.get('duration',100))))
                if len(frames)>600: raise ValueError('素材超过 600 帧，请先截取')
                if len(frames)*frames[0].shape[0]*frames[0].shape[1]>64000000:
                    raise ValueError('素材解码体积过大，请缩小 working_max_size 或缩短片段')
        if 'range' in job:
            start,end=time_range(job['range'])
            if end>sum(durations)/1000+.001: raise ValueError('时间段超出图片动画时长')
            selected=[]
            times=[]
            cursor=0.
            for frame,duration in zip(frames,durations):
                overlap=max(0.,min(cursor+duration,end*1000)-max(cursor,start*1000))
                if overlap>0: selected.append(frame); times.append(overlap)
                cursor+=duration
            frames,durations=selected,times
        return frames,durations,source
    if 'range' not in job: raise ValueError('视频素材必须指定时间段')
    start,end=time_range(job['range'])
    cap=cv2.VideoCapture(str(source))
    try:
        fps=cap.get(cv2.CAP_PROP_FPS)
        count=cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if not cap.isOpened() or not math.isfinite(fps) or fps<=0:
            raise ValueError('视频无法读取或帧率无效')
        if end>count/fps+.001: raise ValueError(f'时间段超出视频时长（约 {count/fps:.2f} 秒）')
        first,last=math.ceil(start*fps-1e-6),math.ceil(end*fps-1e-6)
        if not 1<=last-first<=600: raise ValueError('片段应包含 1～600 帧')
        cap.set(cv2.CAP_PROP_POS_FRAMES,first)
        frames=[]
        for _ in range(last-first):
            ok,frame=cap.read()
            if not ok: raise ValueError('视频解码未完成，未安装该动作')
            frames.append(working_frame(cv2.cvtColor(frame,cv2.COLOR_BGR2RGBA),job))
            if len(frames)*frames[0].shape[0]*frames[0].shape[1]>64000000:
                raise ValueError('素材解码体积过大，请缩小 working_max_size 或缩短片段')
        return frames,[1000/fps]*len(frames),source
    finally:
        cap.release()


def foreground(frames,job):
    profile=job.get('profile','alpha')
    output=[]
    head_tops=[]
    source_edges=0
    for rgba in frames:
        rgba=rgba.copy()
        if max(rgba.shape[:2])>4096: raise ValueError('原素材尺寸超过 4096，请先缩小')
        if 'roi' in job:
            x,y,w,h=map(int,job['roi'])
            if min(x,y)<0 or min(w,h)<=0 or x+w>rgba.shape[1] or y+h>rgba.shape[0]:
                raise ValueError('取景范围超出原图')
            rgba=rgba[y:y+h,x:x+w].copy()
        rgb=rgba[:,:,:3].copy()
        for box in job.get('subtitle_regions',[]):
            x,y,w,h=map(int,box)
            if min(x,y)<0 or min(w,h)<=0 or x+w>rgb.shape[1] or y+h>rgb.shape[0]:
                raise ValueError('字幕清理区域超出画面')
            hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
            white=((hsv[y:y+h,x:x+w,1]<30)&(hsv[y:y+h,x:x+w,2]>210)).astype(np.uint8)*255
            mask=np.zeros(rgb.shape[:2],np.uint8)
            mask[y:y+h,x:x+w]=cv2.dilate(white,np.ones((11,11),np.uint8))
            rgb=cv2.inpaint(rgb,mask,4,cv2.INPAINT_TELEA)
        hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
        if profile=='alpha':
            alpha=rgba[:,:,3]
            if np.all(alpha==255): raise ValueError('素材没有透明背景，请指定去背景处理方案')
        elif profile=='yui_pink':
            alpha=component(~(((hsv[:,:,0]<8)|(hsv[:,:,0]>170))&(hsv[:,:,2]>170)))
        elif profile=='chroma':
            color=np.array(job['background_rgb'],np.float32)
            if color.shape!=(3,): raise ValueError('背景色需要 RGB 三个数值')
            distance=np.linalg.norm(rgb.astype(np.float32)-color,axis=2)
            alpha=component(distance>float(job.get('color_tolerance',45)))
        elif profile=='grabcut':
            rectangle=tuple(map(int,job['foreground_rect']))
            x,y,w,h=rectangle
            if min(x,y)<0 or min(w,h)<=0 or x+w>rgb.shape[1] or y+h>rgb.shape[0]:
                raise ValueError('前景范围超出画面')
            mask=np.zeros(rgb.shape[:2],np.uint8)
            cv2.grabCut(rgb,mask,rectangle,np.zeros((1,65)),np.zeros((1,65)),3,cv2.GC_INIT_WITH_RECT)
            alpha=component(np.isin(mask,[cv2.GC_FGD,cv2.GC_PR_FGD]))
        else:
            raise ValueError('不支持的去背景方案：'+str(profile))
        if profile!='alpha':
            alpha=cv2.morphologyEx(alpha,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
            if job.get('fill_holes',profile=='yui_pink'):
                contours,_=cv2.findContours(alpha,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(alpha,contours,-1,255,-1)
            alpha=cv2.GaussianBlur(alpha,(3,3),.4)
        if not np.any(alpha>0): raise ValueError('出现空白动作帧')
        if np.any(alpha[0]) or np.any(alpha[-1]) or np.any(alpha[:,0]) or np.any(alpha[:,-1]):
            source_edges+=1
        if job.get('check_yui_head',profile=='yui_pink'):
            hair=component((hsv[:,:,0]>8)&(hsv[:,:,0]<30)&(hsv[:,:,1]>50)&
                           (hsv[:,:,2]>60)&(hsv[:,:,2]<195))
            head_top=cv2.boundingRect(hair)[1]
            head_tops.append(head_top)
            if head_top<int(job.get('head_margin',8)):
                raise ValueError('原片头顶靠近或碰到画面边缘，请换片段；加透明边距不能补回缺失的头顶')
        output.append(np.dstack([rgb,alpha]))
    return output,dict(head_checked=bool(head_tops),source_head_top_min=min(head_tops) if head_tops else None,
                       source_touches_edge_frames=source_edges)


def common_canvas(frames,job):
    if len({frame.shape for frame in frames})!=1: raise ValueError('输入帧的画布大小不一致')
    anchor=job.get('anchor','none')
    if anchor=='lower_torso':
        aligned=[]
        h,w=frames[0].shape[:2]
        for frame in frames:
            hsv=cv2.cvtColor(frame[:,:,:3],cv2.COLOR_RGB2HSV)
            shirt=(hsv[:,:,0]>70)&(hsv[:,:,0]<110)&(hsv[:,:,1]>20)&(frame[:,:,3]>0)
            positions=np.where(shirt[int(h*.96):])[1]
            if not positions.size: raise ValueError('找不到下摆锚点，请改用 anchor=none 或调整取景')
            shift=w-int(np.median(positions))
            canvas=np.zeros((h,w*2,4),np.uint8)
            canvas[:,shift:shift+w]=frame
            aligned.append(canvas)
        frames=aligned
    elif anchor!='none': raise ValueError('不支持的锚点方式')
    union=np.zeros(frames[0].shape[:2],np.uint8)
    for frame in frames: union|=(frame[:,:,3]>0).astype(np.uint8)
    x,y,w,h=cv2.boundingRect(union)
    maximum=int(job.get('max_size',480))
    padding=int(job.get('padding',20))
    if not 96<=maximum<=768 or not 8<=padding<=64: raise ValueError('画布大小或边距超出允许范围')
    # Reserve padding in final pixels, then apply one identical transform to all frames.
    factor=(maximum-2*padding)/max(w,h)
    width,height=max(1,round(w*factor)),max(1,round(h*factor))
    if len(frames)*(width+2*padding)*(height+2*padding)>32000000:
        raise ValueError('输出动作包过大，请减少 max_size 或缩短片段')
    output=[]
    for frame in frames:
        crop=frame[y:y+h,x:x+w]
        # Premultiplication prevents colored/black fringes during resampling.
        premult=crop.astype(np.float32)
        premult[:,:,:3]*=premult[:,:,3:4]/255
        resized=cv2.resize(premult,(width,height),interpolation=cv2.INTER_AREA if factor<1 else cv2.INTER_LINEAR)
        alpha=resized[:,:,3:4]
        resized[:,:,:3]=np.divide(resized[:,:,:3]*255,alpha,
                                  out=np.zeros_like(resized[:,:,:3]),where=alpha>0)
        resized=np.clip(resized,0,255).astype(np.uint8)
        output.append(cv2.copyMakeBorder(resized,padding,padding,padding,padding,
                                         cv2.BORDER_CONSTANT,value=(0,0,0,0)))
    return output,dict(union_crop=[x,y,w,h],anchor=anchor,output_padding=padding,
                       uniform_scale=factor)


def quality(frames,source_checks,canvas_checks,job):
    errors=[]
    warnings=[]
    if not source_checks['head_checked']: warnings.append('未配置人物头部识别；请在预览确认原片没有缺头')
    if source_checks['source_touches_edge_frames'] and job.get('composition')=='full-body':
        errors.append('素材声明为全身，但人物触及原画面边缘，可能缺少身体部分，请换素材或更正构图声明')
    elif source_checks['source_touches_edge_frames'] and job.get('composition') not in ('half-body','close-up'):
        warnings.append('原片有人物像素接触画面边缘；输出已留边，但不能补画原片缺失部分')
    shapes={frame.shape for frame in frames}
    if len(shapes)!=1: errors.append('输出画布不统一')
    bounds=[]
    for frame in frames:
        alpha=frame[:,:,3]
        x,y,w,h=cv2.boundingRect((alpha>0).astype(np.uint8))
        if not w or not h: errors.append('输出有空白帧'); break
        if min(x,y,frame.shape[1]-x-w,frame.shape[0]-y-h)<8: errors.append('输出安全边距不足'); break
        bounds.append([x,y,w,h])
    def painted(frame):
        a=frame[:,:,3:4].astype(float)/255
        return frame[:,:,:3]*a+245*(1-a)
    seam=float(np.abs(painted(frames[0])-painted(frames[-1])).mean()/255)
    if job.get('loop',True) and seam>float(job.get('seam_warning',.12)): warnings.append('首尾差异较大，建议检查循环接缝')
    if len(frames)>1 and not any(np.any(frame!=frames[0]) for frame in frames[1:]):
        warnings.append('所有帧相同，将表现为静态动作')
    return dict(passed=not errors,errors=errors,warnings=warnings,frames=len(frames),
                seam_difference=round(seam,5),frame_bounds=bounds,**source_checks,**canvas_checks)


def preview(frames,durations,folder):
    samples=list(dict.fromkeys(np.linspace(0,len(frames)-1,min(8,len(frames)),dtype=int)))
    contact=Image.new('RGB',(240*len(samples),270),'#f7f6f0')
    draw=ImageDraw.Draw(contact)
    images=[]
    for index,frame in enumerate(frames):
        rgba=Image.fromarray(frame)
        canvas=Image.new('RGBA',rgba.size,'#f7f6f0')
        canvas.alpha_composite(rgba)
        images.append(canvas.convert('RGB'))
        if index in samples:
            tile=canvas.convert('RGB')
            tile.thumbnail((230,240),Image.Resampling.LANCZOS)
            column=samples.index(index)
            contact.paste(tile,(column*240+(240-tile.width)//2,240-tile.height))
            draw.text((column*240+8,248),str(index),fill='#315c50')
    contact.save(folder/'contact.png')
    images[0].save(folder/'preview.gif',save_all=True,append_images=images[1:],
                   duration=[round(value) for value in durations],loop=0,disposal=2)


def import_action(job,workspace=ROOT,install=False,replace=False,install_root=None):
    workspace=Path(workspace).resolve()
    if not isinstance(job,dict): raise ValueError('每个动作任务应为 JSON 对象')
    key=job.get('id','')
    if not isinstance(key,str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}',key) or key in RESERVED:
        raise ValueError('请填写有效且不与内置动作重名的 id')
    name=job.get('name')
    if not isinstance(name,str) or not name.strip(): raise ValueError('请填写动作名称')
    output=workspace/'output/action-imports'/f'{key}-{uuid.uuid4().hex[:10]}'
    output.mkdir(parents=True)
    try:
        frames,durations,source=decode(job)
        if not frames or sum(durations)>60000: raise ValueError('素材为空或超过 60 秒')
        frames,source_checks=foreground(frames,job)
        frames,canvas_checks=common_canvas(frames,job)
        report=quality(frames,source_checks,canvas_checks,job)
        for index,frame in enumerate(frames): Image.fromarray(frame).save(output/f'{index:03d}.png')
        manifest=dict(schema_version=1,id=key,name=name,frame_count=len(frames),
            fps=max(1,min(120,round(1000/float(np.median(durations)),6))),durations_ms=durations,
            frame_files=[f'{i:03d}.png' for i in range(len(frames))],
            duration=sum(durations)/1000,loop=job.get('loop',True),source=source.name,composition=job.get('composition','original'),
            button_label=job.get('button_label',name),bubble=job.get('bubble',name+'～'),
            playback=job.get('playback',dict(weights=dict(daily=10,music=0),
                            cycles=[1,2] if job.get('loop',True) else [1,1],
                            cooldown_seconds=90,manual_cycles=2 if job.get('loop',True) else 1)))
        if source.is_file(): manifest['source_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
        if 'range' in job: manifest['source_interval']=list(time_range(job['range']))
        (output/'motion.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        load_pack(output)
        preview(frames,durations,output)
        (output/'qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        installed=None
        if install and report['passed']:
            root=Path(install_root or workspace/'actions').resolve()
            if not root.is_relative_to(workspace): raise ValueError('安装目录必须位于当前项目内')
            root.mkdir(parents=True,exist_ok=True)
            target=root/key
            if target.resolve().parent!=root: raise ValueError('安装目标路径越界')
            if target.exists() and not replace: raise ValueError('同名动作已存在；显式选择 replace 才可更新')
            backup=None
            if target.exists():
                backup=workspace/'output/action-backups'/f'{key}-{uuid.uuid4().hex[:10]}'
                backup.parent.mkdir(parents=True,exist_ok=True)
                target.rename(backup)
            try:
                shutil.copytree(output,target)
                load_pack(target)
            except Exception:
                if target.exists():
                    failed=workspace/'output/action-imports'/f'{key}-failed-{uuid.uuid4().hex[:10]}'
                    target.rename(failed)
                if backup: backup.rename(target)
                raise
            installed=str(target)
        return dict(id=key,passed=report['passed'],output=str(output),installed=installed,
                    warnings=report['warnings'],errors=report['errors'])
    except Exception as exc:
        (output/'qa.json').write_text(json.dumps(dict(passed=False,errors=[str(exc)]),ensure_ascii=False,indent=2),encoding='utf-8')
        raise ValueError(f'{exc}（检查记录：{output / "qa.json"}）') from exc


def main():
    parser=argparse.ArgumentParser(description='将视频/GIF/透明帧目录转换为可直接载入的动作包')
    parser.add_argument('job',type=Path)
    parser.add_argument('--install',action='store_true')
    parser.add_argument('--replace',action='store_true')
    parser.add_argument('--install-root',type=Path)
    args=parser.parse_args()
    data=json.loads(args.job.read_text(encoding='utf-8-sig'))
    jobs=data if isinstance(data,list) else [data]
    results=[]
    for job in jobs:
        try: results.append(import_action(job,install=args.install,replace=args.replace,install_root=args.install_root))
        except Exception as exc: results.append(dict(id=job.get('id','') if isinstance(job,dict) else '',passed=False,errors=[str(exc)]))
    print(json.dumps(results,ensure_ascii=False,indent=2))
    return 0 if all(result['passed'] for result in results) else 2


if __name__=='__main__': raise SystemExit(main())
