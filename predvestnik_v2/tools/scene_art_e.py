"""Holiday additions. Each illustration is drawn separately; no recoloured old scenes."""
from scene_kit import art, svg


def E(name, body, w=160, h=200):
    # CSS quoted data URLs cannot contain literal newlines.
    art(name, "e", svg(w, h, " ".join(body.split())))


# Ghost coach: transparent glass cabin, scrolling iron chassis, lanterns and spoked wheels.
E("ghostCoach", """<path fill='#102c31' stroke='#94e5d5' stroke-width='2' d='M31 45Q80 11 127 45L117 64 123 124Q80 147 36 124L42 64Z'/>
<path fill='#458282' fill-opacity='.45' stroke='#b4fae9' d='M48 65H73v50H43ZM84 65H109l5 50H84Z'/>
<g fill='none' stroke='#65bcb5' stroke-width='2'><path d='M25 133Q8 116 17 113Q35 123 34 137H129Q148 117 139 111Q130 115 130 131M80 40V124M32 47Q80 33 127 47M52 20l10 10 18-18 19 18 10-10'/></g>
<g stroke='#9ee9df' fill='#08191f' stroke-width='2'><circle cx='36' cy='153' r='24'/><circle cx='123' cy='153' r='24'/><path d='M12 153h48m-24-24v48m-17-41 34 34m0-34-34 34M99 153h48m-24-24v48m-17-41 34 34m0-34-34 34'/></g>
<g fill='#ddfff0'><path d='M15 57h12v24H15ZM133 57h12v24h-12Z'/><circle cx='80' cy='18' r='3'/></g><g stroke='#759696' fill='none'><path d='M14 56h14l-7-11Zm118 0h14l-7-11Z'/></g>""")

# Polar locomotive: riveted brass boiler, red buffers, headlamp, snowy arches.
E("northEngine", """<path fill='#1c3653' stroke='#a4b9c5' stroke-width='2' d='M20 103h80V61h38v75H18Z'/><path fill='#304a66' stroke='#d4b77c' stroke-width='3' d='M15 87h89v39H15Z'/>
<path fill='#ffe8ae' d='M109 70h20v25h-20Z'/><path fill='#141f34' stroke='#c7ab75' stroke-width='2' d='M31 86V54H47v32Zm-6-32h28V44H25Zm71 4h45V49H96Z'/>
<path fill='#6d2940' stroke='#caa56d' stroke-width='2' d='M12 126h131v15H12Zm-4 18 20-4v15H8Z'/><g fill='#0b1727' stroke='#d8b87f' stroke-width='3'><circle cx='39' cy='148' r='16'/><circle cx='80' cy='148' r='16'/><circle cx='121' cy='149' r='13'/><path d='M25 149h69m-54-15v29m39-29v29'/></g>
<circle fill='#ffeab2' stroke='#dba86b' stroke-width='3' cx='15' cy='102' r='10'/><g fill='#8eaabd' fill-opacity='.65'><ellipse cx='35' cy='30' rx='18' ry='9'/><ellipse cx='57' cy='17' rx='24' ry='11'/><ellipse cx='91' cy='8' rx='29' ry='8'/></g>""")
# Rose and quill.
E("roseQuill", """<path fill='none' stroke='#5f9d84' stroke-width='3' d='M35 190Q87 126 56 56'/><path fill='#38705e' d='M50 132Q15 99 51 110L57 122Q92 87 72 132Z'/><g fill='#c94c73' stroke='#ffacbb' stroke-width='1'><path d='M56 70Q15 47 38 29q0-29 22-16 30-8 30 17 22 30-34 40Z'/><path d='M56 61Q28 47 43 33q26-21 32 4-2 20-19 24ZM54 46q-9-13 4-15 15 3-4 15Z'/></g><path fill='#f8d3b2' stroke='#d6a582' d='M73 158Q82 68 142 31q15 55-69 127Z'/><path fill='none' stroke='#b58a73' stroke-width='2' d='m65 180 67-130m-49 89 25-7m-14-16 23-5m-10-14 22-5'/>""")
# Cut crystal heart: deliberately separate planes and prismatic cracks, no raster blur.
E("crystalHeart", """<path fill='#5f3b76' stroke='#e8dbff' stroke-width='2' d='M80 180 13 103 8 59 36 25 62 24 80 44 99 24 126 25 153 59 148 103Z'/>
<path fill='#e8b4ec' d='m80 44-18-20-26 1 13 40Z'/><path fill='#a780d3' d='m8 59 28-34 13 40-36 38Z'/><path fill='#c8dff5' d='m99 24 27 1 27 34-39 7Z'/><path fill='#dc91c3' d='m49 65 31-21 34 22-34 91Z'/><path fill='#7167a9' d='m13 103 36-38 31 92Z'/><path fill='#929fd1' d='m114 66 39-7-5 44-68 54Z'/><path fill='#e5bce4' d='m13 103 67 54v23Z'/><path fill='#b8c7ef' d='m80 180v-23l68-54Z'/>
<g fill='none' stroke='#f5e5ff' stroke-opacity='.7'><path d='m8 59 41 6 31-21 34 22 39-7M49 65l31 92 34-91M13 103l67 54 68-54'/></g><path fill='#fff' d='m41 49 2 10 10 2-10 2-2 10-2-10-10-2 10-2Z'/>""")
