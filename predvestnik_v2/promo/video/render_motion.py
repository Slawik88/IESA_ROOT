"""Narrative motion pilot: animated chat, continuous UI camera, pointer and voice.

All characters/messages are fictional. UI is the existing captured renderer.
No real moderation action or real testimonial is depicted.
"""
from __future__ import annotations
from pathlib import Path
from functools import lru_cache
import argparse
import json
import math
import subprocess
import sys
import wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.runtime'))
import imageio_ffmpeg

W, H, FPS, SECONDS = 720, 1280, 30, 18
BG, WHITE, GREY = '#101017', '#faf8f2', '#b9b7c6'
LIME, RED, PURPLE = '#d4ff57', '#ff667e', '#bba4ff'
OUT = ROOT / 'out' / 'motion_v2'
OUT.mkdir(exist_ok=True)
PANELS = {n: Image.open(ROOT / 'assets' / f'{n}.png').convert('RGB') for n in ('candidates', 'skipped')}

@lru_cache(maxsize=80)
def font(size, bold=True):
    return ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf', size)

def txt(d, pos, value, size=40, color=WHITE, bold=True):
    d.text(tuple(round(v) for v in pos), value, fill=color, font=font(size, bold))

def ease(x):
    x = max(0, min(1, x)); return 1-(1-x)**3

def spring(x):
    x = max(0, min(1, x)); return 1 + math.exp(-8*x)*math.sin(13*x-1.57) if x < 1 else 1

def mix(a,b,x): return a+(b-a)*max(0,min(1,x))

def caption(im, lines, t, start, color=WHITE):
    d = ImageDraw.Draw(im)
    offset = 65*(1-ease((t-start)/.32))
    for i,line in enumerate(lines):
        txt(d,(48,155+i*75+offset),line,62,color)

def bubble(im, top, start, t, name, lines, mine=False):
    if t < start: return
    v = spring((t-start)/.42)
    bw, bh = 560, 74+len(lines)*45
    left = 105 if mine else 48
    card = Image.new('RGB',(bw,bh),'#353c2d' if mine else '#282430')
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle((0,0,bw-1,bh-1),22,fill='#353c2d' if mine else '#282430')
    txt(cd,(22,10),name,22,LIME if mine else PURPLE)
    for i,line in enumerate(lines): txt(cd,(22,44+i*45),line,33,WHITE,False)
    txt(cd,(bw-76,bh-28),'19:42',16,GREY,False)
    card = card.resize((max(1,round(bw*v)),max(1,round(bh*v))),Image.Resampling.LANCZOS)
    im.paste(card,(left+round((bw-card.width)/2),top+round((bh-card.height)/2)))

def cursor(d,x,y,click=0):
    if click>0:
        r=18+42*click
        d.ellipse((x-r,y-r,x+r,y+r),outline=LIME,width=max(1,round(5*(1-click))))
    d.polygon([(x,y),(x+6,y+44),(x+17,y+29),(x+34,y+29)],fill='white',outline='#15151d',width=3)

def panel(im,t):
    # Pan from the participant's name toward the real Skip button. The image
    # underneath is the current UI renderer, not an invented product screen.
    p = PANELS['skipped' if t>=10.25 else 'candidates']
    z=ease((t-7.4)/.9)
    scale=mix(.52,1.18,z)
    if t<8.2: focus=mix(600,380,z)
    elif t<9.0: focus=mix(380,860,ease((t-8.2)/.8))
    else: focus=860
    if t>=10.25:
        scale=mix(1.18,.63,ease((t-10.5)/.7))
        focus=mix(860,600,ease((t-10.5)/.7))
    # Keep the first row in the visual centre even as its layout shrinks.
    row_y=319 if t>=10.25 else 349
    px=round(350-focus*scale); py=round(650-row_y*scale)
    rendered=p.resize((round(p.width*scale),round(p.height*scale)),Image.Resampling.LANCZOS)
    layer=Image.new('RGB',(624,485),'#16151e')
    layer.paste(rendered,(px-48,py-430))
    mask=Image.new('L',layer.size); ImageDraw.Draw(mask).rounded_rectangle((0,0,623,484),26,fill=255)
    im.paste(layer,(48,430),mask)
    d=ImageDraw.Draw(im)
    d.rounded_rectangle((48,430,672,915),26,outline='#555164',width=2)
    txt(d,(65,386),'ПРЕДВЕСТНИК / ПАНЕЛЬ ЧИСТКИ',23,GREY)
    if 8.85<t<10.8:
        progress=ease((t-8.85)/1.1)
        targetx=px+1110*scale; targety=py+row_y*scale
        x=mix(550,targetx,progress); y=mix(945,targety,progress)
        cursor(d,x,y,(t-10.25)/.5 if 10.25<=t<10.75 else 0)
    if t>=9.1:
        d.rounded_rectangle((330,936,666,1001),17,fill=LIME)
        txt(d,(355,947),'ПРОПУСТИТЬ',33,'#14180d')

def frame(t):
    im=Image.new('RGB',(W,H),BG); d=ImageDraw.Draw(im)
    # Quiet moving background keeps depth without competing with dialogue.
    for i in range(9):
        y=round((i*182-t*28)%1550)-170
        d.line((0,y,720,y-170),fill='#201e2a',width=2)
    txt(d,(48,75),'ПОСТАНОВОЧНЫЙ СЮЖЕТ · ТЕСТОВЫЕ ДАННЫЕ',19,GREY)
    txt(d,(48,1155),'ПОСТОЯЛЫЙ ДВОР × ПРЕДВЕСТНИК',22,GREY)
    if t<2.9:
        caption(im,['12 сообщений.','КИКАЕМ?'],t,0)
        d=ImageDraw.Draw(im)
        s=spring(min(1,t/.5)); r=115*s
        cx=355+math.sin(t*14)*max(0,1-t)*8
        d.ellipse((cx-r,495-r,cx+r,495+r),fill=PURPLE)
        txt(d,(cx-36,438),'Л',86,'#20152e')
        txt(d,(272,641),'ЛЕНА',43,WHITE)
        # Large animated counter is editorial, not a fabricated app widget.
        value=round(12*ease(t/.5))
        txt(d,(223,712),f'{value:02d} / 50',76,RED)
        txt(d,(205,807),'сообщений за неделю',27,GREY,False)
        pulse=1+.025*math.sin(t*12)
        bx=175-round(8*pulse)
        d.rounded_rectangle((bx,902,550,1006),25,fill=RED)
        txt(d,(235,920),'КИК?',55,'#25101a')
        cursor(d,510+20*math.sin(t),965)
        txt(d,(219,1040),'мысли админа',24,GREY,False)
    elif t<6.0:
        caption(im,['А человек','просто на смене.'],t,2.9,LIME)
        d=ImageDraw.Draw(im)
        txt(d,(48,379),'ПОСТОЯЛЫЙ ДВОР',26,PURPLE)
        bubble(im,438,2.95,t,'Лена',['я на смене до вечера'])
        bubble(im,615,3.75,t,'Лена',['не выгоняйте, я живая'])
        bubble(im,792,4.65,t,'Админ',['ой.'],True)
        if t<3.2:
            for i in range(3):
                yy=470+math.sin(t*13-i)*5
                d.ellipse((90+i*30,yy,102+i*30,yy+12),fill=GREY)
    elif t<11.7:
        caption(im,['Бот — список.','Ты — решение.'] if t<9.8 else ['Лену?','ПРОПУСТИТЬ.'],t,6 if t<9.8 else 9.8,LIME if t>=9.8 else WHITE)
        panel(im,t)
        d=ImageDraw.Draw(im)
        if t<9.1: txt(d,(65,980),'Смотри контекст. Выбирай действие.',29,GREY,False)
        if t>=10.65:
            txt(d,(65,1040),'ОСТАЁТСЯ В ЧАТЕ',40,LIME)
    elif t<14.4:
        caption(im,['Лена остаётся.','Чат живёт дальше.'],t,11.7,LIME)
        d=ImageDraw.Draw(im)
        txt(d,(48,379),'ПОСТОЯЛЫЙ ДВОР',26,PURPLE)
        bubble(im,455,11.75,t,'Лена',['всё, я дома. кто в игру?'])
        bubble(im,660,12.45,t,'Марк',['мы тебя ждали'],True)
        for i in range(12):
            a=i*2.4+t*.6; rad=150+(t-11.7)*65
            x=360+math.cos(a)*rad; y=960+math.sin(a)*rad*.4
            d.ellipse((x,y,x+6,y+6),fill=LIME)
    else:
        caption(im,['Меньше рутины.','Решение — твоё.'],t,14.4,LIME)
        d=ImageDraw.Draw(im)
        shift=80*(1-ease((t-14.4)/.5))
        txt(d,(49,470+shift),'ПРЕДВЕСТНИК',65,WHITE)
        txt(d,(52,570+shift),'Чистка с решением по каждому',30,GREY,False)
        d.rounded_rectangle((48,740+shift,654,853+shift),25,fill=LIME)
        txt(d,(78,769+shift),'@predvestnik_bot',46,'#15190c')
        txt(d,(53,887+shift),'Открой бота → добавь в свой чат',30,WHITE,False)
        if t>16.6:
            txt(d,(50,1033),'А 12 сообщений — повод кикать?',30,PURPLE)
    # A brief motion wipe connects the chat and the actual product shot.
    for cut in (2.9,6,11.7,14.4):
        dt=t-cut
        if 0<=dt<.14:
            x=round((dt/.14)*1000)-280
            ImageDraw.Draw(im).polygon([(x,0),(x+210,0),(x+40,H),(x-170,H)],fill=LIME)
    return im

VOICE_STARTS=[.05,2.92,6.02,8.0,9.9,11.78,14.5]

def audio(dest):
    rate=48000; time=np.arange(rate*SECONDS)/rate
    beat=np.zeros(len(time),dtype=np.float64)
    rng=np.random.default_rng(17)
    # Original electronic bed: kick, snare, offbeat hat, two-note bass.
    bpm=126; step=60/bpm
    for b,ts in enumerate(np.arange(0,SECONDS,step)):
        dt=time-ts; active=(dt>=0)&(dt<.23)
        a=dt[active]
        beat[active]+=.15*np.sin(2*np.pi*(48*a+5*(1-np.exp(-30*a))))*np.exp(-20*a)
        if b%2:
            active=(dt>=0)&(dt<.12); a=dt[active]
            beat[active]+=.038*rng.standard_normal(len(a))*np.exp(-30*a)
        dt=time-ts-step/2; active=(dt>=0)&(dt<.045); a=dt[active]
        beat[active]+=.024*rng.standard_normal(len(a))*np.exp(-90*a)
    beat += .016*np.sin(2*np.pi*55*time)*(np.sin(2*np.pi*time/step)>.3)
    # Break under the correction: audible stop, then rebuild beneath the UI.
    beat[(time>=2.9)&(time<6)]*=.08
    for ts,f in [(2.97,900),(3.77,1100),(4.67,620),(10.25,1300),(11.8,880),(12.5,1050)]:
        dt=time-ts; ix=(dt>=0)&(dt<.16); a=dt[ix]
        beat[ix]+=.2*np.sin(2*np.pi*f*a)*np.exp(-28*a)
    for ts in [2.9,6,11.7,14.4]:
        dt=time-ts; ix=(dt>=0)&(dt<.14); a=dt[ix]
        beat[ix]+=.06*rng.standard_normal(len(a))*np.sin(np.pi*a/.14)
    voice=np.zeros_like(beat); timings=[]
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    for i,start in enumerate(VOICE_STARTS):
        source=ROOT/'assets'/f'voice_{i:02}.wav'
        decoded=subprocess.run([ffmpeg,'-v','error','-i',str(source),'-f','f32le','-ac','1','-ar',str(rate),'-'],capture_output=True,check=True)
        samples=np.frombuffer(decoded.stdout,dtype='<f4').astype(np.float64)
        available=(VOICE_STARTS[i+1]-.10-start) if i+1<len(VOICE_STARTS) else SECONDS-.15-start
        duration=len(samples)/rate
        if duration>available:
            tempo=duration/available
            decoded=subprocess.run([ffmpeg,'-v','error','-i',str(source),'-af',f'atempo={tempo:.6f}',
                                    '-f','f32le','-ac','1','-ar',str(rate),'-'],capture_output=True,check=True)
            samples=np.frombuffer(decoded.stdout,dtype='<f4').astype(np.float64)
        samples=samples[:round(available*rate)]
        samples*=.82/max(.01,np.max(np.abs(samples)))
        at=round(start*rate); end=min(len(voice),at+len(samples))
        voice[at:end]+=samples[:end-at]
        timings.append({'start':start,'duration':len(samples)/rate,'file':source.name})
    # Duck the bed around narration; retain event transients in the background.
    mixed=np.tanh((beat*.65+voice)*1.1)*.87
    with wave.open(str(dest),'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate)
        f.writeframes((mixed*32767).astype('<i2').tobytes())
    return timings

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--preview-only',action='store_true'); args=parser.parse_args()
    moments=[.8,3.5,5.3,7.3,9.55,10.7,12.9,15.5]
    sheet=Image.new('RGB',(960,854),BG)
    for i,t in enumerate(moments):
        f=frame(t); f.save(OUT/f'frame_{i:02}.jpg',quality=92)
        sheet.paste(f.resize((240,427)),((i%4)*240,(i//4)*427))
    sheet.save(OUT/'storyboard.jpg',quality=94)
    if args.preview_only: return
    timings=audio(OUT/'soundtrack.wav')
    dest=OUT/'predvestnik_motion_v2.mp4'
    command=[imageio_ffmpeg.get_ffmpeg_exe(),'-y','-hide_banner','-loglevel','warning','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-i',str(OUT/'soundtrack.wav'),'-vf','scale=1080:1920:flags=lanczos','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-movflags','+faststart','-shortest',str(dest)]
    with (OUT/'render.log').open('w') as log:
        proc=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=log)
        try:
            for i in range(FPS*SECONDS):
                proc.stdin.write(frame(i/FPS).tobytes())
                if i%(FPS*3)==0: print(f'Rendered {i/FPS:.0f}/{SECONDS}s',flush=True)
        finally: proc.stdin.close()
        if proc.wait(): raise RuntimeError('Encoder failed')
    manifest={'status':'rendered_demo','file':dest.name,'duration_seconds':SECONDS,'fps':FPS,'size':[1080,1920],
              'source_render_size':[W,H], 'fictional_chat':True,'real_backend_actions':False,
              'ui':'Existing app.07.js loadPurgePanel captures, animated camera and pointer; fixture state change',
              'voice':'Local Windows Pavel synthetic Russian voice','audio':'Original synthesized beat and effects',
              'voice_timing':timings,'retention':'Untested; no publication metrics','variant':'Narrative motion v2'}
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Created {dest} ({dest.stat().st_size:,} bytes)',flush=True)

if __name__=='__main__': main()
