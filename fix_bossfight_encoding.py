"""Fix BossFight.tsx encoding - replace all U+FFFD sequences with correct Russian text."""

def fffd(n):
    return b'\xef\xbf\xbd' * n

def u(s):
    return s.encode('utf-8')

with open(r'G:\IESA_ROOT\frontend\src\pages\BossFight.tsx', 'rb') as f:
    raw = f.read()

REPLACEMENTS = [
    # L440: section comment
    (b'      {/* \xe2\x94\x80\xe2\x94\x80 ' + fffd(6) + b' ' + fffd(3) + b' \xef\xbf\xbd ' + fffd(4) + b' ' + fffd(6) + b' \xe2\x94\x80\xe2\x94\x80 */}\r',
     b'      {/* \xe2\x94\x80\xe2\x94\x80 ' + u('Купоны босса') + b' \xe2\x94\x80\xe2\x94\x80 */}\r'),
    # L451: label 'Купоны дня'
    (b'>' + fffd(6) + b' ' + fffd(3) + b'<',
     b'>' + u('Купоны дня') + b'<'),
    # L462: label 'Попытки сегодня' (7+7 fffd)
    (b'>' + fffd(7) + b' ' + fffd(7) + b'<',
     b'>' + u('Попытки сегодня') + b'<'),
    # L464: word 'раз' (3 fffd at end)
    (b' ' + fffd(3) + b'\r',
     b' ' + u('раз') + b'\r'),
    # L470: modal comment (8+7 fffd)
    (b'      {/* \xe2\x94\x80\xe2\x94\x80 ' + fffd(8) + b' ' + fffd(7) + b' \xe2\x94\x80\xe2\x94\x80 */}\r',
     b'      {/* \xe2\x94\x80\xe2\x94\x80 ' + u('Модальное купонов') + b' \xe2\x94\x80\xe2\x94\x80 */}\r'),
    # L481: header comment (9 fffd)
    (b'            {/* ' + fffd(9) + b' */}\r',
     b'            {/* ' + u('Заголовок') + b' */}\r'),
    # L494: icons comment (6+7 fffd)
    (b'            {/* ' + fffd(6) + b' ' + fffd(7) + b' */}\r',
     b'            {/* ' + u('Иконки купонов') + b' */}\r'),
    # L508: description comment (8 fffd)
    (b'            {/* ' + fffd(8) + b' */}\r',
     b'            {/* ' + u('Описание') + b' */}\r'),
    # L516: buy button comment (6+7 fffd) - same pattern as L494, handled above
    # Already covered if same pattern
]

applied = 0
for old, new in REPLACEMENTS:
    if old in raw:
        raw = raw.replace(old, new)
        applied += 1
        print(f'OK: {repr(new[:60])}')
    else:
        print(f'MISS: expected {repr(old[:40])}')

# Now handle remaining lines - line-by-line replacements for complex ones
lines = raw.split(b'\n')
for i, line in enumerate(lines):
    if b'\xef\xbf\xbd' not in line:
        continue
    orig = line
    
    # L485 in modal: title 'Купоны дня' (same pattern as L451, already fixed above)
    
    # L511: description line 1
    if b'                ' + fffd(6) + b' ' + fffd(9) + b' ' + fffd(5) in line:
        lines[i] = b'                ' + u('Купоны позволяют сыграть дополнительные бои сверх дневного лимита.') + b'\r'
    
    # L512: description line 2
    elif b'                ' + fffd(8) + b' 5 ' in line:
        lines[i] = b'                ' + u('Максимум 5 купонов. Один купон восполняется каждые 3 часа.') + b'\r'
    
    # L527: toast success
    elif b'\xf0\x9f\x8e\xab ' + fffd(5) + b' ' + fffd(6) + b'!' in line:
        lines[i] = line.replace(
            b'\xf0\x9f\x8e\xab ' + fffd(5) + b' ' + fffd(6) + b'!',
            b'\xf0\x9f\x8e\xab ' + u('Купон куплен') + b'!'
        )
    
    # L529: error fallback
    elif b'r.error ?? "' + fffd(6) + b'"' in line:
        lines[i] = line.replace(
            b'r.error ?? "' + fffd(6) + b'"',
            b'r.error ?? "' + u('\u041e\u0448\u0438\u0431\u043a\u0430') + b'"'
        )
    
    # L537: max purchased label
    elif b'"' + fffd(6) + b' ' + fffd(9) + b'"' in line:
        lines[i] = line.replace(
            b'"' + fffd(6) + b' ' + fffd(9) + b'"',
            b'"' + u('Максимум куплено') + b'"'
        )
    
    # L538: buy button text
    elif b': <>' + fffd(6) + b' ' + fffd(5) in line:
        lines[i] = b'                : <>' + u('Купить за 7 \U0001f48e') + b'</>}\r'
    
    if lines[i] != orig:
        applied += 1
        print(f'Line {i+1} fixed')

raw = b'\n'.join(lines)

# Final check
remaining = [(i+1, lines[i]) for i in range(len(lines)) if b'\xef\xbf\xbd' in lines[i]]
print(f'\nApplied {applied} replacements. Remaining garbled lines: {len(remaining)}')
for lineno, line in remaining:
    print(f'  L{lineno}: {repr(line[:100])}')

with open(r'G:\IESA_ROOT\frontend\src\pages\BossFight.tsx', 'wb') as f:
    f.write(raw)
print('Saved.')
