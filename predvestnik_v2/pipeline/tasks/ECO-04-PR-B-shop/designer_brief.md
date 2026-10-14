# Designer brief: Shop, gifts, key tiers, pet level-up (ECO-04)

Style it with your Mini App rules (tokens, themes, tap targets, states). This file says what must be on screen and what data arrives.
Owner decided: paid key prices (Silver 120✨, Platinum 300✨), polish 60 Essence, diamond key is 6★. Everything else is draft (`shop_catalog.json`). Take numbers from data, never hardcode.
Tone: short Russian UI copy, no pressure ("great deal", "hurry", "today only" are banned).

## 1. Shop screen
Entry: your choice (bottom nav or profile). Top: balances of all live currencies: 🪙 Mora, 💎 Diamonds, ✨ Zarniki, 🔮 Essence, 🗝 Keys (count per tier).
Tabs: **Keys · Essence · Exchange · Gifts**. Bottom tiles link to existing screens: Season Pass, VIP, Skins.

One product card for all tabs:
- icon, name, tier;
- what you get, one line ("key: chest from 4★");
- price in one or several currencies (e.g. 300 🪙 + 200 🔮; 5 💎 + 3000 🪙). Missing currency highlighted, button disabled, hint "Missing: 120 🪙";
- action word on the button: Buy / Craft / Exchange;
- limit: "2 of 3 left this week" / "resets in 4 h";
- states: available, not enough currency, limit reached, loading, network error, success (short confirmation, balances update in place).

Confirm sheet before any charge: what you pay, what you get, balance before/after. For ✨ and 💎 an extra line "This cannot be undone".

Tabs:
1. **Keys** (5 items): Bronze 3★ (800 🪙, 3/week), Silver 4★ (craft 300 🪙 + 200 🔮, 1/week; or 120 ✨, 2/day), Platinum 6★ (5 💎 + 3000 🪙, 1/week; or 300 ✨, 1/day). Tier colors yours (also base 1★; 5★ and 7★ exist only as rewards).
   Silver has two ways: one tile with a method switch. Limits are counted in keys.
   Honest odds line from data: "4★ key: about 89% exactly 4★, the rest higher", "6★ key: about 97% exactly 6★".
2. **Essence** (1 item): Polish, 600 🪙 + 1 💎 → 60 🔮, 2/week.
3. **Exchange**: ✨ → 🪙 (10 per 1✨) and ✨ → 💎 (1💎 per 100✨). Amount field, hint "Limit 50✨ per day, N left", warning "Irreversible". Backend exists, UI needed.
4. **Gifts**: four tier sections (see 2). Food is NOT sold in the shop.

## 2. Gifts
Tiers: 1 "Sign" (Mora), 2 "Warm" (Mora), 3 "Rare" (Diamonds), 4 "Legendary" (Zarniki), three gifts each (`shop_catalog.json`). Each tier looks clearly richer than the previous (frame, glow, reveal animation, your call); the tier must read without a label.
First release: gifts go to the marriage partner only (as today), new tiers and shelf. Later to any player, then add "decline gifts" and "report note".
Send flow: choose recipient (search by name/@username, recent) → gift → optional note up to 60 chars → confirm with price.
Error texts: "5 gifts per day", "Max 3 per person per day", "You cannot gift yourself".
Success: short animation; recipient gets a bot notification.

## 3. Gift shelf in profile
**Own profile**, section "Gifts": four shelves by tier, slots on each, empty slots as silhouettes. Counters "received / sent" on top.
Tap a gift: who sent, when, note, tier. User can **pin up to 3** to the showcase (star).
History: received and sent lists, tier filter.
**Other profile / public card**: only pinned gifts (max 3) and the total count; the full shelf is private. A top-tier gift gives a small badge next to the name (your badge rules).
Empty: "No gifts yet" + "Send a gift" only in someone else's profile.
(Today the gifts screen is unreachable: there is no `#pro-marriage-card` host. A new profile block is needed.)

## 4. Pets: level-up
"Upgrade" button on the pet card (backend in PR #25, dark behind a flag). Shows the step price: 🃏 cards (needed/have), 🪙 Mora, and on steps into L5/L10/L15 also 🔮 Essence. Card progress bar; if one thing is missing it must be visible at once.
Max level is 16. Small milestone mark at 5/10/15. Data: `GET /pets-v1/me` → `level_up: {enabled, max_level, steps: {pet_id: {cards, mora, essence, cards_have, level_after} | null}}`; action: `POST /pets-v1/level-up {pet_id, action_id}`.

## 5. Data (proposed, final names at implementation)
- `GET /api/shop/catalog` → `{balances, items:[{id, section, mode, name, icon, tier, cost:{mora,dia,zar,ess}, gives, limit:{period,max,left,resets_in}, affordable, missing:{...}}]}`
- `POST /api/shop/buy {item_id, qty}` → `{ok, balances, receipt}` or `{error:{code,message}}` (`not_enough`, `limit`, `disabled`)
- `POST /api/gifts/send {to, gift_id, note}`; `GET /api/profile/gifts` (own shelf); the public card returns pinned gifts only.
- Assets: 12 gifts and key tiers need art; emoji placeholders come from the catalog.

## 6. Do not
- No "savings" labels, countdown pressure, red "N left" badges (real limits only).
- Never show Dark Mora or Echo Shards anywhere: they are being retired.
- Keep currency names: Mora, Diamonds, Zarniki, Essence, Cards, Jokers, Keys.
