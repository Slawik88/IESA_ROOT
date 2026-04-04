"""Fix remaining garbled notify_admins block in antispam section"""

filepath = r"g:\IESA_ROOT\PredvestnikBot\middlewares\message_counter.py"

with open(filepath, "rb") as f:
    content = f.read()

print("File size:", len(content))

# Find the remaining garbled parts
# 1. Garbled 👤 in notify_admins
idx1 = content.find(b"\xd1\x80\xd1\x9f'\xa4")
print("garbled 👤 at:", idx1)
if idx1 >= 0:
    print(repr(content[idx1:idx1+60]))

# 2. Search for garbled Заглушен (capital)
idx2 = content.find(b"\xd0\xa0\xd0\x97\xd0\xa0\xc2\xb0")
print("garbled Заг at:", idx2)

# 3. Search with a different approach - look for the full notify_admins block
idx3 = content.find(b"f\"\xd1\x80\xd1\x9f")
print("garbled f string at:", idx3)
if idx3 >= 0:
    print(repr(content[idx3:idx3+200]))

# Show what's around the known 🚫 in the notify_admins block
idx4 = content.find(b"Авто-антиспам</b>")
if idx4 >= 0:
    print("\n--- Context after Авто-антиспам ---")
    print(repr(content[idx4:idx4+300]))
