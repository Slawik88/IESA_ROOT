"""Full UI/UX redesign script for index.html
Replaces <style> block and key HTML structural issues.
"""
import re

SRC = r'g:\IESA_ROOT\PredvestnikBot\web\index.html'

with open(SRC, 'r', encoding='utf-8') as f:
    html = f.read()

# ============================================================
# 1. NEW CSS — comprehensive design system
# ============================================================
NEW_CSS = r"""
:root{
  --bg:#09090f;--bg2:#0e1020;--bg3:#161a2a;--card:#111426;
  --border:#1e2244;--accent:#7c6af7;--accent2:#a855f7;
  --gold:#f4c542;--green:#22c55e;--red:#ef4444;--red2:#dc2626;
  --text:#e8eaf6;--text2:#7880a8;--radius:16px
}

/* ==== THEMES ==== */
@keyframes themeGradShift{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}
body[data-theme="fire"]{--bg:#100600;--bg2:#180c00;--bg3:#231200;--accent:#fb923c;--accent2:#f97316;--gold:#fbbf24;--card:#160900;--border:#5c2000;--text:#fff0e6;--text2:#d97020;background:#100600}
body[data-theme="ice"]{--bg:#030c18;--bg2:#05111e;--bg3:#0a1a2e;--accent:#38bdf8;--accent2:#7dd3fc;--gold:#93c5fd;--card:#040d18;--border:#163a58;--text:#e8f4fd;--text2:#5090c0;background:#030c18}
body[data-theme="neon"]{--bg:#07000f;--bg2:#0d001b;--bg3:#150028;--accent:#a855f7;--accent2:#7dd3fc;--card:#0a0016;--border:#3d0080;--text:#f0e8ff;--text2:#9060d0;background:linear-gradient(-45deg,#07000f,#0f001e,#07000f,#130024);background-size:400% 400%;animation:themeGradShift 12s ease infinite}
body[data-theme="royal"]{--bg:#0a0700;--bg2:#140e00;--bg3:#1e1500;--accent:#f4c542;--accent2:#fbbf24;--gold:#ffd700;--card:#0f0a00;--border:#5a4200;--text:#fff5c8;--text2:#c09020;background:linear-gradient(-45deg,#0a0700,#181000,#0a0700,#1a1100);background-size:400% 400%;animation:themeGradShift 14s ease infinite}
body[data-theme="abyss"]{--bg:#06060f;--bg2:#0a0a1c;--bg3:#101024;--accent:#818cf8;--accent2:#a5b4fc;--card:#070716;--border:#1e1e48;--text:#e4e4ff;--text2:#6060a8;background:linear-gradient(-45deg,#060610,#0a0a1e,#06060f,#0d0d22);background-size:400% 400%;animation:themeGradShift 18s ease infinite}
body[data-theme="sakura"]{--bg:#0b0710;--bg2:#140e22;--bg3:#1c1430;--accent:#f472b6;--accent2:#e879b0;--gold:#f9a8d4;--card:#0f081e;--border:#481240;--text:#ffe4f5;--text2:#b04888;background:linear-gradient(-45deg,#0b0710,#130c20,#0b0710,#150d1c);background-size:400% 400%;animation:themeGradShift 16s ease infinite}

/* ==== RESET ==== */
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:14px;min-height:100vh;overflow-x:hidden;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}

/* ==== CATEGORY BAR ==== */
.cat-bar{display:flex;background:var(--bg2);border-bottom:1.5px solid var(--border);position:sticky;top:0;z-index:102;padding:0 4px}
.cat-btn{flex:1;padding:8px 4px 6px;border:none;background:none;cursor:pointer;font-size:19px;line-height:1.1;color:var(--text2);border-bottom:2.5px solid transparent;transition:all .2s;min-height:48px;display:flex;flex-direction:column;align-items:center;gap:2px;position:relative}
.cat-btn span{display:block;font-size:10px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;transition:color .2s}
.cat-btn.active{color:var(--accent);border-bottom-color:var(--accent)}
.cat-btn.active span{color:var(--accent)}
.cat-btn:active{transform:scale(.9)}

/* ==== TAB BAR ==== */
.tabs{display:flex;background:var(--bg2);border-bottom:1.5px solid var(--border);overflow-x:auto;position:sticky;top:48px;z-index:100;scrollbar-width:none;padding:6px 8px;gap:5px}
.tabs::-webkit-scrollbar{display:none}
.tab-btn{flex:0 0 auto;padding:5px 12px;font-size:12px;font-weight:600;color:var(--text2);border:1.5px solid transparent;background:none;cursor:pointer;white-space:nowrap;border-radius:20px;transition:all .2s;line-height:1.4}
.tab-btn.active{background:rgba(124,106,247,.16);color:var(--accent);border-color:rgba(124,106,247,.38);font-weight:700}

/* ==== GLOBAL BALANCE BAR ==== */
.balance-bar{display:flex;align-items:center;justify-content:flex-end;gap:5px;padding:5px 14px;background:var(--bg2);border-bottom:1px solid var(--border);font-size:13px;font-weight:800;color:var(--gold);position:sticky;top:86px;z-index:90;letter-spacing:.2px}

/* ==== TAB CONTENT ==== */
.tab-content{display:none;padding:12px;padding-bottom:max(env(safe-area-inset-bottom,0px),16px);max-width:480px;margin:0 auto}
@media(min-width:600px){.tab-content{max-width:min(920px,98vw);padding:16px 20px}}
.tab-content.active{display:block}

/* ==== CARDS ==== */
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin-bottom:10px;animation:fade-in .3s ease backwards;transition:box-shadow .2s,transform .2s}
.card:hover{transform:translateY(-1px);box-shadow:0 6px 28px rgba(0,0,0,.38)}
.tab-content.active .card:nth-child(1){animation-delay:0s}
.tab-content.active .card:nth-child(2){animation-delay:.05s}
.tab-content.active .card:nth-child(3){animation-delay:.1s}
.tab-content.active .card:nth-child(4){animation-delay:.15s}
.tab-content.active .card:nth-child(5){animation-delay:.2s}
.tab-content.active .card:nth-child(6){animation-delay:.24s}
.tab-content.active .card:nth-child(7){animation-delay:.28s}
.tab-content.active .card:nth-child(8){animation-delay:.32s}
.card-title{font-size:11px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.7px;margin-bottom:12px;display:flex;align-items:center;gap:6px}

/* Profile hero card */
.profile-hero{background:linear-gradient(135deg,rgba(124,106,247,.1) 0%,rgba(168,85,247,.06) 100%);border-color:rgba(124,106,247,.28)}

/* ==== PROFILE HERO HEADER ==== */
.profile-hero-header{display:flex;align-items:center;gap:14px;padding-bottom:14px;border-bottom:1px solid var(--border);margin-bottom:12px}
.profile-avatar{width:62px;height:62px;border-radius:50%;background:linear-gradient(135deg,var(--accent),var(--accent2));border:3px solid rgba(124,106,247,.5);display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:800;color:#fff;flex-shrink:0;box-shadow:0 0 22px rgba(124,106,247,.35);text-shadow:0 1px 4px rgba(0,0,0,.3)}
.profile-info{flex:1;min-width:0}
.profile-name{font-size:18px;font-weight:800;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;line-height:1.2}
.profile-title-line{font-size:12px;color:var(--accent);margin-top:3px;font-weight:600}
.profile-level-pill{display:inline-flex;align-items:center;gap:4px;background:rgba(124,106,247,.16);border:1px solid rgba(124,106,247,.3);border-radius:20px;padding:3px 10px;font-size:11px;font-weight:700;color:var(--accent);margin-top:6px}

/* ==== STAT ROWS ==== */
.stat-row{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid rgba(255,255,255,.05);transition:background .12s,padding .12s,border-radius .12s}
.stat-row:last-child{border-bottom:none}
.stat-row:hover{background:rgba(255,255,255,.03);border-radius:8px;padding-left:6px;padding-right:6px}
.stat-label{color:var(--text2);font-size:12px;display:flex;align-items:center;gap:5px}
.stat-value{font-weight:700;color:var(--text);font-size:13px}

/* ==== BUTTONS ==== */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:11px 18px;border:none;border-radius:12px;cursor:pointer;font-size:13px;font-weight:700;transition:all .17s;width:100%;margin-top:6px;letter-spacing:.2px;position:relative;overflow:hidden}
.btn:active{transform:scale(.96)}
.btn:hover:not(:disabled){filter:brightness(1.08)}
.btn-primary{background:linear-gradient(135deg,#6c5fe0,#9b4dca);color:#fff;box-shadow:0 4px 16px rgba(124,106,247,.32)}
.btn-primary:hover{box-shadow:0 6px 22px rgba(124,106,247,.48)}
.btn-green{background:linear-gradient(135deg,#15813d,#1da04d);color:#fff;box-shadow:0 4px 14px rgba(34,197,94,.28)}
.btn-red{background:linear-gradient(135deg,#b91c1c,#dc2626);color:#fff;box-shadow:0 4px 14px rgba(239,68,68,.28)}
.btn-gold{background:linear-gradient(135deg,#b8870a,#e8b820);color:#000;box-shadow:0 4px 14px rgba(244,197,66,.32);font-weight:800}
.btn:disabled,.btn[disabled]{opacity:.38;pointer-events:none;box-shadow:none}
.btn-sm{padding:8px 14px;font-size:12px;width:auto;margin-top:0;border-radius:10px}
.btn-row{display:flex;gap:8px}
.btn-row .btn{flex:1}

/* ==== PROGRESS BARS ==== */
.progress-bar{height:6px;background:var(--bg3);border-radius:3px;overflow:hidden;margin:6px 0}
.progress-fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:3px;transition:width .5s cubic-bezier(.4,0,.2,1)}
.pet-bar{height:6px;background:var(--bg3);border-radius:3px;overflow:hidden;margin:6px 0}
.pet-bar-fill{height:100%;border-radius:3px;transition:width .4s}
.pet-bar-fill.tired{background:linear-gradient(90deg,#ef4444,#f97316)}
.pet-bar-fill.ok{background:linear-gradient(90deg,#15863e,#22c55e)}

/* ==== BADGES ==== */
.badge{display:inline-block;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700}
.badge-junk{background:rgba(107,114,128,.2);color:#9aa0b8}
.badge-common{background:rgba(59,130,246,.2);color:#60a5fa}
.badge-rare{background:rgba(139,92,246,.22);color:#a78bfa}
.badge-legendary{background:rgba(245,158,11,.2);color:#fbbf24}

/* ==== INPUTS ==== */
.input-group{display:flex;gap:8px;margin-top:10px}
.input-group input{flex:1;background:var(--bg3);border:1.5px solid var(--border);border-radius:10px;padding:10px 14px;color:var(--text);font-size:14px;outline:none;transition:border-color .2s,box-shadow .2s}
.input-group input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(124,106,247,.2)}
.input-field{background:var(--bg3);border:1.5px solid var(--border);border-radius:10px;padding:10px 14px;color:var(--text);width:100%;box-sizing:border-box;font-size:14px;outline:none;transition:border-color .2s,box-shadow .2s}
.input-field:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(124,106,247,.2)}
select{background:var(--bg3);border:1.5px solid var(--border);border-radius:10px;padding:10px 14px;color:var(--text);font-size:13px;outline:none;width:100%;-webkit-appearance:none;appearance:none;transition:border-color .2s}
select:focus{border-color:var(--accent)}

/* ==== TOAST ==== */
.toast{position:fixed;bottom:80px;left:50%;transform:translateX(-50%) translateY(20px);background:rgba(14,16,32,.96);border:1px solid var(--border);border-radius:14px;padding:11px 20px;color:var(--text);font-size:13px;font-weight:600;opacity:0;transition:all .3s;z-index:9999;pointer-events:none;max-width:min(360px,88vw);text-align:center;white-space:pre-wrap;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);box-shadow:0 8px 28px rgba(0,0,0,.5)}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.toast.error{border-color:var(--red);color:#fca5a5;background:rgba(28,8,8,.95)}
.toast.success{border-color:var(--green);color:#86efac;background:rgba(8,22,12,.95)}
@keyframes toast-in{0%{opacity:0;transform:translateX(-50%) translateY(30px) scale(.9)}60%{transform:translateX(-50%) translateY(-4px) scale(1.02)}100%{opacity:1;transform:translateX(-50%) translateY(0) scale(1)}}
.toast.show{animation:toast-in .35s ease-out forwards}

/* ==== GACHA OVERLAY ==== */
#gachaOverlay{position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:9000;display:none;flex-direction:column;align-items:center;justify-content:flex-start;padding:20px;overflow-y:auto}
#gachaOverlay.active{display:flex;animation:fade-backdrop .3s ease}
.gacha-title{font-size:23px;font-weight:800;background:linear-gradient(135deg,#a855f7,#f4c542);background-clip:text;-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:20px;text-align:center}
.gacha-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(70px,1fr));gap:8px;width:100%;max-width:440px}
.gacha-card{aspect-ratio:3/4;border-radius:12px;position:relative;perspective:600px;cursor:default}
.gacha-card-inner{width:100%;height:100%;transform-style:preserve-3d;transition:transform .6s ease;position:relative}
.gacha-card.flipped .gacha-card-inner{transform:rotateY(180deg)}
.gacha-card-front,.gacha-card-back{position:absolute;width:100%;height:100%;backface-visibility:hidden;border-radius:12px;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:6px;text-align:center}
.gacha-card-front{background:linear-gradient(135deg,#4f46e5,#7c3aed);border:2px solid rgba(255,255,255,.22);font-size:28px}
.gacha-card-back{transform:rotateY(180deg)}
.gacha-card-back.junk{background:linear-gradient(135deg,#2a2e40,#1d2030);border:2px solid #363a50}
.gacha-card-back.common{background:linear-gradient(135deg,#183260,#1e3c90);border:2px solid #3060c0}
.gacha-card-back.rare{background:linear-gradient(135deg,#2a1c68,#4a38a8);border:2px solid #7050d8}
.gacha-card-back.legendary{background:linear-gradient(135deg,#381800,#6e3000);border:2px solid #d08000;animation:legendary-glow 1.5s ease-in-out infinite alternate}
.gacha-card-back .card-emoji{font-size:24px;margin-bottom:4px}
.gacha-card-back .card-name{font-size:11px;font-weight:600;color:#fff;word-break:break-word;line-height:1.2}
@keyframes legendary-glow{from{box-shadow:0 0 6px #c07000}to{box-shadow:0 0 24px #f59e0b,0 0 48px rgba(245,158,11,.35)}}
.gacha-close{margin-top:16px;padding:11px 32px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.14);border-radius:12px;color:var(--text);cursor:pointer;font-size:14px;font-weight:600;backdrop-filter:blur(8px);transition:background .15s}
.gacha-close:hover{background:rgba(255,255,255,.12)}
.gacha-item-sheet{background:var(--card);border:1px solid var(--border);border-radius:20px;padding:22px;max-width:330px;width:100%;box-sizing:border-box;animation:sheet-slide-up .3s cubic-bezier(.34,1.56,.64,1);box-shadow:0 24px 64px rgba(0,0,0,.65)}
.gitem-stats-row{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin-top:14px}
.gitem-stat{background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:6px 12px;font-size:12px;color:var(--text2);display:flex;gap:5px;align-items:center}

/* ==== SUMMON ANIMATION ==== */
@keyframes summon-spin{0%{transform:rotate(0deg) scale(.3);opacity:0}30%{opacity:1;transform:rotate(180deg) scale(1)}100%{transform:rotate(720deg) scale(1.1);opacity:0}}
@keyframes summon-pulse{0%{box-shadow:0 0 20px rgba(168,85,247,.4)}50%{box-shadow:0 0 72px rgba(168,85,247,.9),0 0 120px rgba(244,197,66,.28)}100%{box-shadow:0 0 20px rgba(168,85,247,.4)}}
@keyframes summon-ring{0%{transform:scale(.5);opacity:0;border-width:3px}50%{opacity:1}100%{transform:scale(2.5);opacity:0;border-width:0px}}
@keyframes summon-particle{0%{transform:translateY(0) scale(1);opacity:1}100%{transform:translateY(-80px) scale(0);opacity:0}}
#gachaSummon{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:2}
.summon-circle{width:160px;height:160px;border-radius:50%;border:3px solid rgba(168,85,247,.6);position:relative;animation:summon-pulse 1s ease-in-out infinite}
.summon-circle::before,.summon-circle::after{content:'';position:absolute;inset:-12px;border-radius:50%;border:2px solid transparent;border-top-color:#a855f7;border-bottom-color:#f4c542;animation:summon-spin 2s linear infinite}
.summon-circle::after{inset:-24px;animation-duration:3s;animation-direction:reverse;border-top-color:#f4c542;border-bottom-color:#a855f7}
.summon-ring{position:absolute;width:80px;height:80px;border-radius:50%;border:2px solid #a855f7;animation:summon-ring 1.2s ease-out infinite}
.summon-text{margin-top:24px;font-size:16px;font-weight:700;color:#a855f7;text-shadow:0 0 24px rgba(168,85,247,.6);letter-spacing:1px}
.summon-particles{position:absolute;width:200px;height:200px}
.summon-particles span{position:absolute;width:4px;height:4px;background:#f4c542;border-radius:50%;animation:summon-particle 1.5s ease-out infinite}

/* ==== MICRO-ANIMATIONS ==== */
@keyframes celebrate-pop{0%{transform:scale(0);opacity:0}50%{transform:scale(1.3);opacity:1}100%{transform:scale(1);opacity:1}}
@keyframes card-appear{from{opacity:0;transform:scale(.7)}to{opacity:1;transform:scale(1)}}
@keyframes rare-shine{0%{background-position:200% center}100%{background-position:-200% center}}
@keyframes confetti-fall{0%{transform:translateY(-10px) rotate(0deg);opacity:1}100%{transform:translateY(100vh) rotate(720deg);opacity:0}}
.gacha-card-back.rare .card-emoji{animation:celebrate-pop .5s ease backwards}
.gacha-card-back.legendary .card-emoji{animation:celebrate-pop .5s ease backwards}
@keyframes checkin-burst{0%{transform:scale(0) rotate(-20deg);opacity:0}60%{transform:scale(1.2) rotate(5deg);opacity:1}100%{transform:scale(1) rotate(0deg);opacity:1}}
@keyframes streak-fire{0%,100%{text-shadow:0 0 4px #f59e0b}50%{text-shadow:0 0 16px #f59e0b,0 0 30px #f97316}}
.checkin-celebrate{animation:checkin-burst .5s ease-out}
@keyframes exped-depart{0%{transform:translateX(0) scale(1);opacity:1}100%{transform:translateX(80px) scale(.6);opacity:0}}
@keyframes exped-reward{0%{transform:scale(0) rotate(-10deg);opacity:0}60%{transform:scale(1.15) rotate(3deg)}100%{transform:scale(1) rotate(0);opacity:1}}
.exped-reward-anim{animation:exped-reward .5s ease-out}
@keyframes coin-spin{0%{transform:rotateY(0deg) scale(1)}50%{transform:rotateY(900deg) scale(1.3)}100%{transform:rotateY(1800deg) scale(1)}}
@keyframes coin-land-win{0%{transform:scale(1)}50%{transform:scale(1.4)}100%{transform:scale(1)}}
@keyframes coin-land-lose{0%{transform:scale(1)}50%{transform:scale(.7);opacity:.5}100%{transform:scale(1);opacity:1}}
#coinEmoji{display:inline-block;font-size:52px;transition:transform .3s}
@keyframes fade-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.tab-content.active{animation:fade-in .28s ease}
@keyframes fade-backdrop{from{opacity:0}to{opacity:1}}
@keyframes slide-up{from{transform:translateY(100%)}to{transform:translateY(0)}}
@keyframes sheet-slide-up{from{transform:translateY(30px);opacity:0}to{transform:translateY(0);opacity:1}}
@keyframes bal-flash{0%{transform:scale(1)}30%{transform:scale(1.12)}100%{transform:scale(1)}}
.bal-update{animation:bal-flash .3s ease}
@keyframes flash-success{0%{box-shadow:0 0 0 0 rgba(34,197,94,0)}35%{box-shadow:0 0 0 8px rgba(34,197,94,.4)}100%{box-shadow:0 0 0 0 rgba(34,197,94,0)}}
.flash-success{animation:flash-success .6s ease}
@keyframes item-pulse{0%{box-shadow:0 0 0 0 rgba(168,85,247,.3)}70%{box-shadow:0 0 0 10px rgba(168,85,247,0)}100%{box-shadow:0 0 0 0 rgba(168,85,247,0)}}
.shop-item:active{animation:item-pulse .4s ease}
.cat-btn:active{transform:scale(.9)}
@keyframes loading-pulse{0%,100%{opacity:.4}50%{opacity:1}}
.loading{color:var(--text2);text-align:center;padding:36px;font-size:13px;animation:loading-pulse 1.5s ease-in-out infinite}
#rarityFlash{position:fixed;inset:0;z-index:8995;pointer-events:none;opacity:0;transition:opacity .12s}

/* ==== LEADERBOARD ==== */
.lb-entry{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:12px;margin-bottom:5px;background:var(--bg3);border:1px solid var(--border);transition:border-color .15s}
.lb-entry:hover{border-color:rgba(124,106,247,.32)}
.lb-entry.highlight{background:rgba(244,197,66,.08);border-color:rgba(244,197,66,.28)}
.lb-rank{width:26px;text-align:center;font-weight:800;font-size:14px;color:var(--text2)}
.lb-rank.top3{color:var(--gold)}
.lb-name{flex:1;font-size:13px;font-weight:600}
.lb-score{font-weight:700;color:var(--accent);font-size:12px}

/* ==== SHOP ==== */
.shop-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(102px,1fr));gap:10px}
.shop-item{background:var(--bg3);border:1.5px solid var(--border);border-radius:14px;padding:12px 8px;text-align:center;cursor:pointer;transition:all .2s;display:flex;flex-direction:column;align-items:center;justify-content:space-between;min-height:90px;gap:4px}
.shop-item:hover{transform:translateY(-3px);box-shadow:0 8px 24px rgba(0,0,0,.35);border-color:var(--accent)}
.shop-item.owned{border-color:rgba(34,197,94,.45)}
.shop-item.active-item{border-color:var(--gold);background:rgba(244,197,66,.06)}
.shop-item-emoji{font-size:26px;line-height:1}
.shop-item-name{font-size:11px;font-weight:600;word-break:break-word;line-height:1.3;color:var(--text)}
.shop-item-price{font-size:11px;color:var(--text2);margin-top:auto}
.shop-item-price.free{color:var(--green)}

/* Shop list cards */
.scard{background:var(--bg3);border:1.5px solid var(--border);border-radius:14px;padding:13px 13px 13px 16px;display:flex;gap:12px;align-items:flex-start;cursor:pointer;transition:all .2s;position:relative;margin-bottom:8px;overflow:hidden}
.scard:hover{transform:translateY(-2px);box-shadow:0 6px 22px rgba(124,106,247,.16);border-color:rgba(124,106,247,.5)}
.scard:active{transform:scale(.985)}
.scard.owned{border-color:rgba(34,197,94,.45)}
.scard.scard-active{border-color:var(--gold);background:rgba(244,197,66,.04)}
.scard-accent{position:absolute;left:0;top:0;bottom:0;width:4px;border-radius:4px 0 0 4px}
.scard-icon{font-size:24px;min-width:32px;text-align:center;margin-top:2px}
.scard-body{flex:1;min-width:0}
.scard-name{font-size:13px;font-weight:700;color:var(--text);margin-bottom:3px}
.scard-desc{font-size:12px;color:var(--text2);line-height:1.4;margin-bottom:5px}
.scard-footer{display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.sbadge{font-size:10px;font-weight:700;padding:3px 9px;border-radius:20px;white-space:nowrap}
.sbadge-price{background:rgba(99,102,241,.18);color:#a5b4fc}
.sbadge-owned{background:rgba(34,197,94,.14);color:#4ade80}
.sbadge-active{background:rgba(244,197,66,.18);color:var(--gold)}
.sbadge-free{background:rgba(34,197,94,.12);color:#4ade80}
.cosmetic-preview{display:flex;align-items:center;gap:5px;margin:3px 0 2px;padding:4px 10px;background:rgba(255,255,255,.04);border-radius:8px;font-size:11px;line-height:1.35;border:1px solid rgba(255,255,255,.07);flex-wrap:wrap;width:fit-content;max-width:100%}

/* ==== GACHA DROP RATES MODAL ==== */
.rates-modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.78);z-index:9200;display:none;align-items:flex-end}
.rates-modal-overlay.open{display:flex;animation:fade-backdrop .2s ease}
.rates-sheet{background:var(--bg2);border-radius:22px 22px 0 0;width:100%;max-height:83vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 -10px 48px rgba(0,0,0,.7)}
.rates-modal-overlay.open .rates-sheet{animation:sheet-slide-up .28s ease}
.rates-header{padding:16px 18px;border-bottom:1px solid var(--border);font-weight:700;font-size:15px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.rates-body{overflow-y:auto;padding:10px 14px 28px}
.rarity-section{margin-bottom:14px}
.rarity-section-hdr{display:flex;align-items:center;gap:8px;padding:9px 12px;border-radius:10px;margin-bottom:6px;font-weight:700;font-size:13px}
.rarity-section-hdr.junk{background:rgba(107,114,128,.12);color:#a0a8b8}
.rarity-section-hdr.common{background:rgba(59,130,246,.12);color:#60a5fa}
.rarity-section-hdr.rare{background:rgba(139,92,246,.15);color:#a78bfa}
.rarity-section-hdr.legendary{background:rgba(245,158,11,.14);color:#f59e0b}
.rates-row{display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:8px;font-size:12px}
.rates-row:nth-child(even){background:var(--bg3)}
.rates-row-icon{font-size:18px;min-width:28px;text-align:center}
.rates-row-name{flex:1}
.rates-row-pct{font-weight:700;color:var(--text2);min-width:46px;text-align:right}

/* ==== ROULETTE ==== */
.roulette-bet-chip{display:inline-flex;align-items:center;justify-content:center;padding:7px 14px;border-radius:20px;background:var(--bg3);border:1.5px solid var(--border);cursor:pointer;font-size:12px;font-weight:700;transition:all .15s;user-select:none;white-space:nowrap}
.roulette-bet-chip:active{transform:scale(.93)}
.roulette-bet-chip.active{border-color:var(--accent);background:rgba(99,102,241,.18);color:var(--accent)}
.rbc-red{border-color:rgba(220,38,38,.4);color:#fca5a5}
.rbc-red.active{background:rgba(220,38,38,.14);border-color:#dc2626}
.rbc-black{border-color:rgba(75,85,99,.4);color:#9ca3af}
.rbc-black.active{background:rgba(75,85,99,.2);border-color:#6b7280;color:#d1d5db}
.rbc-green{border-color:rgba(22,163,74,.4);color:#4ade80}
.rbc-green.active{background:rgba(22,163,74,.14);border-color:#16a34a}
@keyframes roulette-result-pop{0%{transform:scale(.8);opacity:0}65%{transform:scale(1.08)}100%{transform:scale(1);opacity:1}}

/* ==== INVENTORY ==== */
.subtabs{display:flex;gap:6px;margin-bottom:12px;overflow-x:auto;scrollbar-width:none;padding-bottom:2px}
.subtabs::-webkit-scrollbar{display:none}
.subtab-btn{padding:6px 14px;border:1.5px solid var(--border);background:var(--bg3);color:var(--text2);border-radius:20px;cursor:pointer;font-size:12px;font-weight:600;white-space:nowrap;transition:all .15s}
.subtab-btn.active{background:var(--accent);color:#fff;border-color:var(--accent);box-shadow:0 3px 14px rgba(124,106,247,.38)}
.inv-item{display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--bg3);border:1px solid var(--border);border-radius:12px;margin-bottom:6px;position:relative;transition:border-color .15s}
.inv-item:hover{border-color:rgba(124,106,247,.38)}
.inv-item .ii-emoji{font-size:22px;min-width:28px;text-align:center}
.inv-item .ii-info{flex:1}
.inv-item .ii-info .ii-name{font-size:13px;font-weight:600}
.inv-item .ii-info .ii-rarity{font-size:11px;color:var(--text2);margin-top:1px}
.inv-item-select{position:absolute;top:10px;left:10px;width:18px;height:18px;z-index:10}
.inv-item.selectable{padding-left:38px}
.inv-item.selected{background:rgba(124,106,247,.1);border-color:rgba(124,106,247,.48)}
.enhance-level{display:inline-block;background:var(--gold);color:#000;font-size:10px;font-weight:800;padding:2px 7px;border-radius:10px;margin-left:6px}
.enhance-cost{font-size:11px;color:var(--text2);margin-top:2px}
.enhance-success{color:var(--green)}
.enhance-danger{color:var(--red)}
.buff-item{display:flex;justify-content:space-between;align-items:center;padding:6px 0;font-size:12px;border-bottom:1px solid rgba(255,255,255,.04)}
.buff-item:last-child{border-bottom:none}
.buff-name{color:var(--green);font-weight:600}
.buff-time{color:var(--text2);font-size:11px}
.selected-count{font-weight:700;color:var(--accent)}
.sell-value{font-weight:700;color:var(--gold)}
.bond-canvas-wrap{height:60px;margin:6px 0;position:relative;background:var(--bg3);border-radius:10px;overflow:hidden}

/* ==== WALLET MODAL ==== */
.wallet-modal{position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:9500;display:none;align-items:flex-end;justify-content:center}
.wallet-modal.open{display:flex;animation:fade-backdrop .2s ease}
.wallet-sheet{background:var(--bg2);border:1px solid var(--border);border-radius:22px 22px 0 0;padding:22px 18px max(env(safe-area-inset-bottom,0px),28px);width:100%;max-width:480px;box-shadow:0 -12px 56px rgba(0,0,0,.7)}
.wallet-modal.open .wallet-sheet{animation:slide-up .3s cubic-bezier(.34,1.2,.64,1)}
.wallet-sheet-title{font-size:11px;font-weight:700;color:var(--text2);text-align:center;text-transform:uppercase;letter-spacing:.7px;margin-bottom:4px}
.wallet-sheet-price{font-size:32px;font-weight:900;color:var(--gold);text-align:center;margin-bottom:20px}
.wallet-options{display:flex;gap:12px;margin-bottom:14px}
.wallet-opt{flex:1;background:var(--bg3);border:2px solid var(--border);border-radius:14px;padding:16px 10px;display:flex;flex-direction:column;align-items:center;gap:5px;cursor:pointer;transition:all .15s;color:var(--text);font-family:inherit}
.wallet-opt:hover{border-color:var(--accent);background:rgba(124,106,247,.08)}
.wallet-opt.insufficient{opacity:.38;pointer-events:none}
.wallet-opt-icon{font-size:28px}
.wallet-opt-label{font-size:11px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.3px}
.wallet-opt-balance{font-size:15px;font-weight:800}
.wallet-cancel{width:100%;background:transparent;border:1.5px solid var(--border);border-radius:12px;padding:11px;color:var(--text2);cursor:pointer;font-size:13px;font-weight:600;font-family:inherit;transition:all .15s}
.wallet-cancel:hover{border-color:var(--red);color:#fca5a5}

/* ==== USER PICKER ==== */
.user-picker-modal{position:fixed;inset:0;background:rgba(0,0,0,.78);z-index:9500;display:none;align-items:flex-end}
.user-picker-modal.open{display:flex;animation:fade-backdrop .2s ease}
.user-picker-sheet{background:var(--bg2);border-radius:22px 22px 0 0;width:100%;max-height:76vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 -10px 48px rgba(0,0,0,.7)}
.user-picker-modal.open .user-picker-sheet{animation:slide-up .3s ease}
.user-picker-item{display:flex;align-items:center;gap:12px;padding:13px 16px;border-bottom:1px solid var(--border);cursor:pointer;min-height:56px;transition:background .15s}
.user-picker-item:active{background:var(--bg3)}
.user-picker-avatar{width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,var(--accent),var(--accent2));display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;flex-shrink:0;color:#fff}
.selected-user-btn{display:flex;align-items:center;gap:10px;padding:11px 14px;background:var(--bg3);border:1.5px solid var(--border);border-radius:12px;cursor:pointer;min-height:50px;width:100%;color:var(--text);font-size:13px;transition:border-color .15s}
.selected-user-btn:hover{border-color:var(--accent)}

/* ==== PUBLIC PROFILE ==== */
.pub-profile-overlay{position:fixed;inset:0;z-index:9100;background:rgba(0,0,0,.72);display:none;align-items:flex-end;justify-content:center}
.pub-profile-overlay.open{display:flex;animation:fade-backdrop .2s ease}
.pub-profile-sheet{background:var(--bg2);border-radius:22px 22px 0 0;padding:22px;width:100%;max-width:480px;max-height:86vh;overflow-y:auto;box-shadow:0 -10px 48px rgba(0,0,0,.7)}
.pub-profile-overlay.open .pub-profile-sheet{animation:slide-up .3s ease}
.pub-profile-header{display:flex;align-items:center;gap:14px;margin-bottom:16px}
.pub-close-btn{margin-left:auto;background:rgba(255,255,255,.08);border:none;color:var(--text2);font-size:16px;cursor:pointer;padding:6px 10px;border-radius:8px;transition:all .15s}
.pub-close-btn:hover{background:rgba(255,255,255,.14);color:var(--text)}

/* ==== AMOUNT PRESETS ==== */
.amt-presets{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.amt-chip{padding:6px 13px;background:var(--bg3);border:1.5px solid var(--border);border-radius:20px;cursor:pointer;font-size:12px;font-weight:600;color:var(--text2);transition:all .15s}
.amt-chip:active,.amt-chip.sel{background:var(--accent);border-color:var(--accent);color:#fff}

/* ==== CALENDAR ==== */
.cal-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:7px;margin:12px 0}
.cal-day{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:7px 4px;border-radius:10px;background:var(--bg3);border:1px solid var(--border);min-height:58px;cursor:default;transition:border-color .15s}
.cal-day.done{background:rgba(34,197,94,.09);border-color:rgba(34,197,94,.4)}
.cal-day.today{background:rgba(124,106,247,.14);border-color:var(--accent);box-shadow:0 0 12px rgba(124,106,247,.3)}
.cal-day.checkpoint{border-color:var(--gold);background:rgba(244,197,66,.06)}
.cal-day .cd-num{font-size:10px;font-weight:700;color:var(--text2);margin-bottom:2px}
.cal-day .cd-icon{font-size:17px;line-height:1}
.cal-day .cd-mora{font-size:10px;color:var(--gold);font-weight:700;margin-top:2px}

/* ==== BANK ==== */
.bank-balance-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px}
.bank-balance-cell{background:var(--bg3);border:1px solid var(--border);border-radius:14px;padding:16px;text-align:center}
.bank-balance-label{font-size:11px;color:var(--text2);font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}
.bank-balance-val{font-size:22px;font-weight:800;color:var(--gold)}
.bank-section-title{font-size:11px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.6px;margin:14px 0 8px}
.bank-empty{background:var(--bg3);border:1px solid var(--border);border-radius:14px;padding:20px;text-align:center;color:var(--text2);font-size:13px;margin-bottom:10px}
.bank-dep-card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:14px;margin-bottom:10px;transition:border-color .2s}
.bank-dep-card.mature{border-color:rgba(34,197,94,.42)}
.bank-dep-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.bank-dep-amounts{font-size:16px;font-weight:700}
.bank-dep-reward{color:var(--green);font-weight:700}
.bank-dep-badge{font-size:11px;font-weight:700;background:rgba(124,106,247,.18);color:var(--accent);border-radius:20px;padding:3px 10px;white-space:nowrap}
.bank-dep-track{height:5px;background:var(--bg3);border-radius:3px;overflow:hidden;margin:8px 0 10px}
.bank-dep-bar{height:100%;border-radius:3px;transition:width .3s}
.bank-dep-footer{display:flex;justify-content:space-between;align-items:center;font-size:11px;color:var(--text2);margin-bottom:10px}
.bank-dep-status.ready{color:var(--green);font-weight:700}
.bank-plan-tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px}
.bank-plan-tab{background:var(--bg3);border:2px solid var(--border);border-radius:12px;padding:12px 4px;cursor:pointer;text-align:center;color:var(--text2);transition:all .15s;font-family:inherit}
.bank-plan-tab.active{background:rgba(124,106,247,.12);border-color:var(--accent);color:var(--text)}
.bank-plan-tab .bpt-days{font-size:12px;font-weight:700}
.bank-plan-tab .bpt-rate{font-size:16px;font-weight:800;color:var(--green);margin-top:3px}
.bank-plan-tab.active .bpt-rate{color:#86efac}
.bank-presets{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px}
.bank-preset-btn{background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:8px 4px;font-size:12px;font-weight:600;color:var(--text);cursor:pointer;text-align:center;transition:all .15s;font-family:inherit}
.bank-preset-btn:hover{border-color:var(--accent);color:var(--accent);background:rgba(124,106,247,.08)}
.bank-amount-inp{width:100%;background:var(--bg3);border:1.5px solid var(--border);border-radius:10px;padding:11px 14px;color:var(--text);font-size:14px;outline:none;margin-bottom:10px;-webkit-appearance:none;appearance:none}
.bank-amount-inp:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(124,106,247,.2)}
.bank-wallet-btns{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.bank-wallet-btns .btn{flex-direction:column;gap:2px;line-height:1.3;padding:11px 8px}
.bank-wallet-btns .btn small{font-size:11px;font-weight:500;opacity:.85}
.wallet-history-row{display:flex;justify-content:space-between;gap:10px;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:12px}
.wallet-history-row:last-child{border-bottom:none}
.wallet-history-main{min-width:0;display:flex;flex-direction:column;gap:2px}
.wallet-history-source{font-weight:700}
.wallet-history-desc{color:var(--text2);word-break:break-word}
.wallet-history-meta{display:flex;flex-direction:column;align-items:flex-end;gap:2px;flex:0 0 auto}
.wallet-history-amt{font-weight:800;font-size:13px}
.wallet-history-amt.income{color:var(--green)}
.wallet-history-amt.expense{color:var(--red)}
.wallet-history-ts{color:var(--text2);font-size:11px}

/* ==== DEV PANEL ==== */
.dev-stat{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);font-size:12px}
.dev-stat:last-child{border:none}
.dev-stat .dv{font-weight:700;color:var(--gold)}
.dev-search-wrap{position:relative;margin-bottom:8px}
.dev-search-wrap input{padding-right:32px}
.dev-dropdown{position:absolute;top:100%;left:0;right:0;background:var(--bg2);border:1px solid var(--border);border-radius:0 0 10px 10px;max-height:180px;overflow-y:auto;z-index:200;display:none}
.dev-dropdown.open{display:block}
.dev-dd-item{padding:9px 12px;cursor:pointer;font-size:13px;border-bottom:1px solid var(--border)}
.dev-dd-item:last-child{border:none}
.dev-dd-item:hover{background:var(--bg3)}
.dev-dd-item .dd-uid{font-size:11px;color:var(--text2);margin-left:6px}
.dev-sel-badge{display:none;align-items:center;gap:8px;background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:10px 12px;font-size:13px;margin-bottom:10px}
.dev-sel-badge.show{display:flex}
.dev-sel-badge-clear{margin-left:auto;cursor:pointer;color:var(--text2);font-size:16px;line-height:1}
.dev-chat-row{display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid var(--border);cursor:pointer;font-size:13px}
.dev-chat-row:last-child{border:none}
.dev-chat-row:hover .dev-chat-title{color:var(--gold)}
.dev-chat-badge{font-size:10px;padding:2px 7px;border-radius:10px;background:var(--bg3);color:var(--text2)}
.dev-chat-badge.group{background:rgba(59,130,246,.18);color:#60a5fa}
.dev-member-row{display:grid;grid-template-columns:1fr auto auto;gap:6px;align-items:center;padding:6px 0;border-bottom:1px solid var(--border);font-size:12px}
.dev-member-row:last-child{border:none}
.dev-rank-badge{font-size:10px;padding:2px 6px;border-radius:8px;background:var(--bg3)}
.dev-member-table-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:10px}
.dev-member-head,.dev-member-edit{display:grid;grid-template-columns:160px 80px 80px 140px 86px 66px 66px 66px 66px auto;gap:6px;align-items:center;min-width:720px}
.dev-member-head{padding:0 0 6px;color:var(--text2);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;border-bottom:2px solid var(--border);margin-bottom:4px}
.dev-member-edit{padding:7px 0;border-bottom:1px solid var(--border)}
.dev-member-edit:last-child{border-bottom:none}
.dev-member-edit input,.dev-member-edit select{width:100%;min-width:0;padding:6px 8px;font-size:12px}
.dev-member-name{font-size:12px;font-weight:600;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dev-mf{display:contents}
.dev-mf-label{display:none}
#devChatMembersList{scrollbar-gutter:stable}
@media(min-width:600px){.dev-member-head,.dev-member-edit{grid-template-columns:200px 90px 90px 160px 90px 74px 74px 74px 74px auto;min-width:920px;gap:8px}.dev-member-edit input,.dev-member-edit select{padding:8px 10px;font-size:13px}.dev-member-table-scroll{border:1px solid var(--border);border-radius:12px;padding:0 10px}}
.dev-inline-btn{width:auto;margin-top:0;padding:8px 10px;font-size:12px}
.dev-salary-grid{display:grid;grid-template-columns:minmax(70px,.8fr) minmax(88px,1fr) minmax(0,2fr) auto;gap:6px;align-items:center}
.dev-event-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px;margin-top:8px}
.dev-event-btn{padding:12px 6px;border-radius:12px;background:var(--bg3);border:1px solid var(--border);font-size:20px;text-align:center;cursor:pointer;transition:all .15s}
.dev-event-btn:hover{background:rgba(244,197,66,.07);border-color:var(--gold)}
.dev-event-btn .dev-event-label{font-size:11px;color:var(--text2);margin-top:4px}
.dev-log-entry{font-size:11px;line-height:1.5;padding:4px 0;border-bottom:1px solid var(--border);word-break:break-all}
.dev-log-entry:last-child{border:none}
.dev-log-ts{color:var(--text2);margin-right:6px}
.err-msg{color:#fca5a5;font-size:12px;margin-top:6px;display:none}
.dev-ban-row{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:12px}
.dev-ban-row:last-child{border:none}
.dev-ban-unban{cursor:pointer;color:#f87171;font-size:16px;margin-left:auto}

/* ==== MISC ==== */
.separator{height:1px;background:var(--border);margin:14px 0}

/* ==== MOBILE ==== */
@media(max-width:420px){
  .dev-member-head{display:none}
  .dev-member-edit{grid-template-columns:1fr 1fr;gap:6px;min-width:0}
  .dev-member-name{grid-column:1/-1}
  .dev-inline-btn{grid-column:1/-1}
  .dev-mf{display:flex;flex-direction:column;gap:2px;min-width:0}
  .dev-mf-label{display:block;font-size:9px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.3px}
  .dev-mf input,.dev-mf select{width:100%;box-sizing:border-box}
  .bank-balance-val{font-size:18px}
  .bank-balance-cell{padding:12px}
  #walletHistoryList,.wallet-history-row{font-size:11px}
  .wallet-history-ts{font-size:10px}
  #familyLogList{font-size:11px}
  .tab-content{padding:10px}
  .card{padding:13px}
}
"""

# Replace entire <style>...</style> block
html = re.sub(r'<style>.*?</style>', f'<style>{NEW_CSS}</style>', html, flags=re.DOTALL)
print('✅ CSS replaced')

# ============================================================
# 2. PROFILE CARD: replace old avatar+name header HTML
# ============================================================
OLD_PROFILE_HEADER = '''    <div class="card">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <div id="profileAvatar" style="width:44px;height:44px;border-radius:50%;background:var(--bg3);border:2px solid var(--accent);display:flex;align-items:center;justify-content:center;font-size:20px">👤</div>
        <div>
          <div id="profileName" style="font-size:15px;font-weight:800"></div>
          <div id="profileTitle" style="font-size:11px;color:var(--accent);margin-top:1px"></div>
        </div>
      </div>
      <div class="stat-row"><span class="stat-label">💠 Уровень</span><span class="stat-value" id="pLevel">—</span></div>'''

NEW_PROFILE_HEADER = '''    <div class="card profile-hero">
      <div class="profile-hero-header">
        <div id="profileAvatar" class="profile-avatar">👤</div>
        <div class="profile-info">
          <div id="profileName" class="profile-name"></div>
          <div id="profileTitle" class="profile-title-line"></div>
          <div class="profile-level-pill">💠 <span id="pLevel">—</span></div>
        </div>
      </div>'''

if OLD_PROFILE_HEADER in html:
    html = html.replace(OLD_PROFILE_HEADER, NEW_PROFILE_HEADER)
    print('✅ Profile header restructured')
else:
    print('⚠️  Profile header not found – skipping')

# ============================================================
# 3. JS: Update avatar initialisation to not create inner div
# ============================================================
OLD_AVATAR_JS = '''    const avatarDiv = document.getElementById('profileAvatar');
    const _initials = (p.name||'').replace(/[^а-яёa-zA-Z]/gi,'').slice(0,2).toUpperCase() || '👤';
    avatarDiv.innerHTML = `<div style="width:52px;height:52px;border-radius:50%;background:var(--accent);border:2px solid var(--accent);display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:700;color:#fff">${_initials}</div>`;'''

NEW_AVATAR_JS = '''    const avatarDiv = document.getElementById('profileAvatar');
    const _initials = (p.name||'').replace(/[^а-яёa-zA-Z]/gi,'').slice(0,2).toUpperCase() || '👤';
    avatarDiv.textContent = _initials;'''

if OLD_AVATAR_JS in html:
    html = html.replace(OLD_AVATAR_JS, NEW_AVATAR_JS)
    print('✅ Avatar JS updated')
else:
    print('⚠️  Avatar JS not found – skipping')

# ============================================================
# 4. Write result
# ============================================================
with open(SRC, 'w', encoding='utf-8') as f:
    f.write(html)

print('🎉 All done! File written.')
