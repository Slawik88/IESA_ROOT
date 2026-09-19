#!/usr/bin/env python3
"""Lock the mobile quest-log hierarchy to the server-authoritative v1 contract."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "FastAPI" / "static" / "app.12.js").read_text(encoding="utf-8")
CSS = (ROOT / "FastAPI" / "static" / "app.css").read_text(encoding="utf-8")


assert "let _questsV1Data=null,_questsV1Tab='daily',_questsV1Busy=false" in JS
assert "['daily','weekly','rewards'].includes(tab)" in JS
assert 'aria-controls="quest-panel"' in JS
assert 'role="tablist"' in JS and 'role="tabpanel"' in JS
assert 'aria-selected="${_questsV1Tab===' in JS
assert "querySelector('.quest-tabs .is-active')?.focus()" in JS
assert 'role="progressbar"' in JS
assert 'aria-label="${esc(quest.title)}:' in JS
assert "questMetricMeta(quest.metric)" in JS
assert "label:'Открыть Ритм'" in JS and "action:'openRhythmV2Game()'" in JS
assert "label:'Открыть Сапёр'" in JS and "action:'openMinesweeperGame()'" in JS
assert "label:'К сундукам'" in JS and "action:'openChestsV1()'" in JS
assert "label:'К питомцам'" in JS and "action:'openPetsV1()'" in JS
assert "questsV1AskReroll" in JS and "Сервер подберёт другой тип задания" in JS
assert "remaining<=0" in JS and "quest.completed" in JS
assert "if(_questsV1Busy)return" in JS
assert "_questsV1Busy=true;renderQuestsV1()" in JS
assert "finally(()=>{_questsV1Busy=false;renderQuestsV1();})" in JS
assert "rewardKinds.reduce" in JS and "195 🪙" not in JS
assert "${target.done}/${target.total} заданий" in JS
assert '<h1>🧭 Квесты</h1>' in JS and '<h2>${active.done}/${active.total}' in JS
assert "quest-overview" not in JS
assert "Квесты не загрузились" in JS and "Повторить" in JS
assert "questsV1TabKey(event)" in JS and "event.key==='ArrowRight'" in JS
assert "api('/quests-v1/reroll'" in JS
assert "api('/quests-v1/claim-reward'" in JS

assert ".quest-tabs" in CSS and "position: sticky" in CSS
assert ".quest-card-actions" in CSS
assert "min-height: 44px" in CSS
assert ".quest-progress" in CSS
assert "#pg-questlog { padding-bottom: calc(86px + var(--safe-b)); }" in CSS
assert ".quest-card-meta" in CSS and "font-size: 11px" in CSS
assert ".quest-head .looks-back { width: 44px; height: 44px; }" in CSS

print("OK: quest log mobile hierarchy and authoritative action contract")
