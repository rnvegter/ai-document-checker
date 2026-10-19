import { test } from "node:test";
import assert from "node:assert/strict";
import { analyze, detectLanguage, splitSentences } from "../static/heuristics.js";

const AI_EN = `In today's fast-paced world, it is important to note that technology plays a crucial role in our lives. Moreover, it serves as a testament to human ingenuity. Furthermore, businesses must navigate the complexities of the digital landscape. Additionally, they need to leverage robust and seamless solutions. It's not just about tools — it's about people. Ultimately, embracing innovation will unlock the full potential of teams, leaders, and communities.`;

const HUMAN_EN = `I fixed the boiler on Tuesday. Took three hours, mostly because the manual was wrong about which valve feeds the expansion tank, and I only figured that out after draining the whole system twice. My neighbour Pete lent me a 22mm pipe cutter. Never again. Next time I'm calling someone, even if it costs £180, which is what the plumber quoted me back in March when I first noticed the pressure dropping overnight.`;

const AI_NL = `In het huidige digitale landschap speelt technologie een cruciale rol. Bovendien is het belangrijk om op te merken dat organisaties een breed scala aan uitdagingen hebben. Daarnaast moeten zij het potentieel ontsluiten van hun medewerkers. Het gaat niet alleen om systemen, maar ook om mensen. Kortom, een holistische aanpak is de sleutel tot succes.`;

test("detects language", () => {
  assert.equal(detectLanguage(AI_EN), "en");
  assert.equal(detectLanguage(AI_NL), "nl");
});

test("splits sentences with offsets", () => {
  const text = "One two. Three four! Five?";
  const s = splitSentences(text);
  assert.deepEqual(s.map((x) => x.text), ["One two.", "Three four!", "Five?"]);
  for (const x of s) assert.equal(text.slice(x.start, x.end), x.text);
});

test("AI-style English scores well above human English", () => {
  const ai = analyze(AI_EN);
  const human = analyze(HUMAN_EN);
  assert.ok(ai.score >= 50, `ai score ${ai.score}`);
  assert.ok(human.score <= 25, `human score ${human.score}`);
});

test("Dutch phrases and constructions are flagged", () => {
  const r = analyze(AI_NL);
  assert.equal(r.language, "nl");
  const types = new Set(r.spans.map((s) => s.type));
  for (const t of ["phrase", "transition", "parallel"]) assert.ok(types.has(t), `missing ${t}`);
  assert.ok(r.score >= 50, `nl score ${r.score}`);
});

test("spans point at the right text and never overlap", () => {
  const r = analyze(AI_EN);
  let lastEnd = -1;
  for (const s of r.spans) {
    assert.ok(s.start >= lastEnd);
    assert.ok(s.end > s.start);
    lastEnd = s.end;
  }
  assert.ok(r.spans.some((s) => AI_EN.slice(s.start, s.end).toLowerCase() === "it is important to note"));
});

test("short or empty input does not crash", () => {
  assert.equal(analyze("").score, 0);
  assert.equal(analyze("Hello there.").confidence, "low");
});
