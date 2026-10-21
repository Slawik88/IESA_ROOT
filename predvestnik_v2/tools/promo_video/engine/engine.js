/* Движок промо-роликов: сценарий (JSON) → кадр в момент t.
 *
 * Всё положение элементов считается из t, без CSS-анимаций и таймеров: так любой кадр можно
 * отрисовать в любом порядке, а рендер (render.cjs) снимает их параллельно.
 * API для рендера: window.__load(scenario, baseUrl) → {duration, fps, cues}; window.__seek(t).
 */
(() => {
  "use strict";

  // ---------- утилиты ----------
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const lerp = (a, b, k) => a + (b - a) * k;
  const prog = (t, start, len) => clamp((t - start) / len);
  const easeOut = k => 1 - Math.pow(1 - k, 3);
  const easeInOut = k => (k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);
  const easeBack = k => { const c = 1.9; return 1 + (c + 1) * Math.pow(k - 1, 3) + c * Math.pow(k - 1, 2); };
  const rng = seed => () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
  const hash = s => { let h = 2166136261; for (const ch of String(s)) h = Math.imul(h ^ ch.codePointAt(0), 16777619); return h >>> 0; };
  const esc = s => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  // «*слово*» → акцент, «\n» → перенос
  const rich = s => esc(s).replace(/\*([^*]+)\*/g, '<span class="acc">$1</span>').replace(/\n/g, "<br>");
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const fmtNum = n => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");

  const AV_COLORS = [["#ff7a59", "#ff3d77"], ["#43c6ff", "#4c6fff"], ["#46e3a0", "#16a085"], ["#ffc93c", "#ff8a00"],
    ["#c56bff", "#7b3fe4"], ["#ff6fb5", "#c2185b"], ["#5ee7df", "#3a7bd5"]];
  const NAME_COLORS = ["#ff9d7a", "#7cc8ff", "#6ee7b0", "#ffd36b", "#d6a6ff", "#ff9fcf", "#8ff0ea"];
  const BOT = { name: "Предвестник", bot: true };

  // ---------- общее состояние ----------
  const S = { sc: null, base: "", list: [], total: 0, cur: -1, obj: null, people: {} };
  const stage = document.getElementById("stage");
  const sceneHost = document.getElementById("scenes");
  const flash = document.getElementById("flash");
  const blobs = [...document.querySelectorAll(".blob")];

  function person(name) {
    if (name === "bot") return BOT;
    const p = S.people[name] || {};
    const h = hash(name);
    return { name, emoji: p.emoji, tag: p.tag, colors: p.colors || AV_COLORS[h % AV_COLORS.length],
      nameColor: p.color || NAME_COLORS[h % NAME_COLORS.length] };
  }
  function avatar(p, cls = "") {
    if (p.bot) return el("div", `av av-bot ${cls}`, "П");
    const a = el("div", `av ${cls}`, p.emoji ? p.emoji : esc([...p.name][0]));
    a.style.background = `linear-gradient(135deg, ${p.colors[0]}, ${p.colors[1]})`;
    return a;
  }

  // Подпись сверху: показывается последняя с at ≤ t, новая «выпрыгивает».
  function captionTrack(root, list) {
    const items = (typeof list === "string" ? [{ at: 0, text: list }] : list || []).slice().sort((a, b) => a.at - b.at);
    const node = el("div", "cap"); root.appendChild(node);
    let shown = -1;
    return {
      cues: items.filter(c => c.at > .05).map(c => ({ t: c.at, s: "tick" })),
      update(t) {
        let idx = -1; items.forEach((c, i) => { if (c.at <= t) idx = i; });
        if (idx !== shown) { node.innerHTML = idx >= 0 ? rich(items[idx].text) : ""; shown = idx; }
        if (idx < 0) return;
        const k = items[idx].at <= 0 ? 1 : easeBack(prog(t, items[idx].at, .28));
        node.style.transform = `scale(${lerp(.55, 1, k)})`;
        node.style.opacity = clamp(k * 1.6);
      },
    };
  }

  // Эмодзи-салют: частицы летят от точки и падают.
  function burstLayer(root, bursts, anchorOf) {
    const parts = [];
    (bursts || []).forEach((b, bi) => {
      const r = rng(hash("burst" + bi + b.at));
      const emojis = Array.isArray(b.emoji) ? b.emoji : [b.emoji || "✨"];
      for (let i = 0; i < (b.count || 14); i++) {
        const node = el("div", "particle", emojis[i % emojis.length]);
        node.style.fontSize = `${Math.round(50 + r() * 50)}px`;
        node.style.opacity = 0; root.appendChild(node);
        const ang = -Math.PI / 2 + (r() - .5) * 2.4;
        const sp = 900 + r() * 900;
        parts.push({ node, b, vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp, rot: (r() - .5) * 720, delay: r() * .12 });
      }
    });
    return {
      cues: (bursts || []).map(b => ({ t: b.at, s: "sparkle" })),
      update(t) {
        for (const p of parts) {
          const lt = t - p.b.at - p.delay;
          if (lt < 0 || lt > 1.6) { p.node.style.opacity = 0; continue; }
          const [x0, y0] = anchorOf(p.b);
          const x = x0 + p.vx * lt, y = y0 + p.vy * lt + 1700 * lt * lt;
          p.node.style.opacity = clamp(1.6 - lt);
          p.node.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%) rotate(${p.rot * lt}deg) scale(${easeBack(prog(lt, 0, .25))})`;
        }
      },
    };
  }

  // Наезд камеры: ключевые кадры {at, scale, x, y}.
  function camera(keys) {
    const ks = (keys || []).slice().sort((a, b) => a.at - b.at);
    return t => {
      if (!ks.length) return "";
      let a = ks[0], b = ks[0];
      for (const k of ks) { if (k.at <= t) a = k; }
      b = ks.find(k => k.at > t) || a;
      const dur = b.dur || .45;
      const k = b === a ? 1 : easeInOut(prog(t, b.at - dur, dur));
      const v = key => lerp(a[key] ?? (key === "scale" ? 1 : 0), b[key] ?? (key === "scale" ? 1 : 0), k);
      return `translate(${v("x")}px, ${v("y")}px) scale(${v("scale")})`;
    };
  }

  // ---------- сцены ----------
  const TYPES = {};

  // Крючок: огромные строки «впечатываются», тряска, эмодзи.
  TYPES.hook = {
    mount(sc, root) {
      if (sc.ghost !== false) {
        const r = rng(hash("ghost" + (sc.lines || []).map(l => l.text).join()));
        for (let i = 0; i < 12; i++) {
          const g = el("div", "ghost");
          const right = r() > .55;
          g.style.width = `${300 + r() * 420}px`; g.style.height = `${80 + r() * 90}px`;
          g.style[right ? "right" : "left"] = `${40 + r() * 80}px`;
          g.dataset.y = 120 + i * 170 + r() * 40;
          root.appendChild(g);
        }
      }
      const wrap = el("div", "hook-wrap"); root.appendChild(wrap);
      const emoji = sc.emoji ? el("div", "hook-emoji", esc(sc.emoji)) : null;
      if (emoji) wrap.appendChild(emoji);
      const lines = (sc.lines || []).map(l => {
        const n = el("div", "hook-line" + (l.accent ? " accent" : ""), esc(l.text));
        n.style.fontSize = `${l.size || 150}px`; wrap.appendChild(n); return { n, l };
      });
      const sub = sc.sub ? el("div", "hook-sub", rich(sc.sub.text)) : null;
      if (sub) wrap.appendChild(sub);
      for (const { n } of lines) {   // строка обязана влезть в 980 px
        let fs = parseFloat(n.style.fontSize);
        while (n.scrollWidth > 980 && fs > 50) { fs -= 4; n.style.fontSize = `${fs}px`; }
      }
      const ghosts = [...root.querySelectorAll(".ghost")];
      const emojiAt = sc.emojiAt ?? 0;
      return {
        update(t) {
          ghosts.forEach((g, i) => { g.style.top = `${(+g.dataset.y - t * 60 * (1 + i % 3)) % 2000}px`; });
          let shake = 0;
          for (const { n, l } of lines) {
            const at = l.at || 0;
            if (at <= 0) { n.style.opacity = 1; n.style.transform = `scale(${lerp(1.06, 1, easeOut(prog(t, 0, .5)))})`; continue; }
            const k = easeOut(prog(t, at, .2));
            n.style.opacity = t < at ? 0 : 1;
            n.style.transform = `scale(${lerp(2.3, 1, k)})`;
            if (t >= at) shake = Math.max(shake, Math.max(0, 1 - (t - at) / .35));
          }
          if (emoji) {
            const k = emojiAt <= 0 ? 1 : easeBack(prog(t, emojiAt, .35));
            emoji.style.opacity = t < emojiAt ? 0 : 1;
            emoji.style.transform = `scale(${k}) rotate(${Math.sin(t * 5) * 6}deg) translateY(${Math.sin(t * 3.2) * 10}px)`;
          }
          if (sub) {
            const k = easeOut(prog(t, sc.sub.at || 0, .3));
            sub.style.opacity = k; sub.style.transform = `translateY(${(1 - k) * 40}px)`;
          }
          const r = rng(Math.floor(t * 30));
          const a = 26 * shake * shake;
          wrap.style.transform = `translate(${(r() - .5) * a}px, ${(r() - .5) * a}px) scale(${1 + t * .015})`;
        },
      };
    },
    cues(sc) {
      const out = [];
      (sc.lines || []).forEach((l, i) => out.push({ t: l.at || 0, s: i === 0 ? "boom" : "hit" }));
      if (sc.emoji) out.push({ t: sc.emojiAt || 0, s: "pop" });
      if (sc.sub) out.push({ t: sc.sub.at || 0, s: "tick" });
      return out;
    },
  };

  // Переписка в группе Telegram.
  TYPES.chat = {
    mount(sc, root) {
      const cap = captionTrack(root, sc.caption);
      const win = el("div", "tg"); root.appendChild(win);
      win.appendChild(el("div", "tg-wall"));
      const head = el("div", "tg-head");
      head.appendChild(el("div", "tg-back", "‹"));
      const gav = avatar({ name: sc.title || "Чат", emoji: sc.chatEmoji || "💬", colors: ["#a855ff", "#ff5fa8"] }, "av-group");
      head.appendChild(gav);
      const htxt = el("div"); htxt.appendChild(el("div", "tg-title", esc(sc.title || "Флудилка")));
      const hsub = el("div", "tg-sub", esc(sc.members || "1 284 участника")); htxt.appendChild(hsub);
      head.appendChild(htxt); win.appendChild(head);
      const body = el("div", "tg-body"); win.appendChild(body);
      const list = el("div", "tg-list"); body.appendChild(list);
      const input = el("div", "tg-input");
      input.appendChild(el("div", "tg-send", "☺"));
      const field = el("div", "tg-field", "Сообщение"); input.appendChild(field);
      const send = el("div", "tg-send", "➤"); input.appendChild(send);
      win.appendChild(input);

      const msgs = (sc.messages || []).map((m, i, arr) => {
        const prev = arr[i - 1];
        const first = !prev || prev.from !== m.from || prev.me !== m.me || prev.from === "service";
        let node;
        if (m.from === "service") {
          node = el("div", "svc"); node.appendChild(el("span", null, rich(m.text)));
        } else {
          const p = m.me ? null : person(m.from);
          node = el("div", "msg" + (m.me ? " me" : "") + (p && p.bot ? " bot" : ""));
          if (!m.me) node.appendChild(first ? avatar(p) : el("div", "spacer"));
          const bub = el("div", "bubble");
          if (!m.me && first) {
            const nm = el("div", "name", esc(p.name) + (p.tag ? `<span class="tag">${esc(p.tag)}</span>` : ""));
            nm.style.color = p.bot ? "#c9a6ff" : p.nameColor; bub.appendChild(nm);
          }
          if (m.reply) {
            const rp = person(m.reply.from);
            const q = el("div", "reply", `<b>${esc(rp.name)}</b><span>${esc(m.reply.text)}</span>`);
            q.style.borderColor = q.firstChild.style.color = rp.bot ? "#c9a6ff" : rp.nameColor;
            bub.appendChild(q);
          }
          if (m.card) bub.appendChild(activityCard(m.card, i));
          const txt = m.html != null ? m.html : esc(m.text).replace(/(@[\wА-Яа-яЁё]+)/g, '<span class="mention">$1</span>');
          if (txt) bub.appendChild(el("div", "txt", txt));
          if (m.buttons) {
            const kb = el("div", "kb");
            m.buttons.forEach(row => { const r = el("div", "kb-row"); row.forEach(b => r.appendChild(el("div", "btn", esc(b)))); kb.appendChild(r); });
            bub.appendChild(kb);
          }
          if (m.react) {
            const rs = el("div", "reacts");
            m.react.items.forEach(([e]) => rs.appendChild(el("div", "react", esc(e))));
            bub.appendChild(rs);
          }
          node.appendChild(bub);
          if (m.react) node.style.paddingBottom = "34px";
        }
        list.appendChild(node);
        return { m, node };
      });
      // замер после вёрстки: шрифты уже загружены в __load
      msgs.forEach(x => { x.top = x.node.offsetTop; x.h = x.node.offsetHeight; });
      const viewH = body.clientHeight;
      const cam = camera(sc.camera);
      const finger = el("div", "finger", "👆"); finger.style.opacity = 0; root.appendChild(finger);
      const bursts = burstLayer(root, sc.bursts, b => {
        if (Array.isArray(b.from)) return b.from;
        const x = msgs[b.from ?? msgs.length - 1];
        const r = x.node.querySelector(".bubble, span").getBoundingClientRect();
        return [r.left + r.width / 2, r.top + r.height / 2];
      });
      const typers = msgs.map((x, i) => {
        if (x.m.me || x.m.from === "service") return null;
        const prevAt = i ? msgs[i - 1].m.at : -1;
        const len = Math.min(x.m.from === "bot" ? .75 : .55, x.m.at - prevAt - .08);
        return len > .15 ? { from: x.m.at - len, to: x.m.at, who: person(x.m.from).name } : null;
      });
      const grayUntil = sc.grayUntil || 0;

      return {
        update(t) {
          cap.update(t);
          let last = -1;
          msgs.forEach((x, i) => { if (x.m.at <= t) last = i; });
          msgs.forEach((x, i) => {
            if (i > last) { x.node.style.opacity = 0; return; }
            const k = prog(t, x.m.at, .3);
            x.node.style.opacity = clamp(k * 2.5);
            x.node.style.transform = k < 1 ? `translateY(${(1 - easeOut(k)) * 40}px) scale(${lerp(.82, 1, easeBack(k))})` : "";
            if (x.m.react) {
              const rs = x.node.querySelectorAll(".react");
              x.m.react.items.forEach(([e, n], j) => {
                const rk = prog(t, x.m.react.at + j * .12, .3);
                rs[j].style.opacity = rk > 0 ? 1 : 0;
                rs[j].style.transform = `scale(${easeBack(rk)})`;
                rs[j].textContent = `${e} ${Math.max(1, Math.round(lerp(1, n || 1, easeOut(prog(t, x.m.react.at + j * .12, .9)))))}`;
              });
            }
            const card = x.node.querySelector(".acard");
            if (card) card._update(t - x.m.at);
          });
          // прокрутка: низ последнего сообщения прижат к полю ввода
          let bottom = 0;
          if (last >= 0) {
            const cur = msgs[last], prev = msgs[last - 1];
            const prevBottom = prev ? prev.top + prev.h : 0;
            bottom = lerp(prevBottom, cur.top + cur.h, easeOut(prog(t, cur.m.at, .3)));
          }
          list.style.transform = `translateY(${viewH - bottom - 18}px)`;

          // «печатает…» в шапке
          const typing = typers.find(y => y && t >= y.from && t < y.to);
          if (typing) {
            hsub.className = "tg-sub typing";
            hsub.textContent = `${typing.who} печатает` + ".".repeat(1 + Math.floor(t * 4) % 3);
          } else { hsub.className = "tg-sub"; hsub.textContent = sc.members || "1 284 участника"; }

          // набор текста в поле ввода для своих сообщений
          const typed = msgs.find(x => x.m.me && x.m.typed && t >= x.m.at - x.m.typed && t < x.m.at);
          if (typed) {
            const s = [...typed.m.text];
            const n = Math.ceil(s.length * prog(t, typed.m.at - typed.m.typed, typed.m.typed * .85));
            field.className = "tg-field has"; field.innerHTML = esc(s.slice(0, n).join("")) + '<span class="caret"></span>';
            send.className = "tg-send on";
          } else { field.className = "tg-field"; field.textContent = "Сообщение"; send.className = "tg-send"; }

          // нажатие на кнопку: палец, вспышка, рябь
          finger.style.opacity = 0;
          msgs.forEach(x => {
            const pr = x.m.press;
            if (!pr || t < pr.at - .5 || t > pr.at + .6) {
              x.node.querySelectorAll(".btn").forEach(b => { b.style.transform = ""; b.style.background = ""; });
              x.node.querySelectorAll(".ripple").forEach(r => r.remove());
              return;
            }
            const btn = x.node.querySelectorAll(".kb-row")[pr.row || 0].children[pr.col || 0];
            const r = btn.getBoundingClientRect();
            const appear = easeOut(prog(t, pr.at - .5, .35));
            const tap = t >= pr.at ? Math.max(0, 1 - (t - pr.at) / .25) : 0;
            finger.style.opacity = t > pr.at + .45 ? clamp(1 - (t - pr.at - .45) / .15) : appear;
            finger.style.left = `${r.left + r.width / 2 - 40}px`;
            finger.style.top = `${r.top + r.height / 2 - 10 + (1 - appear) * 160}px`;
            finger.style.transform = `scale(${1 - tap * .15})`;
            btn.style.transform = `scale(${1 - tap * .06})`;
            btn.style.background = t >= pr.at && t < pr.at + .5 ? "rgba(168,85,255,.75)" : "";
            let rip = btn.querySelector(".ripple");
            if (t >= pr.at) {
              if (!rip) { rip = el("div", "ripple"); btn.appendChild(rip); }
              const rk = prog(t, pr.at, .45);
              rip.style.left = `${r.width / 2 - 20}px`; rip.style.top = `${r.height / 2 - 20}px`;
              rip.style.transform = `scale(${rk * 14})`; rip.style.opacity = 1 - rk;
            } else if (rip) rip.remove();
          });

          // «до/после»: серый мёртвый чат, потом цвет
          if (grayUntil) {
            const k = easeOut(prog(t, grayUntil, .45));
            win.style.filter = k >= 1 ? "" : `grayscale(${1 - k}) brightness(${lerp(.62, 1, k)})`;
          }
          win.style.transform = cam(t);
          bursts.update(t);
        },
      };
    },
    cues(sc) {
      const out = [];
      (sc.messages || []).forEach(m => {
        out.push({ t: m.at, s: m.from === "service" ? "tick" : m.me ? "send" : m.from === "bot" ? "ding" : "pop" });
        if (m.press) out.push({ t: m.press.at, s: "click" });
        if (m.react) m.react.items.forEach((_, j) => out.push({ t: m.react.at + j * .12, s: "pop", v: .5 }));
        if (m.me && m.typed) for (let k = m.at - m.typed; k < m.at - .1; k += .09) out.push({ t: k, s: "key", v: .5 });
      });
      (sc.bursts || []).forEach(b => out.push({ t: b.at, s: "sparkle" }));
      if (sc.grayUntil) out.push({ t: sc.grayUntil, s: "boom" });
      const caps = typeof sc.caption === "string" ? [] : (sc.caption || []);
      caps.forEach(c => { if (c.at > .05) out.push({ t: c.at, s: "tick" }); });
      return out;
    },
  };

  // Карточка активности в сообщении (как «бот я» со скином).
  function activityCard(c, seedIdx) {
    const node = el("div", "acard");
    const tiers = { S: ["rgba(255,95,168,.55)", "#ffb3d9"], SS: ["rgba(76,111,255,.65)", "#a9bbff"], SSS: ["rgba(168,85,255,.9)", "#e9a8ff"] };
    const [frameColor, badge] = tiers[c.tier || "S"] || tiers.S;
    node.innerHTML = `<div class="frame" style="border-color:${frameColor}"></div>
      <div class="t1">${esc(c.title || "Странник Предвестника")}</div><div class="t2">${esc(c.subtitle || "Повелитель Лепестков")}</div>
      <div class="tier" style="background:${badge}">${esc(c.tier || "S")}</div>
      <div class="lbl">${esc(fmtNum(c.total || 2139))} сообщений · 30 дней</div><div class="num">0</div><div class="bars"></div>`;
    const bars = node.querySelector(".bars"), num = node.querySelector(".num");
    const r = rng(hash("card" + seedIdx));
    const hs = Array.from({ length: 30 }, (_, i) => i === 29 ? .72 : .15 + r() * .85);
    const els = hs.map((h, i) => { const b = el("div", "bar" + (i === 29 ? " today" : "")); b.style.height = `${h * 100}%`; bars.appendChild(b); return b; });
    node._update = lt => {
      els.forEach((b, i) => { b.style.transform = `scaleY(${easeOut(prog(lt, .15 + i * .018, .45))})`; });
      num.textContent = fmtNum((c.today || 89) * easeOut(prog(lt, .2, 1)));
    };
    node._update(0);
    return node;
  }

  // Сетка фич: плитки вылетают по очереди.
  TYPES.grid = {
    mount(sc, root) {
      const cap = captionTrack(root, sc.caption);
      const cols = sc.cols || 2;
      const grid = el("div", "grid"); grid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`; root.appendChild(grid);
      const step = sc.interval || .16, start = sc.delay ?? .25;
      const tiles = (sc.items || []).map((it, i) => {
        const tile = el("div", "tile", `<div class="e">${esc(it.emoji)}</div><div class="h">${rich(it.title)}</div>${it.sub ? `<div class="s">${rich(it.sub)}</div>` : ""}<div class="shine"></div>`);
        grid.appendChild(tile);
        return { tile, at: start + i * step, shine: tile.querySelector(".shine") };
      });
      const r = rng(hash("grid" + (sc.items || []).length));
      const rots = tiles.map(() => (r() - .5) * 16);
      return {
        update(t) {
          cap.update(t);
          tiles.forEach((x, i) => {
            const k = prog(t, x.at, .32);
            x.tile.style.opacity = clamp(k * 3);
            x.tile.style.transform = `translateY(${(1 - easeOut(k)) * 120}px) scale(${lerp(.5, 1, easeBack(k))}) rotate(${rots[i] * (1 - easeOut(k))}deg)`;
            x.shine.style.left = `${lerp(-200, 700, prog(t, x.at + .25, .6))}px`;
          });
          grid.style.transform = `translateY(${-t * 6}px)`;
        },
      };
    },
    cues(sc) {
      const step = sc.interval || .16, start = sc.delay ?? .25;
      return (sc.items || []).map((_, i) => ({ t: start + i * step, s: "pop", v: .7 }));
    },
  };

  // Большая цифра + облако примеров вокруг.
  TYPES.stat = {
    mount(sc, root) {
      const cap = captionTrack(root, sc.caption);
      const num = el("div", "stat-num"); root.appendChild(num);
      const label = el("div", "stat-label", rich(sc.label || "")); root.appendChild(label);
      const r = rng(hash("stat" + sc.value));
      // места вокруг цифры: полоса над ней и поле под подписью (подпись сверху и цифру не закрывают)
      const SLOTS = [[230, 520], [560, 470], [860, 540], [200, 1200], [540, 1170], [880, 1220], [300, 1340], [740, 1350],
        [180, 1470], [520, 1480], [880, 1460], [380, 590]];
      const chips = (sc.chips || []).slice(0, SLOTS.length).map((c, i) => {
        const node = el("div", "chip", esc(c)); root.appendChild(node);
        return { node, slot: SLOTS[i], ph: r() * 6, at: .5 + i * .09 };
      });
      chips.forEach(c => { c.w = c.node.offsetWidth; c.h = c.node.offsetHeight;
        c.slot = [clamp(c.slot[0], c.w / 2 + 30, 1050 - c.w / 2), c.slot[1]]; });
      const countLen = sc.countLen || 1;
      return {
        update(t) {
          cap.update(t);
          const k = easeOut(prog(t, .1, countLen));
          num.textContent = fmtNum(sc.value * k) + (sc.suffix || "");
          num.style.transform = `scale(${1 + (t >= .1 + countLen ? Math.max(0, 1 - (t - .1 - countLen) / .3) * .12 : 0)})`;
          label.style.opacity = easeOut(prog(t, .3, .3));
          chips.forEach(c => {
            const x = c.slot[0] + Math.sin(t * 1.4 + c.ph) * 14, y = c.slot[1] + Math.cos(t * 1.1 + c.ph) * 12;
            const ck = prog(t, c.at, .3);
            c.node.style.opacity = clamp(ck * 3);
            c.node.style.transform = `translate(${x - c.w / 2}px, ${y - c.h / 2}px) scale(${easeBack(ck)})`;
          });
        },
      };
    },
    cues(sc) {
      const out = [];
      const len = sc.countLen || 1;
      for (let k = .1; k < .1 + len; k += .07) out.push({ t: k, s: "key", v: .45 });
      out.push({ t: .1 + len, s: "hit" });
      (sc.chips || []).forEach((_, i) => out.push({ t: .5 + i * .09, s: "pop", v: .35 }));
      return out;
    },
  };

  // Мини-приложение: телефон, страницы листаются.
  const NAV = { rhythm: "🎮", pass: "🎟", pets: "🐾", skins: "🎨", family: "🌳" };
  TYPES.app = {
    mount(sc, root) {
      const cap = captionTrack(root, sc.caption);
      const phone = el("div", "phone"); root.appendChild(phone);
      const screen = el("div", "screen"); phone.appendChild(screen);
      screen.appendChild(el("div", "app-top", "Предвестник"));
      const pagesEl = el("div", "pages"); screen.appendChild(pagesEl);
      const nav = el("div", "app-nav"); screen.appendChild(nav);
      const pages = sc.pages || [];
      const navKeys = ["rhythm", "pass", "pets", "skins", "family"];
      const navEls = navKeys.map(k => { const d = el("div", null, NAV[k]); nav.appendChild(d); return d; });
      const per = (sc.dur - .2) / Math.max(1, pages.length);
      const built = pages.map((p, i) => {
        const node = el("div", "page", `<div class="ph">${rich(p.title)}</div><div class="ps">${rich(p.sub || "")}</div>`);
        pagesEl.appendChild(node);
        return { node, p, upd: PAGE[p.kind] ? PAGE[p.kind](node, i) : () => {}, at: i * per };
      });
      return {
        update(t) {
          cap.update(t);
          let pos = 0;
          built.forEach((b, i) => { if (i > 0) pos += easeInOut(prog(t, b.at - .3, .35)); });
          const cur = Math.round(pos);
          built.forEach((b, i) => {
            b.node.style.transform = `translateX(${(i - pos) * 708}px)`;
            b.node.style.visibility = Math.abs(i - pos) < 1 ? "visible" : "hidden";
            if (Math.abs(i - pos) < 1) b.upd(t - b.at + .3);
          });
          navEls.forEach((n, j) => n.className = built[cur] && navKeys[j] === built[cur].p.kind ? "on" : "");
          phone.style.transform = `translateY(${(1 - easeOut(prog(t, 0, .4))) * 160}px) rotate(${Math.sin(t * 1.3) * .8}deg)`;
        },
      };
    },
    cues(sc) {
      const per = (sc.dur - .2) / Math.max(1, (sc.pages || []).length);
      return (sc.pages || []).slice(1).map((_, i) => ({ t: (i + 1) * per - .3, s: "whoosh", v: .6 }));
    },
  };

  // Наполнение страниц мини-приложения.
  const PAGE = {
    rhythm(node) {
      const xs = [120, 314, 508];
      xs.forEach(x => { const l = el("div", "lane"); l.style.left = `${x - 85 + 20}px`; node.appendChild(l); });
      node.appendChild(el("div", "hitline"));
      const combo = el("div", "combo"); node.appendChild(combo);
      const r = rng(7);
      const colors = [["#ff5fa8", "#ff9fcf"], ["#a855ff", "#d6a6ff"], ["#4c6fff", "#9fb3ff"]];
      const runes = Array.from({ length: 26 }, (_, i) => {
        const lane = Math.floor(r() * 3);
        const n = el("div", "rune"); n.style.left = `${xs[lane] + 20}px`;
        n.style.background = `linear-gradient(135deg, ${colors[lane][0]}, ${colors[lane][1]})`;
        n.style.boxShadow = `0 0 30px ${colors[lane][0]}`;
        node.appendChild(n); return { n, spawn: i * .14 - .6 };
      });
      return t => {
        let hits = 0;
        runes.forEach(x => {
          const y = 230 + (t - x.spawn) * 620;
          if (y > 684) hits++;
          const after = y - 684;
          x.n.style.top = `${Math.min(y, 684)}px`;
          x.n.style.opacity = y < 230 ? 0 : after > 0 ? clamp(1 - after / 90) : 1;
          x.n.style.transform = `rotate(45deg) scale(${after > 0 ? 1 + after / 60 : 1})`;
        });
        combo.innerHTML = `КОМБО <span class="acc">×${hits}</span>`;
      };
    },
    pass(node) {
      const wrap = el("div", null, `<div style="margin-top:60px;font-size:34px;font-weight:800">Уровень <span class="lvl">8</span> / 30</div>`);
      const bar = el("div", "pbar"); bar.style.marginTop = "18px"; const fill = el("div"); bar.appendChild(fill); wrap.appendChild(bar);
      const cells = el("div", "cells");
      const items = [["🎁", "сундук"], ["💎", "алмазы"], ["🎨", "образ"], ["🪙", "мора"], ["🐾", "питомец"], ["✨", "рамка"]];
      const cs = items.map(([e, s]) => { const c = el("div", "cell", `<span>${e}</span><small>${s}</small>`); cells.appendChild(c); return c; });
      wrap.appendChild(cells); node.appendChild(wrap);
      const lvl = wrap.querySelector(".lvl");
      return t => {
        const k = easeOut(prog(t, .2, 1.2));
        lvl.textContent = Math.round(lerp(8, 14, k));
        fill.style.width = `${lerp(8, 14, k) / 30 * 100}%`;
        cs.forEach((c, i) => {
          const ck = prog(t, .3 + i * .16, .3);
          c.style.transform = `scale(${lerp(.7, 1, easeBack(ck))})`;
          c.style.opacity = lerp(.25, 1, ck);
          c.style.borderColor = ck >= 1 ? "rgba(255,95,168,.6)" : "";
        });
      };
    },
    pets(node) {
      const pets = [["🦊", "Искра", "Поход · 2 ч"], ["🐉", "Пиксель", "Поход · 6 ч"], ["🦉", "Ухта", "Поход · 12 ч"]];
      const rows = pets.map(([e, n, r]) => {
        const row = el("div", "pet", `<div class="pe">${e}</div><div style="flex:1"><div class="pn">${n}<span class="done" style="opacity:0">+ находка</span></div><div class="pr">${r}</div><div class="pbar"><div></div></div></div>`);
        node.appendChild(row); return row;
      });
      node.querySelector(".ps").insertAdjacentHTML("afterend", '<div style="height:20px"></div>');
      return t => rows.forEach((row, i) => {
        const k = easeInOut(prog(t, .1 + i * .2, .9));
        row.querySelector(".pbar > div").style.width = `${k * 100}%`;
        const d = row.querySelector(".done"); const dk = prog(t, 1 + i * .2, .25);
        d.style.opacity = dk; d.style.transform = `scale(${easeBack(dk)})`;
        row.style.transform = `translateX(${(1 - easeOut(prog(t, i * .1, .35))) * 300}px)`;
      });
    },
    skins(node, i) {
      const holder = el("div"); holder.style.cssText = "margin-top:50px;transform-origin:0 0;transform:scale(.89)"; node.appendChild(holder);
      const tiers = ["S", "SS", "SSS"];
      const cards = tiers.map((tier, j) => { const c = activityCard({ tier, title: "Странник", subtitle: ["Лепестковый Вихрь", "Ледяной Шёпот", "Бездна"][j] }, 40 + j); c.style.position = "absolute"; holder.appendChild(c); return c; });
      return t => {
        const cur = Math.min(2, Math.floor(t / .8));
        cards.forEach((c, j) => {
          c.style.opacity = j === cur ? 1 : 0;
          c.style.transform = j === cur ? `scale(${lerp(.9, 1, easeBack(prog(t, j * .8, .3)))})` : "";
          c._update(t - j * .8 + .5);
        });
      };
    },
    family(node) {
      const tree = el("div", null, `<blockquote style="margin-top:50px;font-size:34px;line-height:1.6;border-left:6px solid #a855ff;padding:14px 24px;background:rgba(168,85,255,.1);border-radius:14px">
        👑 Бабушка Ира 💍 Дед Саня<br>&nbsp;&nbsp;└ 🧑 Лиза 💍 Марк<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ 🧒 Кира<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ 🧒 Тёма</blockquote>
        <div style="margin-top:30px;font-size:32px;font-weight:800">💰 Кошелёк семьи: <span class="acc">12 400</span></div>`);
      node.appendChild(tree);
      return t => { tree.style.opacity = easeOut(prog(t, .1, .4)); tree.style.transform = `translateY(${(1 - easeOut(prog(t, .1, .4))) * 60}px)`; };
    },
  };

  // Готовая картинка (скриншот) в телефоне.
  TYPES.image = {
    mount(sc, root) {
      const cap = captionTrack(root, sc.caption);
      const phone = el("div", "phone"); root.appendChild(phone);
      const screen = el("div", "screen"); phone.appendChild(screen);
      const shot = el("div", "shot"); shot.style.backgroundImage = `url("${new URL(sc.src, S.base).href}")`; screen.appendChild(shot);
      const img = new Image(); img.src = new URL(sc.src, S.base).href;
      return {
        ready: img.decode().catch(() => {}),
        update(t) {
          cap.update(t);
          shot.style.transform = `scale(${1 + t * .025})`;
          shot.style.backgroundPosition = `50% ${Math.min(100, t * (sc.pan || 0))}%`;
          phone.style.transform = `translateY(${(1 - easeOut(prog(t, 0, .4))) * 160}px)`;
        },
      };
    },
    cues() { return []; },
  };

  // Финал: аватар, @ник, кнопка «добавить».
  TYPES.cta = {
    mount(sc, root) {
      const rings = [0, 1, 2].map(() => { const r = el("div", "cta-ring"); root.appendChild(r); return r; });
      const av = avatar(BOT, "cta-av"); root.appendChild(av);
      const name = el("div", "cta-name", rich(sc.title || "Предвестник")); root.appendChild(name);
      const handle = el("div", "cta-handle", `<span>${esc(sc.handle || "@IIIPredvestnikIIIBot")}</span>`); root.appendChild(handle);
      const btn = el("div", "cta-btn", rich(sc.button || "➕ Добавить в чат")); root.appendChild(btn);
      const sub = el("div", "cta-sub", rich(sc.sub || "бесплатно · в любую группу")); root.appendChild(sub);
      const cap = captionTrack(root, sc.caption);
      const finger = el("div", "finger", "👆"); root.appendChild(finger);
      return {
        update(t) {
          cap.update(t);
          rings.forEach((r, i) => {
            const k = ((t + i * .55) % 1.65) / 1.65;
            const d = lerp(300, 820, k);
            r.style.width = r.style.height = `${d}px`; r.style.marginLeft = r.style.marginTop = `${-d / 2}px`;
            r.style.opacity = (1 - k) * .8;
          });
          av.style.transform = `scale(${easeBack(prog(t, 0, .4)) * (1 + Math.sin(t * 6) * .025)})`;
          const show = (n, at) => { const k = easeOut(prog(t, at, .3)); n.style.opacity = k; return k; };
          const nk = show(name, .15); name.style.transform = `translateY(${(1 - nk) * 50}px)`;
          const hk = show(handle, .3); handle.style.transform = `translateX(-50%) scale(${lerp(.6, 1, easeBack(prog(t, .3, .35)))})`;
          const bk = show(btn, .55);
          const tapT = (t - 1.1) % 1.2;
          const tap = t > 1.1 && tapT < .25 ? 1 - tapT / .25 : 0;
          btn.style.transform = `translateY(${(1 - bk) * 60}px) scale(${(1 + Math.sin(t * 7) * .02) * (1 - tap * .06)})`;
          show(sub, .8);
          finger.style.opacity = easeOut(prog(t, .9, .3));
          finger.style.left = "830px"; finger.style.top = `${1265 + (1 - easeOut(prog(t, .9, .3))) * 200 + tap * -20}px`;
          finger.style.transform = `scale(${1 - tap * .15})`;
          void hk;
        },
      };
    },
    cues(sc) {
      const out = [{ t: 0, s: "boom" }, { t: .3, s: "ding" }];
      for (let k = 1.1; k < sc.dur; k += 1.2) out.push({ t: k, s: "click" });
      return out;
    },
  };

  // ---------- таймлайн ----------
  function updateBackground(t) {
    const pal = S.sc.palette || ["#7b3fe4", "#ff5fa8", "#3a4cff"];
    blobs.forEach((b, i) => {
      b.style.background = pal[i % pal.length];
      const x = 540 + Math.cos(t * .35 + i * 2.1) * 420 - 450;
      const y = 900 + Math.sin(t * .28 + i * 1.7) * 700 - 450;
      b.style.transform = `translate(${x}px, ${y}px)`;
    });
  }

  async function mountScene(i) {
    sceneHost.innerHTML = "";
    const sc = S.list[i];
    const root = el("div", "scene"); sceneHost.appendChild(root);
    S.obj = TYPES[sc.type].mount(sc, root);
    S.obj.root = root;
    S.cur = i;
    if (S.obj.ready) await S.obj.ready;
  }

  window.__seek = async t => {
    t = clamp(t, 0, S.total - 1e-4);
    let i = S.list.findIndex(s => t >= s.start && t < s.start + s.dur);
    if (i < 0) i = S.list.length - 1;
    if (i !== S.cur) await mountScene(i);
    const sc = S.list[i], lt = t - sc.start;
    updateBackground(t);
    S.obj.update(lt);
    // переход между сценами: короткая вспышка и «удар» масштабом
    const k = i > 0 ? prog(lt, 0, .22) : 1;
    flash.style.opacity = (1 - k) * .28;
    if (k < 1) S.obj.root.style.transform = `scale(${lerp(1.08, 1, easeOut(k))})`;
    else S.obj.root.style.transform = "";
  };

  window.__load = async (scenario, base) => {
    S.sc = scenario; S.base = base || location.href; S.people = scenario.people || {};
    let at = 0;
    S.list = scenario.scenes.map((s, i, arr) => {
      const x = { ...s, start: at }; at += s.dur;
      // чат продолжается: хвост переписки прошлой сцены уже на экране (выключить: "carry": false)
      const prev = arr[i - 1];
      if (s.type === "chat" && s.carry !== false && prev && prev.type === "chat" && prev.title === s.title) {
        const tail = prev.messages.slice(-6).map((m, j) => {
          const { press, typed, ...rest } = m;
          return { ...rest, at: -10 + j * .01, react: m.react && { ...m.react, at: -9 } };
        });
        x.messages = [...tail, ...s.messages];
        x.bursts = (s.bursts || []).map(b => (typeof b.from === "number" ? { ...b, from: b.from + tail.length } : b));
      }
      return x;
    });
    S.total = at; S.cur = -1;
    const probes = ["400", "600", "700", "800", "900"].map(w => document.fonts.load(`${w} 40px Inter`, "Аa"));
    probes.push(document.fonts.load('40px "Noto Color Emoji"', "😀"), document.fonts.load('40px "JetBrains Mono"', "a"));
    await Promise.all(probes.map(p => p.catch(() => {})));
    const cues = [];
    S.list.forEach((s, i) => {
      if (i > 0) cues.push({ t: s.start, s: "whoosh" });
      for (const c of TYPES[s.type].cues(s)) if (c.t >= 0 && c.t < s.dur) cues.push({ ...c, t: s.start + c.t });
    });
    cues.sort((a, b) => a.t - b.t);
    return { duration: S.total, fps: scenario.fps || 30, cues, scenes: S.list.map(s => ({ type: s.type, start: s.start, dur: s.dur })) };
  };

  // Предпросмотр в браузере: index.html?s=../scenarios/01-dead-chat.json (через любой http-сервер)
  const q = new URLSearchParams(location.search).get("s");
  if (q) {
    fetch(q).then(r => r.json()).then(async sc => {
      const info = await window.__load(sc, new URL(q, location.href).href);
      document.body.style.transformOrigin = "0 0";
      const fit = () => { document.body.style.transform = `scale(${Math.min(innerWidth / 1080, innerHeight / 1920)})`; };
      fit(); addEventListener("resize", fit);
      let t0 = performance.now();
      const loop = async () => { await window.__seek(((performance.now() - t0) / 1000) % info.duration); requestAnimationFrame(loop); };
      document.addEventListener("click", () => { t0 = performance.now(); });
      loop();
    });
  }
})();
