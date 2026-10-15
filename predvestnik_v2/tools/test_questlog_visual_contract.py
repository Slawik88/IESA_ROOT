#!/usr/bin/env python3
"""Lock the quest screen to the server-authoritative v1 contract and the shared design rules (docs/MINIAPP_DESIGN_RULES.md)."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "FastAPI" / "static" / "app.12.js").read_text(encoding="utf-8")
CSS = (ROOT / "FastAPI" / "static" / "quests-v3.css").read_text(encoding="utf-8")


assert "let _questsV1Data=null,_questsV1Tab='daily',_questsV1Busy=false" in JS
assert "['daily','weekly','rewards'].includes(tab)" in JS
assert 'aria-controls="quest-panel"' in JS and 'role="tablist"' in JS and 'role="tabpanel"' in JS
assert 'aria-selected="${_questsV1Tab===' in JS and "questsV1TabKey(event)" in JS and "event.key==='ArrowRight'" in JS
assert "v3Head('Задания'" in JS and 'class="v3-tabs v3-tabs--wide quest-tabs"' in JS
# One progress per quest: a bar and «2/4», no percent; the route and the reroll live in the quest's sheet.
assert "questMetricMeta(quest.metric)" in JS and "questsV1Open(" in JS and "%</span>" not in JS.split("function questRow")[1].split("function questPeriodSummary")[0]
assert "label:'Открыть Ритм'" in JS and "action:'openRhythmV2Game()'" in JS
assert "label:'Открыть Сапёр'" in JS and "action:'openMinesweeperGame()'" in JS
assert "label:'К сундукам'" in JS and "action:'openChestsV1()'" in JS
assert "label:'К питомцам'" in JS and "action:'openPetsV1()'" in JS
assert "questsV1AskReroll" in JS and "Сервер подберёт другой тип задания" in JS and "remaining<=0" in JS
# A ready reward is the screen's primary action, above the tabs; on the rewards tab it stays in its row.
assert "ready&&_questsV1Tab!=='rewards'" in JS and "questsV1Claim('${kind}')" in JS
assert "if(_questsV1Busy)return" in JS and "_questsV1Busy=true;renderQuestsV1()" in JS
assert "finally(()=>{_questsV1Busy=false;renderQuestsV1();})" in JS
assert "amount_essence" in JS and "amount_keys" in JS, "quests show Essence and keys next to Mora"
assert "Задания не загрузились" in JS and "Повторить" in JS and "Задания не обновились" in JS
assert "api('/quests-v1/reroll'" in JS and "api('/quests-v1/claim-reward'" in JS
assert 'data-q="${period}-${quest.slot}"' in JS and "quest-card" in JS, "v3QuestsDone (app.31.js) marks freshly completed quests"

assert "min-height: 60px" in CSS and "background: var(--v3-ink)" in CSS
assert "--v3-acc" not in CSS, "the screen's accent is the shared tab and the claim pill, not its own colors"
print("OK: quest screen rows, one progress each, ready reward on top, authoritative actions")
