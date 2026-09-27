#!/usr/bin/env python3
"""Static release contract for the hidden player-exchange Mini App surface."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
index = (ROOT / "FastAPI/static/index.html").read_text(encoding="utf-8")
js = (ROOT / "FastAPI/static/app.14.js").read_text(encoding="utf-8")
css = (ROOT / "FastAPI/static/app.css").read_text(encoding="utf-8")
main = (ROOT / "FastAPI/main.py").read_text(encoding="utf-8")

assert 'id="pg-exchange-v1"' in index
assert 'id="cc-exchange-v1" hidden' in index
assert "economy_player_exchange_v1" in js
assert "Игровой актив без вывода в деньги" in js
assert "Цена может резко вырасти или упасть" in js
assert 'aria-pressed="${_pxSide===\'buy\'}"' in js
assert "min-height:44px" in css
assert "app.{i:02d}.js\" for i in (1, 2, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14)" in main
assert "/player-exchange/v1/me?limit=100" in js
assert "/cancel" in js
assert "_pxRecoveryCoins" in js
assert "Аукционные заявки" in js
assert "_pxConfirmOrder" in js
assert "Подтвердите" in js
assert "_pxConfirmBid" in js
assert "maker 0,10%, taker 0,25%" in js
assert "Отменить заявку нельзя" in js
assert "_pxOpenEmission" in js and "/emissions" in js
assert "_pxConfirmEmission" in js and "_pxPendingEmission" in js
assert "circulation_snapshot_units" in js and "projected_total_supply_units" in js
assert "emission_executes_at" in js and "data-px-emission-cancel" in js
assert "emission_can_cancel===true" in js and "e.can_cancel===true" in js
assert "e.executed_at" in js and "e.cancelled_at" in js
assert "Максимум сейчас" in js and "попадут в казну" in js
assert "Отмена закрыта" in js and "_pxEmissionCancelActions" in js
print("PLAYER_EXCHANGE_V1_UI_CONTRACT_OK")
