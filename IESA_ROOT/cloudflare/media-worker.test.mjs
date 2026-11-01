import assert from "node:assert/strict";
import test from "node:test";
import worker from "./media-worker.mjs";

function mediaStore() {
  const calls = [];
  const object = {
    body: "image", size: 5, httpEtag: '"content-hash"',
    writeHttpMetadata(headers) { headers.set("Content-Type", "image/webp"); },
  };
  return {
    calls,
    env: { MEDIA: {
      async get(key) { calls.push(["get", key]); return key === "missing" ? null : object; },
      async head(key) { calls.push(["head", key]); return object; },
    } },
  };
}

test("GET preserves stored keys and serves original content and MIME type", async () => {
  const { env, calls } = mediaStore();
  const response = await worker.fetch(new Request("https://media.example/media/a%20b.webp?v=1"), env);
  assert.equal(await response.text(), "image");
  assert.equal(response.headers.get("Content-Type"), "image/webp");
  assert.equal(response.headers.get("X-Content-Type-Options"), "nosniff");
  assert.deepEqual(calls, [["get", "media/a b.webp"]]);
});

test("HEAD does not read object contents", async () => {
  const { env, calls } = mediaStore();
  const response = await worker.fetch(new Request("https://media.example/photo.webp", { method: "HEAD" }), env);
  assert.equal(await response.text(), "");
  assert.equal(response.headers.get("Content-Length"), "5");
  assert.deepEqual(calls, [["head", "photo.webp"]]);
});

test("writes cannot reach the bucket", async () => {
  const { env, calls } = mediaStore();
  const response = await worker.fetch(new Request("https://media.example/photo.webp", { method: "PUT" }), env);
  assert.equal(response.status, 405);
  assert.deepEqual(calls, []);
});

test("missing objects and invalid encodings do not expose a bucket listing", async () => {
  const { env } = mediaStore();
  for (const [path, status] of [["/", 404], ["/missing", 404], ["/%ZZ", 400]]) {
    assert.equal((await worker.fetch(new Request(`https://media.example${path}`), env)).status, status);
  }
});

test("conditional GET returns no body for a matching ETag", async () => {
  const { env } = mediaStore();
  const response = await worker.fetch(new Request("https://media.example/photo.webp", {
    headers: { "If-None-Match": '"content-hash"' },
  }), env);
  assert.equal(response.status, 304);
  assert.equal(await response.text(), "");
});
