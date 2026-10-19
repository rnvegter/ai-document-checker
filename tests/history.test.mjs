import { test } from "node:test";
import assert from "node:assert/strict";
import { createHistory, titleFor } from "../static/history.js";

function memoryStorage(limit = Infinity) {
  const data = new Map();
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => {
      if (v.length > limit) throw new Error("QuotaExceededError");
      data.set(k, v);
    },
    removeItem: (k) => data.delete(k),
  };
}

test("titles come from the first non-empty line", () => {
  assert.equal(titleFor("\n\n# My report\nBody"), "My report");
  assert.equal(titleFor(""), "Untitled");
  assert.ok(titleFor("x".repeat(200)).length <= 70);
});

test("save, update, list, remove", () => {
  const h = createHistory(memoryStorage());
  const a = h.save({ text: "First doc", heurScore: 10 });
  const b = h.save({ text: "Second doc", heurScore: 20 });
  assert.deepEqual(h.list().map((e) => e.id), [b.id, a.id]);
  const a2 = h.save({ id: a.id, text: "First doc, edited", heurScore: 30 });
  assert.equal(a2.created, a.created);
  assert.equal(h.list()[0].id, a.id);
  assert.equal(h.get(a.id).heurScore, 30);
  h.remove(b.id);
  assert.equal(h.list().length, 1);
  h.clear();
  assert.equal(h.list().length, 0);
});

test("drops oldest entries when storage is full", () => {
  const h = createHistory(memoryStorage(600));
  for (let i = 0; i < 10; i++) h.save({ text: `Document number ${i} `.repeat(3) });
  const list = h.list();
  assert.ok(list.length > 0 && list.length < 10);
  assert.ok(list[0].text.startsWith("Document number 9"));
});

test("works without storage and with corrupt data", () => {
  const none = createHistory(null);
  assert.equal(none.save({ text: "x" }).title, "x");
  assert.deepEqual(none.list(), []);
  const s = memoryStorage();
  s.setItem("aichecker.history.v1", "{not json");
  assert.deepEqual(createHistory(s).list(), []);
});
