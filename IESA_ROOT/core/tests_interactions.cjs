/* Behaviour regressions for touch gestures and asynchronous overlays.
 * Run: node --test IESA_ROOT/core/tests_interactions.cjs
 * IESA_BASE_REF optionally runs the same scenarios against a Git revision.
 * This isolated event harness tests handlers, not real iOS touch physics.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { execFileSync } = require("node:child_process");
const root = path.resolve(__dirname, "..");
function source(name) {
  return process.env.IESA_BASE_REF
    ? execFileSync(
        "git",
        ["show", `${process.env.IESA_BASE_REF}:IESA_ROOT/${name}`],
        { cwd: root, encoding: "utf8" },
      )
    : fs.readFileSync(path.join(root, name), "utf8");
}
function inline(name, marker) {
  return [...source(name).matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)]
    .map((m) => m[1])
    .find((s) => s.includes(marker));
}
class Element {
  constructor(id = "") {
    this.id = id;
    this.style = { setProperty() {} };
    this.dataset = {};
    this.listeners = {};
    this.attributes = {};
    this.children = [];
    this.classes = new Set();
    this.scrollTop = 0;
    this.offsetParent = {};
    this.classList = {
      add: (...xs) => xs.forEach((x) => this.classes.add(x)),
      remove: (...xs) => xs.forEach((x) => this.classes.delete(x)),
      contains: (x) => this.classes.has(x),
      toggle: (x, on = !this.classes.has(x)) =>
        on ? this.classes.add(x) : this.classes.delete(x),
    };
  }
  addEventListener(type, callback) {
    (this.listeners[type] ||= []).push(callback);
  }
  emit(type, event = {}) {
    for (const callback of this.listeners[type] || [])
      callback({ target: this, preventDefault() {}, ...event });
  }
  setAttribute(k, v) {
    this.attributes[k] = v;
  }
  getAttribute(k) {
    return this.attributes[k] ?? null;
  }
  removeAttribute(k) {
    delete this.attributes[k];
  }
  querySelector() {
    return null;
  }
  querySelectorAll() {
    return [];
  }
  matches() {
    return false;
  }
  closest() {
    return null;
  }
  contains(e) {
    return e === this || this.children.includes(e);
  }
  appendChild(e) {
    this.children.push(e);
  }
  focus() {
    this.focused = true;
  }
  getBoundingClientRect() {
    return { top: 0, bottom: 20 };
  }
}
function harness() {
  const document = new Element(),
    body = new Element(),
    win = new Element();
  const nodes = new Map();
  let serial = 0;
  const timers = new Map(),
    frames = [];
  document.body = body;
  document.head = new Element();
  document.documentElement = new Element();
  document.readyState = "loading";
  document.activeElement = new Element("trigger");
  document.getElementById = (id) => nodes.get(id) || null;
  document.createElement = () => new Element();
  const collapse = {
    hides: 0,
    hide() {
      this.hides++;
      nodes.get("iesa-nav-collapse")?.classList.remove("show");
    },
  };
  const modal = {
    opens: 0,
    show() {
      this.opens++;
      nodes.get("galleryModal").emit("show.bs.modal");
    },
  };
  Object.assign(win, {
    innerWidth: 390,
    innerHeight: 640,
    scrollY: 0,
    matchMedia: () => ({ matches: false }),
    location: { pathname: "/blog/29/" },
    navigator: { standalone: true },
    scrollTo() {
      this.scrollCalls = (this.scrollCalls || 0) + 1;
    },
  });
  const history = {
    length: 2,
    calls: 0,
    back() {
      this.calls++;
    },
  };
  const globals = {
    window: win,
    document,
    navigator: win.navigator,
    history,
    bootstrap: {
      Collapse: {
        getOrCreateInstance: () => collapse,
        getInstance: () => collapse,
      },
      Modal: { getOrCreateInstance: () => modal },
    },
    htmx: {},
    console,
    setTimeout: (cb) => {
      const id = ++serial;
      timers.set(id, cb);
      return id;
    },
    clearTimeout: (id) => timers.delete(id),
    requestAnimationFrame: (cb) => frames.push(cb),
  };
  const context = vm.createContext(globals);
  return {
    document,
    body,
    win,
    nodes,
    collapse,
    modal,
    history,
    add(id) {
      const el = new Element(id);
      nodes.set(id, el);
      return el;
    },
    run(code) {
      assert.ok(code, "script found");
      vm.runInContext(code, context);
    },
    frames() {
      while (frames.length) frames.shift()();
    },
    timers() {
      for (let i = 0; timers.size && i < 20; i++) {
        const callbacks = [...timers.values()];
        timers.clear();
        callbacks.forEach((cb) => cb());
      }
    },
  };
}
const touch = (x, y, id = 1) => ({
  identifier: id,
  clientX: x,
  clientY: y,
  screenX: x,
  screenY: y,
});
function swipe(el, x1, y1, x2, y2) {
  el.emit("touchstart", {
    touches: [touch(x1, y1)],
    changedTouches: [touch(x1, y1)],
  });
  el.emit("touchmove", { touches: [touch(x2, y2)] });
  el.emit("touchend", { changedTouches: [touch(x2, y2)] });
}
function mobile() {
  const h = harness(),
    nav = h.add("iesa-nav-collapse"),
    toggle = h.add("toggle");
  nav.classList.add("show");
  h.document.querySelector = (s) => (s === ".iesa-toggler" ? toggle : null);
  h.run(source("static/js/mobile-optimization.js"));
  h.document.emit("DOMContentLoaded");
  return { ...h, nav, toggle };
}
test("scrolling a long menu to its bottom and lifting the finger leaves it open", () => {
  const h = mobile();
  h.nav.scrollTop = 300;
  swipe(h.nav, 180, 500, 190, 180);
  assert.equal(h.collapse.hides, 0);
  assert.ok(h.nav.classList.contains("show"));
});
test("Escape closes the mobile menu and returns focus to its button", () => {
  const h = mobile();
  h.document.emit("keydown", { key: "Escape" });
  assert.equal(h.collapse.hides, 1);
  assert.equal(h.toggle.focused, true);
});
test("desktop outside clicks do not collapse the desktop navigation", () => {
  const h = mobile();
  h.win.innerWidth = 1440;
  h.document.emit("click", { target: new Element() });
  assert.equal(h.collapse.hides, 0);
});
test("HTMX settlement does not undo scrolling performed by the user", () => {
  const h = mobile();
  h.win.scrollY = 100;
  h.document.emit("htmx:beforeSwap");
  h.win.scrollY = 400;
  h.document.emit("htmx:afterSettle");
  assert.equal(h.win.scrollCalls || 0, 0);
});
function sheets() {
  const h = harness();
  const a = h.add("a"),
    b = h.add("b"),
    back = h.add("bs-backdrop");
  for (const s of [a, b]) {
    s.handle = new Element();
    s.close = new Element();
    s.querySelector = (q) => (q === ".bs-handle" ? s.handle : s.close);
    s.querySelectorAll = () => [];
  }
  h.document.querySelectorAll = (q) =>
    q === ".iesa-bottom-sheet" ? [a, b] : [];
  h.run(inline("templates/base.html", "window.IESABottomSheet ="));
  return { ...h, a, b, back, api: h.win.IESABottomSheet };
}
test("a rapidly reopened sheet keeps its backdrop and remains the active sheet", () => {
  const h = sheets();
  h.api.open("a");
  h.frames();
  h.api.close("a");
  h.api.open("b");
  h.frames();
  h.timers();
  assert.equal(h.back.style.display, "block");
  assert.equal(h.api._currentSheet, h.b);
});
test("opening the same sheet twice does not leave the page permanently locked after close", () => {
  const h = sheets();
  h.body.style.overflow = "";
  h.api.open("a");
  h.frames();
  h.api.open("a");
  h.api.close("a");
  assert.equal(h.body.style.overflow, "");
});
test("closing an obsolete sheet cannot unlock or close another sheet", () => {
  const h = sheets();
  h.api.open("a");
  h.frames();
  h.api.open("b");
  h.frames();
  h.api.close("a");
  assert.equal(h.api._currentSheet, h.b);
  assert.equal(h.body.style.overflow, "hidden");
});
test("cancelled handle drag resets its transform and cannot later dismiss the sheet", () => {
  const h = sheets();
  h.api.open("a");
  h.frames();
  h.a.handle.emit("touchstart", { touches: [touch(100, 100)] });
  h.a.handle.emit("touchmove", { touches: [touch(100, 180)] });
  h.a.handle.emit("touchcancel");
  assert.equal(h.a.style.transform, "");
  h.a.handle.emit("touchend", { changedTouches: [touch(100, 350)] });
  assert.equal(h.api._currentSheet, h.a);
});
test("closing a sheet before its opening frame cannot make it visible again", () => {
  const h = sheets();
  h.api.open("a");
  h.api.close("a");
  h.frames();
  assert.equal(h.a.classList.contains("open"), false);
});
function gallery() {
  const h = harness();
  const items = [0, 1, 2].map((i) => {
    const e = new Element();
    e.dataset = { src: `photo-${i}`, caption: `Photo ${i}` };
    return e;
  });
  h.document.querySelectorAll = (s) =>
    s === ".gallery-grid__item" ? items : [];
  for (const id of [
    "galleryModal",
    "galleryModalImage",
    "galleryModalCaption",
    "galleryCounter",
    "galleryPrev",
    "galleryNext",
  ])
    h.add(id);
  h.run(
    inline(
      "gallery/templates/gallery/gallery.html",
      "const items = Array.from",
    ),
  );
  items[0].emit("click");
  return {
    ...h,
    items,
    modalEl: h.nodes.get("galleryModal"),
    image: h.nodes.get("galleryModalImage"),
  };
}
test("diagonal vertical scrolling in the photo viewer does not change photos", () => {
  const h = gallery();
  swipe(h.modalEl, 180, 450, 100, 150);
  h.timers();
  assert.equal(h.image.src, "photo-0");
});
test("horizontal swiping still advances the photo", () => {
  const h = gallery();
  swipe(h.modalEl, 260, 300, 80, 305);
  h.timers();
  assert.equal(h.image.src, "photo-1");
});
test("pinching and cancelled touch do not advance photos", () => {
  const h = gallery();
  h.modalEl.emit("touchstart", {
    touches: [touch(260, 300), touch(70, 300, 2)],
    changedTouches: [touch(260, 300)],
  });
  h.modalEl.emit("touchend", { changedTouches: [touch(70, 300)] });
  h.timers();
  assert.equal(h.image.src, "photo-0");
  h.modalEl.emit("touchstart", {
    touches: [touch(260, 300)],
    changedTouches: [touch(260, 300)],
  });
  h.modalEl.emit("touchcancel");
  h.modalEl.emit("touchend", { changedTouches: [touch(70, 300)] });
  h.timers();
  assert.equal(h.image.src, "photo-0");
});
test("closing during a photo transition never reopens the modal", () => {
  const h = gallery();
  h.nodes.get("galleryNext").emit("click");
  h.modalEl.emit("hide.bs.modal");
  h.timers();
  assert.equal(h.modal.opens, 1);
});
test("rapid next presses advance by each press instead of losing the second press", () => {
  const h = gallery();
  h.nodes.get("galleryNext").emit("click");
  h.nodes.get("galleryNext").emit("click");
  h.timers();
  assert.equal(h.image.src, "photo-2");
});
function backGesture() {
  const h = harness();
  h.run(
    source("static/js/touch-gestures.js").slice(
      source("static/js/touch-gestures.js").indexOf(
        "(function () {",
        source("static/js/touch-gestures.js").indexOf("Block 2e"),
      ),
    ),
  );
  return h;
}
test("standalone back swipe never navigates through an open overlay", () => {
  const h = backGesture();
  h.body.style.overflow = "hidden";
  swipe(h.document, 10, 100, 150, 100);
  assert.equal(h.history.calls, 0);
});
test("standalone back swipe ignores cancellation and diagonal scroll", () => {
  const h = backGesture();
  swipe(h.document, 10, 100, 110, 190);
  assert.equal(h.history.calls, 0);
  h.document.emit("touchstart", { touches: [touch(10, 100)] });
  h.document.emit("touchcancel");
  h.document.emit("touchend", { changedTouches: [touch(150, 100)] });
  assert.equal(h.history.calls, 0);
});
test("intentional standalone back swipe still works", () => {
  const h = backGesture();
  swipe(h.document, 10, 100, 150, 102);
  assert.equal(h.history.calls, 1);
});
function qr() {
  const h = harness(),
    overlay = h.add("qr-fullscreen-overlay");
  overlay.setAttribute("aria-hidden", "true");
  h.add("qr-fs-close");
  h.run(inline("templates/base.html", "window.IESAOpenQR ="));
  return { ...h, overlay };
}
test("scrolling the QR overlay does not dismiss the QR", () => {
  const h = qr();
  h.win.IESAOpenQR();
  swipe(h.overlay, 150, 100, 160, 250);
  assert.equal(h.overlay.getAttribute("aria-hidden"), "false");
});
test("opening QR twice then closing restores scroll instead of trapping the page", () => {
  const h = qr();
  h.body.style.overflow = "";
  h.win.IESAOpenQR();
  h.win.IESAOpenQR();
  h.win.IESACloseQR();
  assert.equal(h.body.style.overflow, "");
});
test("menu closure preserves the scroll lock of an already opened bottom sheet", () => {
  const h = harness(),
    header = new Element(),
    nav = h.add("iesa-nav-collapse");
  h.document.querySelector = (s) => (s === "header" ? header : null);
  h.run(source("static/js/header-hide-on-scroll.js"));
  h.document.emit("DOMContentLoaded");
  nav.emit("show.bs.collapse");
  h.win.IESABottomSheet = { _currentSheet: new Element() };
  nav.emit("hidden.bs.collapse");
  assert.equal(h.body.style.overflow, "hidden");
});
test("closing a sheet opened over the menu releases the obsolete menu lock", () => {
  const h = sheets();
  h.body.classList.add("mobile-menu-open");
  h.body.style.overflow = "hidden";
  h.api.open("a");
  h.frames();
  h.body.classList.remove("mobile-menu-open");
  h.api.close("a");
  assert.equal(h.body.style.overflow, "");
});
test("a pending QR wake lock is released if the QR has already closed", async () => {
  const h = qr();
  let releases = 0;
  h.win.navigator.wakeLock = {
    request: async () => ({
      release: async () => {
        releases++;
      },
    }),
  };
  h.win.IESAOpenQR();
  h.win.IESACloseQR();
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(releases, 1);
});
test("opening a Bootstrap modal hands off the menu scroll lock before its snapshot", () => {
  const h = harness(), modal = new Element();
  modal.classList.add("modal");
  h.add("iesa-nav-collapse").classList.add("show");
  h.body.classList.add("mobile-menu-open"); h.body.style.overflow = "hidden";
  h.run(inline("templates/base.html", "document.addEventListener('show.bs.modal'"));
  h.document.emit("show.bs.modal", { target: modal });
  assert.equal(h.body.style.overflow, "");
  assert.equal(h.collapse.hides, 1);
});
