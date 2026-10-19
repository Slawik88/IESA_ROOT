"""Holiday additions. Each illustration is drawn separately; no recoloured old scenes."""
from scene_kit import art, svg


def E(name, body, w=160, h=200):
    # CSS quoted data URLs cannot contain literal newlines.
    art(name, "e", svg(w, h, " ".join(body.split())))


# Engraved theatre mask, asymmetric raven feathers, gold rivets and velvet ribbons.
E("ravenMask", """<path fill='#281437' d='M8 195Q32 90 16 4L78 18 145 1Q121 88 153 195L115 168 130 196 79 182 28 198 42 163Z'/>
<g fill='#4e315c' stroke='#af875c' stroke-width='1'><path d='M49 90Q-5 44 30 10Q30 47 59 70L46 18Q81 33 76 73L98 8Q129 40 101 77L143 31Q157 65 118 101Z'/></g>
<path fill='#c4a476' stroke='#ffe3a1' stroke-width='2' d='M22 87Q49 66 80 91Q112 64 139 86L128 127 99 138 80 122 58 139 32 124Z'/>
<path fill='#160d21' d='M35 99Q52 84 68 103Q54 118 38 110ZM91 103Q108 83 125 99L123 111Q105 120 91 103Z'/>
<g fill='none' stroke='#765037' stroke-width='1.5'><path d='M28 92Q47 73 70 95M90 95Q114 72 134 91M40 121Q57 127 69 115M92 115Q110 128 121 120M80 94V119'/></g>
<g fill='#ffe7ab'><circle cx='28' cy='102' r='2'/><circle cx='132' cy='102' r='2'/><path d='m80 80 4 7-4 7-4-7Z'/></g>""")
E("ravenKey", """<path fill='#171222' stroke='#68536c' stroke-width='1.5' d='M30 143Q13 113 32 93L21 73 49 70Q53 40 81 46L106 58 92 64Q89 85 74 92L91 127 67 115 80 143 53 126 48 156Z'/>
<path fill='#b39467' d='M91 63 122 64 122 68 104 68 104 73 99 73 99 68 91 68Z'/><circle fill='#e9c483' cx='78' cy='56' r='2'/>
<path fill='none' stroke='#a28a62' stroke-width='3' d='M118 89V142h13v-7h-6v-8h8'/><circle fill='none' stroke='#e9c483' stroke-width='3' cx='118' cy='81' r='9'/>""")
# Ghost coach: transparent glass cabin, scrolling iron chassis, lanterns and spoked wheels.
E("ghostCoach", """<path fill='#102c31' stroke='#94e5d5' stroke-width='2' d='M31 45Q80 11 127 45L117 64 123 124Q80 147 36 124L42 64Z'/>
<path fill='#458282' fill-opacity='.45' stroke='#b4fae9' d='M48 65H73v50H43ZM84 65H109l5 50H84Z'/>
<g fill='none' stroke='#65bcb5' stroke-width='2'><path d='M25 133Q8 116 17 113Q35 123 34 137H129Q148 117 139 111Q130 115 130 131M80 40V124M32 47Q80 33 127 47M52 20l10 10 18-18 19 18 10-10'/></g>
<g stroke='#9ee9df' fill='#08191f' stroke-width='2'><circle cx='36' cy='153' r='24'/><circle cx='123' cy='153' r='24'/><path d='M12 153h48m-24-24v48m-17-41 34 34m0-34-34 34M99 153h48m-24-24v48m-17-41 34 34m0-34-34 34'/></g>
<g fill='#ddfff0'><path d='M15 57h12v24H15ZM133 57h12v24h-12Z'/><circle cx='80' cy='18' r='3'/></g><g stroke='#759696' fill='none'><path d='M14 56h14l-7-11Zm118 0h14l-7-11Z'/></g>""")
E("ghostGate", """<g fill='none' stroke='#507c84' stroke-width='2'><path d='M18 192V39Q80-12 142 39v153M27 192V44Q80 1 133 44v148M40 188V47m20 139V34m20 152V30m20 156V34m20 154V47M18 107h124M18 174h124'/><path d='M18 43 10 28l8-15 8 15-8 15m124 0-8-15 8-15 8 15-8 15M42 85Q66 63 80 85 94 63 118 85M42 150Q66 128 80 150 94 128 118 150'/></g>""")
# Iced bakery: tiled biscuit roof, candy columns, glowing shop windows and sugar trim.
E("sugarBakery", """<path fill='#855034' stroke='#e7b77a' stroke-width='2' d='M27 89H134v95H27Z'/><path fill='#9e5738' d='m12 94 67-77 70 77Z'/>
<path fill='none' stroke='#fff0cf' stroke-width='7' stroke-linecap='round' stroke-linejoin='round' d='m16 91 63-71 66 71M29 106q9 12 18 0 9 12 18 0 9 12 18 0 9 12 18 0 9 12 18 0'/>
<g fill='#ffdc83' stroke='#663a27' stroke-width='4'><path d='M41 124h27v28H41ZM94 124h26v28H94ZM71 181v-45q10-17 20 0v45Z'/></g>
<g stroke='#fff0cf' stroke-width='3'><path d='M54 125v26m-12-13h24m41-13v26m-12-13h24M28 178h105'/></g>
<g fill='#d35154'><circle cx='48' cy='70' r='4'/><circle cx='80' cy='43' r='4'/><circle cx='111' cy='77' r='4'/></g><g fill='#e8c789'><path d='m81 62 3 8 9 1-7 6 2 9-7-5-8 5 2-9-6-6 9-1Z'/></g><path fill='#fff2da' d='M106 32h17v37l-17-18Z'/>""")
E("sugarTools", """<g transform='rotate(-20 80 100)'><path fill='#c58b53' stroke='#f1c892' stroke-width='2' d='M24 81h113v37H24Z'/><path fill='#8c5737' d='M9 91h15v17H9Zm128 0h15v17h-15Z'/><path fill='none' stroke='#e6b87f' d='M35 84v31m13-31v31m70-31v31'/></g><path fill='#d2a16c' stroke='#fff0ca' stroke-width='3' d='m66 139 9 15 17-4-6 18 11 14-19 1-10 14-7-17-17-5 15-12Z'/>""")
# Polar locomotive: riveted brass boiler, red buffers, headlamp, snowy arches.
E("northEngine", """<path fill='#1c3653' stroke='#a4b9c5' stroke-width='2' d='M20 103h80V61h38v75H18Z'/><path fill='#304a66' stroke='#d4b77c' stroke-width='3' d='M15 87h89v39H15Z'/>
<path fill='#ffe8ae' d='M109 70h20v25h-20Z'/><path fill='#141f34' stroke='#c7ab75' stroke-width='2' d='M31 86V54H47v32Zm-6-32h28V44H25Zm71 4h45V49H96Z'/>
<path fill='#6d2940' stroke='#caa56d' stroke-width='2' d='M12 126h131v15H12Zm-4 18 20-4v15H8Z'/><g fill='#0b1727' stroke='#d8b87f' stroke-width='3'><circle cx='39' cy='148' r='16'/><circle cx='80' cy='148' r='16'/><circle cx='121' cy='149' r='13'/><path d='M25 149h69m-54-15v29m39-29v29'/></g>
<circle fill='#ffeab2' stroke='#dba86b' stroke-width='3' cx='15' cy='102' r='10'/><g fill='#8eaabd' fill-opacity='.65'><ellipse cx='35' cy='30' rx='18' ry='9'/><ellipse cx='57' cy='17' rx='24' ry='11'/><ellipse cx='91' cy='8' rx='29' ry='8'/></g>""")
E("northBridge", """<path fill='#172d48' stroke='#617e9e' stroke-width='2' d='M0 82H360v86h-30v-44q-22-40-44 0v44h-31v-44q-22-40-44 0v44h-31v-44q-22-40-44 0v44h-31v-44q-22-40-44 0v44H0Z'/><path stroke='#cce6f1' stroke-width='5' d='M0 80h360'/><path stroke='#a9bac8' d='M0 69h360m-335-10v21m25-21v21m25-21v21m25-21v21m25-21v21m25-21v21m25-21v21m25-21v21m25-21v21m25-21v21m25-21v21m25-21v21m25-21v21'/>""", 360, 180)
# Handwritten letter, folded paper, wax seal, a separate thorned rose and quill.
E("roseEnvelope", """<path fill='#c6a48d' stroke='#f4d9b9' stroke-width='2' d='m14 83 66-42 66 42v93H14Z'/><path fill='#edd1b3' d='M29 19h102v114H29Z'/><g stroke='#9b6a68' fill='none' stroke-width='1.7'><path d='M44 46q16-13 22 0t20-2 29 0M44 61q10-10 17 0t24-2 30 0M44 78q17-10 29 0t35-1M44 96h50'/></g>
<path fill='#b38178' stroke='#f2cfb2' stroke-width='1.5' d='m14 83 66 48 66-48v93H14Z'/><path fill='#d1a08c' stroke='#f2cfb2' d='m14 176 66-53 66 53Z'/><circle fill='#922d4e' stroke='#d7788b' stroke-width='2' cx='80' cy='130' r='15'/><path fill='none' stroke='#eaa0ad' stroke-width='1.5' d='M80 138q-15-9-8-15 6-5 8 2 4-7 9-2 6 6-9 15Z'/>""")
E("roseQuill", """<path fill='none' stroke='#5f9d84' stroke-width='3' d='M35 190Q87 126 56 56'/><path fill='#38705e' d='M50 132Q15 99 51 110L57 122Q92 87 72 132Z'/><g fill='#c94c73' stroke='#ffacbb' stroke-width='1'><path d='M56 70Q15 47 38 29q0-29 22-16 30-8 30 17 22 30-34 40Z'/><path d='M56 61Q28 47 43 33q26-21 32 4-2 20-19 24ZM54 46q-9-13 4-15 15 3-4 15Z'/></g><path fill='#f8d3b2' stroke='#d6a582' d='M73 158Q82 68 142 31q15 55-69 127Z'/><path fill='none' stroke='#b58a73' stroke-width='2' d='m65 180 67-130m-49 89 25-7m-14-16 23-5m-10-14 22-5'/>""")
# Cut crystal heart: deliberately separate planes and prismatic cracks, no raster blur.
E("crystalHeart", """<path fill='#5f3b76' stroke='#e8dbff' stroke-width='2' d='M80 180 13 103 8 59 36 25 62 24 80 44 99 24 126 25 153 59 148 103Z'/>
<path fill='#e8b4ec' d='m80 44-18-20-26 1 13 40Z'/><path fill='#a780d3' d='m8 59 28-34 13 40-36 38Z'/><path fill='#c8dff5' d='m99 24 27 1 27 34-39 7Z'/><path fill='#dc91c3' d='m49 65 31-21 34 22-34 91Z'/><path fill='#7167a9' d='m13 103 36-38 31 92Z'/><path fill='#929fd1' d='m114 66 39-7-5 44-68 54Z'/><path fill='#e5bce4' d='m13 103 67 54v23Z'/><path fill='#b8c7ef' d='m80 180v-23l68-54Z'/>
<g fill='none' stroke='#f5e5ff' stroke-opacity='.7'><path d='m8 59 41 6 31-21 34 22 39-7M49 65l31 92 34-91M13 103l67 54 68-54'/></g><path fill='#fff' d='m41 49 2 10 10 2-10 2-2 10-2-10-10-2 10-2Z'/>""")
E("crystalArc", """<g fill='none' stroke='#a3bbdf' stroke-width='1.4'><ellipse cx='80' cy='100' rx='68' ry='30' transform='rotate(-43 80 100)'/><ellipse cx='80' cy='100' rx='68' ry='30' transform='rotate(43 80 100)'/><path d='m29 35 19 17 20-12 23 18m7 86 23-17 17 21'/></g><g fill='#f8d5f2'><circle cx='29' cy='35' r='3'/><circle cx='48' cy='52' r='2'/><circle cx='68' cy='40' r='3'/><circle cx='91' cy='58' r='2'/><circle cx='98' cy='144' r='3'/><circle cx='121' cy='127' r='2'/><circle cx='138' cy='148' r='3'/></g>""")
