"""Fix remaining garbled bytes in notify_admins antispam block + extra space"""

filepath = r"g:\IESA_ROOT\PredvestnikBot\middlewares\message_counter.py"

with open(filepath, "rb") as f:
    content = f.read()

replacements = [
    # garbled 👤
    (b'\xd1\x80\xd1\x9f\xe2\x80\x98\xc2\xa4', '\U0001f464'.encode('utf-8')),
    # garbled 💬  
    (b'\xd1\x80\xd1\x9f\xe2\x80\x99\xc2\xac', '\U0001f4ac'.encode('utf-8')),
    # garbled "Заглушен на {label} за спам."
    (
        b'\xd0\xa0\xe2\x80\x94\xd0\xa0\xc2\xb0\xd0\xa0\xd1\x96\xd0\xa0\xc2\xbb\xd0\xa1\xd1\x93\xd0\xa1\xe2\x82\xac\xd0\xa0\xc2\xb5\xd0\xa0\xd0\x85 \xd0\xa0\xd0\x85\xd0\xa0\xc2\xb0 {label} \xd0\xa0\xc2\xb7\xd0\xa0\xc2\xb0 \xd0\xa1\xd0\x83\xd0\xa0\xd1\x97\xd0\xa0\xc2\xb0\xd0\xa0\xd1\x98.',
        '\u0417\u0430\u0433\u043b\u0443\u0448\u0435\u043d \u043d\u0430 {label} \u0437\u0430 \u0441\u043f\u0430\u043c.'.encode('utf-8')
    ),
    # extra double space in mute message
    (
        b'\xf0\x9f\x9a\xab {user_mention(user.id, user.full_name)}"\r\n                        f"  \xd0\xb7\xd0\xb0\xd0\xb3\xd0\xbb\xd1\x83\xd1\x88\xd0\xb5\xd0\xbd',
        b'\xf0\x9f\x9a\xab {user_mention(user.id, user.full_name)}"\r\n                        f" \xd0\xb7\xd0\xb0\xd0\xb3\xd0\xbb\xd1\x83\xd1\x88\xd0\xb5\xd0\xbd'
    ),
]

for old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        print(f"Replaced: {repr(old[:20])} ...")
    else:
        print(f"NOT FOUND: {repr(old[:20])} ...")

with open(filepath, "wb") as f:
    f.write(content)

print("\nVerification:")
# Check notify_admins block is clean
avtokey = "\u0410\u0432\u0442\u043e-\u0430\u043d\u0442\u0438\u0441\u043f\u0430\u043c</b>".encode("utf-8")
idx = content.find(avtokey)
if idx >= 0:
    segment = content[idx:idx+300]
    try:
        decoded = segment.decode('utf-8')
        print("OK: notify_admins block decoded cleanly")
        print(decoded[:200])
    except UnicodeDecodeError as e:
        print("STILL GARBLED:", e)
        print(repr(segment))
