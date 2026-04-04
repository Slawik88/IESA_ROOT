"""Fix remaining garbled notify_admins block in antispam section"""

filepath = r"g:\IESA_ROOT\PredvestnikBot\middlewares\message_counter.py"

with open(filepath, "rb") as f:
    content = f.read()

print("File size:", len(content))

# Find the remaining garbled parts after the fixed 🚫 <b>Авто-антиспам</b>
avtokey = "\u0410\u0432\u0442\u043e-\u0430\u043d\u0442\u0438\u0441\u043f\u0430\u043c</b>".encode("utf-8")
idx4 = content.find(avtokey)
print("Авто-антиспам</b> at:", idx4)
if idx4 >= 0:
    print(repr(content[idx4:idx4+400]))
