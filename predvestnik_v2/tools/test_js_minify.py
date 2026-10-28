#!/usr/bin/env python3
"""The JS minifier (FastAPI/static_assets.py) changes no code: every script the Mini App serves keeps exactly the same tokens on the same lines.

    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_js_minify.py

The token check runs a real JS tokenizer (acorn, from /opt/node-tools/node_modules or NODE_PATH) over the source and its minified copy:
same token types and exact token text, each on the same line (so error reports point at the same line), and the minified copy parses.
Without Node and acorn only the small cases below run, and the run says so.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("PV_MINIFY_JS", None)

from FastAPI.static_assets import minify_js  # noqa: E402

CASES = {
    "let a = 1;   // note\n\n    const b = 2; /* block */ c();\n": "let a = 1;\n\nconst b = 2; c();\n",
    "x = '// not a comment' + \"/* nor this */\";": "x = '// not a comment' + \"/* nor this */\";",
    "s = `a ${b ? `c ${d}` : '}'} // kept`; // gone": "s = `a ${b ? `c ${d}` : '}'} // kept`;",
    "if (/\\/\\/'[/]/.test(s)) n = a / b / c;": "if (/\\/\\/'[/]/.test(s)) n = a / b / c;",
    "return /x\\//g.exec(y)": "return /x\\//g.exec(y)",
    "f(a,\n  /* two\n  lines */ b)": "f(a,\n\nb)",
    "    html = `\n      <b>  kept  </b>\n    `;": "html = `\n      <b>  kept  </b>\n    `;",
}
UNSURE = ("s = 'never closed", "x = `open ${", "}", "a = /re\n/")

for source, expected in CASES.items():
    assert minify_js(source) == expected, (source, minify_js(source))
for source in UNSURE:
    assert minify_js(source) == source, f"an unclear source is served as it is: {source!r}"
os.environ["PV_MINIFY_JS"] = "0"
assert minify_js("a = 1; // kept\n") == "a = 1; // kept\n", "PV_MINIFY_JS=0 serves the sources as they are"
os.environ.pop("PV_MINIFY_JS")

TOKENS = r"""
const acorn = require('acorn'); const fs = require('fs');
const toks = text => { const out = []; for (const t of acorn.tokenizer(text, {ecmaVersion: 'latest', locations: true, allowHashBang: true}))
  out.push([t.type.label, text.slice(t.start, t.end), t.loc.start.line]); return out; };
const bad = [];
for (const [name, src, min] of JSON.parse(fs.readFileSync(0, 'utf8'))) {
  try { acorn.parse(min, {ecmaVersion: 'latest', allowHashBang: true}); } catch (e) { bad.push(`${name}: the minified copy does not parse: ${e.message}`); continue; }
  const a = toks(src), b = toks(min);
  if (a.length !== b.length) { bad.push(`${name}: ${a.length} tokens became ${b.length}`); continue; }
  const i = a.findIndex((t, k) => JSON.stringify(t) !== JSON.stringify(b[k]));
  if (i >= 0) bad.push(`${name}: token ${i} ${JSON.stringify(a[i])} became ${JSON.stringify(b[i])}`);
}
console.log(JSON.stringify(bad));
"""


def node_with_acorn() -> dict[str, str] | None:
    if not shutil.which("node"):
        return None
    env = {**os.environ, "NODE_PATH": os.pathsep.join(p for p in (os.environ.get("NODE_PATH", ""), "/opt/node-tools/node_modules") if p)}
    probe = subprocess.run(["node", "-e", "require('acorn')"], env=env, capture_output=True)
    return env if probe.returncode == 0 else None


def main() -> None:
    from FastAPI.main import _JS_SOURCES, _STORE
    env = node_with_acorn()
    if env is None:
        print("JS minifier: small cases OK; SKIPPED the token check of the served scripts (needs node with acorn)")
        return
    files = [(name, source, _STORE[name].body.decode("utf-8")) for name, source in _JS_SOURCES.items()]
    assert any(min_ != src for _, src, min_ in files), "the served scripts are minified"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as script:
        script.write(TOKENS)
    try:
        run = subprocess.run(["node", script.name], input=json.dumps(files), env=env, capture_output=True, text=True, check=True)
    finally:
        os.unlink(script.name)
    bad = json.loads(run.stdout)
    assert not bad, "\n".join(bad)
    before = sum(len(src.encode()) for _, src, _ in files)
    after = sum(len(min_.encode()) for _, _, min_ in files)
    print(f"JS minifier: OK, {len(files)} scripts keep every token on its line; {before // 1024} KB -> {after // 1024} KB before gzip")


if __name__ == "__main__":
    main()
