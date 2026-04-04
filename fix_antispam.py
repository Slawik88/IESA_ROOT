"""Fix garbled antispam block in message_counter.py"""
import re

filepath = r"g:\IESA_ROOT\PredvestnikBot\middlewares\message_counter.py"

with open(filepath, "rb") as f:
    content = f.read()

# Find and replace the broken antispam block
old_marker = b"check_spam(user.id, chat_id, _antispam_type(event))"
new_marker = b"_is_bot_cmd = _is_bot_command(event)\r\n        if _feat_antispam and not _is_hack_detection and not _is_bot_cmd and check_spam(chat_id, user.id, AF2_ANTISPAM_LIMIT):"

if old_marker in content:
    # Replace just the condition line first
    old_line = b"if _feat_antispam and not _is_hack_detection and check_spam(user.id, chat_id, _antispam_type(event)):"
    new_line = b"_is_bot_cmd = _is_bot_command(event)\r\n        if _feat_antispam and not _is_hack_detection and not _is_bot_cmd and check_spam(chat_id, user.id, AF2_ANTISPAM_LIMIT):"
    content = content.replace(old_line, new_line, 1)
    print("Replaced check_spam line")
else:
    print("check_spam old line not found!")

# Fix garbled label line: "Рмин" / "Рч" → "мин." / "ч."
# The garbled bytes for "мин" double-encoded: мин = D0 BC D0 B8 D0 BD -> C0A0 D198 etc.
# Let's find by pattern
old_label = b'\xd0\xa0\xd1\x98\xd0\xa0\xd1\x91\xd0\xa0\xd0\x85'  # double-encoded "мин"
new_label = b'\xd0\xbc\xd0\xb8\xd0\xbd'  # UTF-8 "мин"
old_ch = b'\xd0\xa1\xe2\x80\xa1'  # double-encoded "ч"
new_ch = b'\xd1\x87'  # UTF-8 "ч"

if old_label in content:
    content = content.replace(old_label, new_label)
    print("Replaced garbled 'мин'")
else:
    print("Garbled 'мин' not found")

if old_ch in content:
    content = content.replace(old_ch, new_ch)
    print("Replaced garbled 'ч'")
else:
    print("Garbled 'ч' not found")

# Fix garbled antispam notification strings
# Find the block with the garbled notification after label
# "заглушен на {label} за спам." - garbled version
old_mute_msg_start = b'\xd1\x80\xd1\x9f\xd1\x99\xc2\xab {user_mention(user.id, user.full_name)}'
new_mute_msg_start = "\U0001f6ab {user_mention(user.id, user.full_name)}".encode("utf-8")

if old_mute_msg_start in content:
    content = content.replace(old_mute_msg_start, new_mute_msg_start)
    print("Replaced garbled 🚫 emoji + user_mention")
else:
    print("Garbled mute msg start not found")

# "заглушен на {label} за спам." - garbled mid part
old_zag = b'\xd0\xa0\xc2\xb7\xd0\xa0\xc2\xb0\xd0\xa0\xd1\x96\xd0\xa0\xc2\xbb\xd0\xa1\xd1\x93\xd0\xa1\xe2\x82\xac\xd0\xa0\xc2\xb5\xd0\xa0\xd0\x85 \xd0\xa0\xd0\x85\xd0\xa0\xc2\xb0 {label} \xd0\xa0\xc2\xb7\xd0\xa0\xc2\xb0 \xd0\xa1\xd0\x83\xd0\xa0\xd1\x97\xd0\xa0\xc2\xb0\xd0\xa0\xd1\x98.'
new_zag = " \u0437\u0430\u0433\u043b\u0443\u0448\u0435\u043d \u043d\u0430 {label} \u0437\u0430 \u0441\u043f\u0430\u043c.".encode("utf-8")

if old_zag in content:
    content = content.replace(old_zag, new_zag)
    print("Replaced garbled 'заглушен на {label} за спам.'")
else:
    print("Garbled 'заглушен на {label} за спам.' not found")
    # Try to find what's actually there
    idx = content.find(b"f\" {user_mention(user.id, user.full_name)}")
    if idx > 0:
        print("Found at:", idx, repr(content[idx-5:idx+200]))

# Fix garbled admin notification
old_admin_notify_start = b'\xd1\x80\xd1\x9f\xd1\x99\xc2\xab <b>'
new_admin_notify_start = "\U0001f6ab <b>".encode("utf-8")

if old_admin_notify_start in content:
    content = content.replace(old_admin_notify_start, new_admin_notify_start)
    print("Replaced garbled 🚫 <b>")
else:
    print("Garbled admin notify start not found")

# "Авто-антиспам" garbled
old_avto = b'\xd0\xa0\xd1\x92\xd0\xa0\xd0\x86\xd0\xa1\xe2\x80\x9a\xd0\xa0\xd1\x95-\xd0\xa0\xc2\xb0\xd0\xa0\xd0\x85\xd0\xa1\xe2\x80\x9a\xd0\xa0\xd1\x91\xd0\xa1\xd0\x83\xd0\xa0\xd1\x97\xd0\xa0\xc2\xb0\xd0\xa0\xd1\x98'
new_avto = "\u0410\u0432\u0442\u043e-\u0430\u043d\u0442\u0438\u0441\u043f\u0430\u043c".encode("utf-8")

if old_avto in content:
    content = content.replace(old_avto, new_avto)
    print("Replaced garbled 'Авто-антиспам'")
else:
    print("Garbled 'Авто-антиспам' not found")

# Fix garbled "Заглушен на {label} за спам." (capital З - in the notify_admins block)
old_zag2 = b'\xd0\xa0\xd0\x97\xd0\xb0\xd0\xb3\xd0\xbb\xd1\x83\xd1\x88\xd0\xb5\xd0\xbd'
# Just let's find any "Р—аглушен"
old_zag2_alt = b'\xd0\xa0\xd0\x97\xd0\xa0\xc2\xb0\xd0\xa0\xd1\x96\xd0\xa0\xc2\xbb\xd0\xa1\xd1\x93\xd0\xa1\xe2\x82\xac\xd0\xa0\xc2\xb5\xd0\xa0\xd0\x85'
new_zag2 = "\u0417\u0430\u0433\u043b\u0443\u0448\u0435\u043d".encode("utf-8")
if old_zag2_alt in content:
    content = content.replace(old_zag2_alt, new_zag2)
    print("Replaced garbled 'Заглушен'")
else:
    print("Garbled 'Заглушен' not found")

# Fix garbled avatar-related 👤 and 💬 emoji in notify_admins
old_person = b'\xd1\x80\xd1\x9f\'\xa4'  # garbled 👤
new_person = "\U0001f464".encode("utf-8")  # 👤
if old_person in content:
    content = content.replace(old_person, new_person)
    print("Replaced garbled 👤")
else:
    print("Garbled 👤 not found")

old_speech = b'\xd1\x80\xd1\x9f\'\xac'  # garbled 💬
new_speech = "\U0001f4ac".encode("utf-8")  # 💬
if old_speech in content:
    content = content.replace(old_speech, new_speech)
    print("Replaced garbled 💬")
else:
    print("Garbled 💬 not found")

with open(filepath, "wb") as f:
    f.write(content)

print("\nDone. Verifying...")

with open(filepath, "rb") as f:
    new_content = f.read()

# Verify check_spam is fixed
if b"check_spam(chat_id, user.id, AF2_ANTISPAM_LIMIT)" in new_content:
    print("OK: check_spam fixed")
else:
    print("FAIL: check_spam not fixed")

if b"check_spam(user.id, chat_id, _antispam_type(event))" in new_content:
    print("FAIL: old check_spam still present!")
else:
    print("OK: old check_spam removed")
