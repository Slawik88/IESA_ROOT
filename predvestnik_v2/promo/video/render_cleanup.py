"""Render a 19s portrait pilot from captured current UI and original graphics/sound."""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import wave
from array import array
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / '.runtime'))
import imageio_ffmpeg

W, H, FPS, DURATION = 1080, 1920, 24, 19
BG, WHITE, MUTED, GOLD, TEAL = '#07080f', '#f1f3fa', '#aab3ca', '#f5d488', '#46c8c0'
REG = 'C:/Windows/Fonts/segoeui.ttf'
BOLD = 'C:/Windows/Fonts/segoeuib.ttf'

SCENES = [
    (0, 3, ['Мало сообщений.', 'Сразу исключать?'], 'candidates', 'Чистка с решением по каждому'),
    (3, 6, ['Выбери период', 'и норму активности.'], 'setup', 'Бот соберёт кандидатов'),
    (6, 9, ['Список готов.', 'Решение — за тобой.'], 'candidates', 'Решение по каждому'),
    (9, 12, ['Этого участника', 'оставляем.'], 'skipped', 'Лена · пропустить'),
    (12, 15, ['А этому —', 'предупреждение.'], 'resolved', 'Марк · выдать варн'),
    (15, 19, ['Бот готовит список.', 'Администратор решает.'], 'resolved', 'Предвестник для вашего чата'),
]

def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else REG, size)

def text(draw, xy, s, size=40, fill=WHITE, bold=False):
    draw.text(xy, s, font=font(size, bold), fill=fill)

def panel(src):
    image = Image.open(HERE / 'assets' / f'{src}.png').convert('RGB')
    width = 944
    height = round(image.height * width / image.width)
    return image.resize((width, height), Image.Resampling.LANCZOS)

def background():
    im = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        d.line((0, y, W, y), fill=(7 + round(4*t), 8 + round(5*t), 15 + round(10*t)))
    glow = Image.new('RGBA', (W, H))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-200, -260, 700, 570), fill=(115, 81, 24, 42))
    gd.ellipse((680, 800, 1320, 1500), fill=(18, 87, 87, 28))
    im = Image.alpha_composite(im.convert('RGBA'), glow.filter(ImageFilter.GaussianBlur(110))).convert('RGB')
    return im

BASE = background()
PANELS = {name: panel(name) for name in ['setup', 'candidates', 'skipped', 'resolved']}
CAPTURE = json.loads((HERE / 'assets' / 'capture_manifest.json').read_text(encoding='utf-8'))
POINTS = {s['name']: [(p['x']*944/s['width'], p['y']*944/s['width']) for p in s['rowPoints']] for s in CAPTURE['states']}

def frame(t):
    index = next((i for i, s in enumerate(SCENES) if s[0] <= t < s[1]), len(SCENES)-1)
    start, end, lines, name, caption = SCENES[index]
    progress = (t-start)/(end-start)
    im = BASE.copy(); d = ImageDraw.Draw(im)
    d.rounded_rectangle((66, 150, 1014, 210), 30, fill='#171b27')
    text(d, (91, 160), 'ПРЕДВЕСТНИК  ×  ПОСТОЯЛЫЙ ДВОР', 29, GOLD, True)
    text(d, (70, 229), 'ТЕСТОВЫЙ ЧАТ · ДЕМОНСТРАЦИЯ', 29, MUTED, True)
    for i, line in enumerate(lines):
        text(d, (68, 285+i*92), line, 72 if index != 5 else 63, WHITE, True)
    text(d, (70, 510), 'МОДЕРАЦИЯ ЧЕРЕЗ ПАНЕЛЬ', 26, MUTED, True)
    y = 615
    p = PANELS[name]
    shadow = Image.new('RGBA', (W, H)); sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((66, y+14, 1016, y+p.height+38), 35, fill=(0, 0, 0, 135))
    im = Image.alpha_composite(im.convert('RGBA'), shadow.filter(ImageFilter.GaussianBlur(20))).convert('RGB')
    im.paste(p, (68, y))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((68, y+p.height+55, 1012, y+p.height+139), 25, fill='#172326')
    text(d, (95, y+p.height+72), caption, 36, TEAL, True)
    # Original editorial callouts, separate from the actual captured UI.
    if index in (3, 4):
        px, py = POINTS[name][0 if index == 3 else 1]
        target_y = y + round(py)
        cx = 68 + round(px)
        r = 16 + round(8 * (0.5 + 0.5*math.sin(progress*math.pi*4)))
        d.ellipse((cx-r, target_y-r, cx+r, target_y+r), outline=GOLD, width=4)
    if index == 5:
        d.rounded_rectangle((68, 1344, 1012, 1494), 30, fill=GOLD)
        text(d, (103, 1363), 'Добавь в свой чат', 43, '#16140d', True)
        text(d, (103, 1421), '@predvestnik_bot', 34, '#42371d')
    elif index in (3, 4):
        _, py = POINTS[name][0 if index == 3 else 1]
        text(d, (70, 1354), 'УВЕЛИЧЕННЫЕ ФРАГМЕНТЫ ПАНЕЛИ', 25, MUTED)
        left = p.crop((0, round(py)-40, 450, round(py)+40)).resize((720,128), Image.Resampling.LANCZOS)
        right = p.crop((p.width-85, round(py)-40, p.width, round(py)+40)).resize((136,128), Image.Resampling.LANCZOS)
        im.paste(left, (68,1410)); im.paste(right, (858,1410)); d = ImageDraw.Draw(im)
    else:
        text(d, (70, 1423), 'Подготовка → список → личное решение', 35, MUTED)
    text(d, (70, 1575), 'Демонстрация интерфейса', 29, MUTED)
    text(d, (70, 1618), 'Тестовые данные · без действий в реальном чате', 26, MUTED)
    for i in range(6):
        x = 70 + i*159
        d.rounded_rectangle((x, 1701, x+137, 1708), 3, fill=GOLD if i <= index else '#2c3041')
    return im

def soundtrack(p):
    rate = 44100
    clicks = [(3.05, 600), (6.05, 780), (9.05, 980), (12.05, 740), (15.05, 900)]
    samples = array('h')
    for i in range(rate*DURATION):
        t = i/rate; value = 0.0
        for ts, hz in clicks:
            dt = t-ts
            if 0 <= dt < 0.16:
                value += 0.13 * math.exp(-dt*27) * math.sin(2*math.pi*hz*dt)
        samples.append(round(max(-1, min(1, value))*32767))
    with wave.open(str(p), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(samples.tobytes())

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--preview-only', action='store_true'); args = parser.parse_args()
    out = HERE / 'out'; out.mkdir(exist_ok=True)
    moments = [1.4, 4.3, 7.3, 10.5, 13.5, 16.8]
    previews = []
    for i, t in enumerate(moments):
        f = frame(t); f.save(out / f'preview_{i+1:02}.jpg', quality=92)
        previews.append(f.resize((270, 480)))
    sheet = Image.new('RGB', (810, 960), BG)
    for i, f in enumerate(previews): sheet.paste(f, ((i%3)*270, (i//3)*480))
    sheet.save(out / 'contact_sheet.jpg', quality=94)
    frame(1.4).save(out / 'cover.jpg', quality=94)
    if args.preview_only: print('Preview frames created'); return
    audio = out / 'original_clicks.wav'; soundtrack(audio)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    dest = out / 'predvestnik_cleanup_pilot.mp4'
    cmd = [ffmpeg, '-y', '-hide_banner', '-loglevel', 'warning', '-f', 'rawvideo', '-vcodec', 'rawvideo',
           '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-i', str(audio),
           '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p',
           '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-shortest', str(dest)]
    with (out / 'render.log').open('w', encoding='utf-8') as log:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=log)
        try:
            for i in range(FPS*DURATION):
                proc.stdin.write(frame(i/FPS).tobytes())
                if i % (FPS*4) == 0: print(f'Rendered {i/FPS:.0f}/{DURATION}s', flush=True)
        finally: proc.stdin.close()
        if proc.wait() != 0: raise RuntimeError('Encoding failed; see out/render.log')
    manifest = {'status': 'rendered_demo', 'file': dest.name, 'width': W, 'height': H, 'fps': FPS,
                'duration_seconds': DURATION, 'audio': 'Original synthesized click tones; no licensed music',
                'footage': 'Unmodified current loadPurgePanel renderer with invented API fixtures',
                'not_live_backend': True, 'not_publication_approved': True,
                'scenes': [{'from': a, 'to': b, 'caption': c, 'ui': n} for a,b,c,n,_ in SCENES]}
    (out / 'pilot_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Created {dest.name} ({dest.stat().st_size:,} bytes)')

if __name__ == '__main__': main()

