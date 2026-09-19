#!/usr/bin/env python3
"""Client retries must reuse mutation ids after an uncertain network result."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = (ROOT / "FastAPI/static/app.12.js").read_text(encoding="utf-8")

assert "const _petsV1PendingActions=new Map()" in CLIENT
assert "const _questsV1PendingActions=new Map()" in CLIENT
assert "_pendingAction(_petsV1PendingActions,key,'pet-feed-')" in CLIENT
assert "_pendingAction(_petsV1PendingActions,key,'pet-activate-')" in CLIENT
assert "_pendingAction(_petsV1PendingActions,key,'pet-activity-')" in CLIENT
assert "_pendingAction(_petsV1PendingActions,key,'pet-decision-')" in CLIENT
assert CLIENT.count("_petsV1PendingActions.delete(key)") == 4
assert "Проверяем запущенный таймер" in CLIENT
assert "_pendingAction(_questsV1PendingActions,key,'quest-reroll-')" in CLIENT
assert "_questsV1PendingActions.delete(key)" in CLIENT
assert "_pendingAction(_chestsV1PendingActions,key,'chest-open-')" in CLIENT
assert "_pendingAction(_chestsV1PendingActions,key,'chest-buy-')" in CLIENT
assert CLIENT.count("_chestsV1PendingActions.delete(key)") == 2
assert "const action='chest-open-'" not in CLIENT
assert "const action='chest-buy-'" not in CLIENT
assert "Повтори: запрос будет отправлен с тем же номером операции" in CLIENT
assert "Повтори: лимит не спишется второй раз" in CLIENT
assert '<h1 class="looks-htitle">Публичный профиль</h1>' in CLIENT
assert '<h1>Трекер чатов</h1>' in CLIENT
assert "window.chatTrackerSearch=" in CLIENT
assert "window.chatTrackerSort=" in CLIENT
assert "window.chatTrackerLoadMore=" in CLIENT
assert "requestGeneration" in CLIENT
assert "generation!==chatTracker.requestGeneration" in CLIENT
assert "setSelectionRange" in CLIENT
assert 'role="status" aria-live="polite"' in CLIENT
assert 'class="chat-tracker-list"' in CLIENT
assert "Не удалось загрузить чаты" in CLIENT
assert "pendingFocus:''" in CLIENT
assert "Следующую страницу загрузить не удалось" in CLIENT
assert "root.querySelector('.chat-tracker-status')" in CLIENT

print("OK: feed, quest-reroll and chest retries retain action ids until success")
