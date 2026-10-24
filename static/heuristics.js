// Offline AI-writing signals for English and Dutch text.
// Every signal is a weak indicator on its own; the combined score is a hint,
// not proof that a text was machine-written.

// weight 1 = strong tell, 0.5 = common in human writing too
const PHRASES = {
  en: [
    ["\\bdelv(e|es|ed|ing)\\b", 1, "Say what you actually examine."],
    ["\\btapestry\\b", 1, "Drop the metaphor; name the things."],
    ["\\b(is|stands as|serves as) a testament to\\b", 1, "State the evidence directly."],
    ["\\bin today'?s (fast-paced|digital|ever-changing|rapidly evolving) (world|landscape|age|era)\\b", 1, "Cut the scene-setting opener."],
    ["\\bever-(evolving|changing)\\b", 1, "Say what changed and when."],
    ["\\b(digital|business|regulatory|competitive) landscape\\b", 1, "Name the market, sector or rules."],
    ["\\bnavigat(e|ing) the complexities\\b", 1, "Name the specific difficulty."],
    ["\\bit(?:'s| is) (important|worth|crucial) (to note|noting|to remember)\\b", 1, "Just state the point."],
    ["\\bplays? an? (crucial|pivotal|vital|key) role\\b", 1, "Say what it does."],
    ["\\bpivotal\\b", 0.5, "Use a plainer word, or show why it matters."],
    ["\\bseamless(ly)?\\b", 0.5, "Describe the actual experience."],
    ["\\brobust\\b", 0.5, "Say what it withstands."],
    ["\\bleverag(e|es|ed|ing)\\b", 0.5, "Use 'use'."],
    ["\\bharness(es|ed|ing)? the (power|potential)\\b", 1, "Say what is used and for what."],
    ["\\bunlock(s|ed|ing)? (the|its|their|your) (full )?potential\\b", 1, "Say what becomes possible."],
    ["\\bfoster(s|ed|ing)?\\b", 0.5, "Use 'build', 'encourage' or a concrete verb."],
    ["\\bunderscor(e|es|ed|ing)\\b", 0.5, "Use 'shows'."],
    ["\\bshowcas(e|es|ed|ing)\\b", 0.5, "Use 'shows'."],
    ["\\bintricate\\b", 0.5, "Say what makes it complicated."],
    ["\\bmultifaceted\\b", 1, "List the facets or drop it."],
    ["\\b(in|within) the realm of\\b", 1, "Use 'in'."],
    ["\\bembark(s|ed|ing)? on\\b", 1, "Use 'start'."],
    ["\\bholistic\\b", 0.5, "Say what is included."],
    ["\\bgame[- ]changer\\b", 1, "Quantify the change."],
    ["\\bcutting[- ]edge\\b", 0.5, "Name the technology."],
    ["\\belevat(e|es|ed|ing)\\b", 0.5, "Use 'improve' and say how."],
    ["\\bempower(s|ed|ing)?\\b", 0.5, "Say what people can now do."],
    ["\\bvibrant\\b", 0.5, "Show it with a detail."],
    ["\\bnestled\\b", 1, "Give the location plainly."],
    ["\\ba myriad of\\b", 1, "Give a number or examples."],
    ["\\bboasts?\\b", 0.5, "Use 'has'."],
    ["\\bat its core\\b", 1, "Cut it."],
    ["\\bwhether you'?re an? .{1,40} or an?\\b", 1, "Address the actual reader."],
    ["\\b(key takeaways?|valuable insights?)\\b", 1, "State the insight itself."],
    ["\\blet'?s dive (in|into)\\b", 1, "Cut it."],
    ["\\bi hope this helps\\b", 1, "Chatbot sign-off: delete."],
    ["\\b(comprehensive|meticulous(ly)?)\\b", 0.5, "Show the scope instead."],
    ["\\bin conclusion\\b", 0.5, "Let the last paragraph conclude on its own."],
    ["\\bin summary\\b", 0.5, "Cut the signpost."],
  ],
  nl: [
    ["\\bin (het|de) (huidige|snel veranderende|digitale) (digitale )?(landschap|wereld|tijdperk)\\b", 1, "Schrap de sfeerschets."],
    ["\\b(digitale|zakelijke|huidige) landschap\\b", 1, "Noem de markt of sector."],
    ["\\bhet is (belangrijk|goed|cruciaal) om (op te merken|te benadrukken|te vermelden|te onthouden)\\b", 1, "Zeg het gewoon."],
    ["\\bvermeldenswaard\\b", 1, "Zeg het gewoon."],
    ["\\bspeelt een (cruciale|essenti[eë]le|belangrijke|sleutel)rol\\b|\\bspeelt een (cruciale|essenti[eë]le|belangrijke) rol\\b", 1, "Zeg wat het doet."],
    ["\\bcruciaal\\b|\\bcruciale\\b", 0.5, "Laat zien waarom het ertoe doet."],
    ["\\bessenti[eë]le?\\b", 0.5, "Gebruik 'nodig' of laat het weg."],
    ["\\bnaadloze?\\b", 0.5, "Beschrijf wat de gebruiker merkt."],
    ["\\brobuuste?\\b", 0.5, "Zeg waartegen het bestand is."],
    ["\\b(het )?potentieel (te )?(ontsluiten|benutten|ontgrendelen)\\b", 1, "Zeg wat er mogelijk wordt."],
    ["\\bduiken in\\b|\\bdieper ingaan op\\b", 1, "Zeg wat je onderzoekt."],
    ["\\blaten we (eens )?(kijken|duiken|beginnen)\\b", 1, "Schrappen."],
    ["\\bholistische?\\b", 1, "Noem wat erbij hoort."],
    ["\\bintegrale aanpak\\b", 0.5, "Noem de onderdelen."],
    ["\\bveelzijdige?\\b", 0.5, "Noem de kanten."],
    ["\\btoekomstbestendige?\\b", 0.5, "Zeg tot wanneer en waartegen."],
    ["\\been (breed )?scala aan\\b", 1, "Geef een aantal of voorbeelden."],
    ["\\bof je nu\\b.{1,60}\\bbent\\b", 1, "Spreek de echte lezer aan."],
    ["\\bin essentie\\b|\\bin de kern\\b", 0.5, "Schrappen."],
    ["\\bde sleutel tot\\b", 1, "Zeg wat de oorzaak is."],
    ["\\bwaardevolle inzichten\\b", 1, "Noem het inzicht zelf."],
    ["\\bonmisbaar\\b", 0.5, "Laat zien waarom."],
    ["\\bfaciliter(en|t|de)\\b", 0.5, "Gebruik 'mogelijk maken' of 'regelen'."],
    ["\\btransformatie(ve|f)\\b", 1, "Zeg wat er verandert."],
    ["\\bbaanbrekende?\\b", 1, "Kwantificeer de vernieuwing."],
    ["\\bsynergie\\b", 1, "Zeg wat samen beter gaat."],
    ["\\bnaar een hoger niveau tillen\\b|\\bnaar een hoger plan\\b", 1, "Zeg wat beter wordt."],
    ["\\bik hoop dat dit helpt\\b", 1, "Chatbot-afsluiter: weg ermee."],
    ["\\bconcluderend\\b|\\bsamenvattend\\b", 0.5, "Laat de slotalinea zelf concluderen."],
    ["\\bal met al\\b", 0.5, "Schrappen."],
  ],
};

const TRANSITIONS = {
  en: /^(moreover|furthermore|additionally|in addition|overall|ultimately|consequently|notably|importantly|that said|however|in conclusion)\b/i,
  nl: /^(bovendien|daarnaast|tevens|verder|kortom|echter|uiteindelijk|tot slot|ten slotte|concluderend|samenvattend|al met al|dat gezegd hebbende)\b/i,
};

const NEG_PARALLEL = [
  /\bnot (just|only|merely|simply)\b[^.!?]{1,80}?\bbut( also)?\b/gi,
  /\bit'?s not\b[^.!?]{1,60}?[,;—–-]\s*it'?s\b/gi,
  /\bniet alleen\b[^.!?]{1,80}?\bmaar ook\b/gi,
  /\bhet gaat niet (alleen )?om\b[^.!?]{1,80}?\bmaar\b/gi,
];

// "X, Y and Z" lists of short items
const TRIAD = /\b[\p{L}-]+(?: [\p{L}-]+)?, [\p{L}-]+(?: [\p{L}-]+)?,? (?:and|or|en|of) [\p{L}-]+/giu;

const STOPWORDS = {
  en: ["the", "and", "is", "of", "to", "that", "it", "with", "for", "this", "are", "be"],
  nl: ["de", "het", "een", "en", "van", "is", "dat", "niet", "met", "voor", "zijn", "wordt"],
};

export function detectLanguage(text) {
  const words = text.toLowerCase().match(/\p{L}+/gu) || [];
  const count = (lang) => words.filter((w) => STOPWORDS[lang].includes(w)).length;
  return count("nl") > count("en") ? "nl" : "en";
}

export function splitSentences(text) {
  const out = [];
  const re = /[^.!?\n]+(?:[.!?]+["'”’)]*|\n|$)/g;
  let m;
  while ((m = re.exec(text))) {
    const raw = m[0];
    const trimmed = raw.trim();
    if (!trimmed) continue;
    const start = m.index + raw.indexOf(trimmed);
    out.push({ text: trimmed, start, end: start + trimmed.length });
  }
  return out;
}

const wordCount = (s) => (s.match(/[\p{L}\p{N}'’-]+/gu) || []).length;

function coefVar(nums) {
  if (nums.length < 2) return null;
  const mean = nums.reduce((a, b) => a + b, 0) / nums.length;
  if (!mean) return null;
  const variance = nums.reduce((a, b) => a + (b - mean) ** 2, 0) / nums.length;
  return Math.sqrt(variance) / mean;
}

const clamp01 = (x) => Math.max(0, Math.min(1, x));

function findAll(re, text, make) {
  const spans = [];
  re.lastIndex = 0;
  let m;
  while ((m = re.exec(text))) {
    spans.push({ start: m.index, end: m.index + m[0].length, ...make(m) });
    if (m[0] === "") re.lastIndex++;
  }
  return spans;
}

export function analyze(source, lang = "auto") {
  // Blank out PowerPoint [Slide n] markers; same length keeps highlight offsets valid.
  const text = source.replace(/^\[Slide \d+(?: notes)?\]$/gm, (m) => " ".repeat(m.length));
  const language = lang === "auto" ? detectLanguage(text) : lang;
  const words = wordCount(text);
  const per1k = (n) => (words ? (n * 1000) / words : 0);
  const sentences = splitSentences(text).filter((s) => wordCount(s.text) > 0);
  const paragraphs = text.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  const spans = [];

  // 1. Stock phrases
  let phraseWeight = 0;
  const phraseHits = {};
  for (const [src, weight, tip] of PHRASES[language]) {
    const found = findAll(new RegExp(src, "giu"), text, (m) => ({
      type: "phrase",
      label: weight >= 1 ? "Typical AI phrase" : "Overused word",
      tip,
      weight,
      match: m[0],
    }));
    for (const s of found) {
      phraseWeight += weight;
      const key = s.match.toLowerCase();
      phraseHits[key] = (phraseHits[key] || 0) + 1;
    }
    spans.push(...found);
  }

  // 2. Sentence-length uniformity (low burstiness)
  const lengths = sentences.map((s) => wordCount(s.text));
  const sentCv = sentences.length >= 5 ? coefVar(lengths) : null;

  // 3. Transition-word openers
  let transitionCount = 0;
  for (const s of sentences) {
    const m = s.text.replace(/^[^\p{L}]+/u, "").match(TRANSITIONS[language]);
    if (m) {
      transitionCount++;
      const offset = s.text.indexOf(m[0]);
      spans.push({
        start: s.start + offset,
        end: s.start + offset + m[0].length,
        type: "transition",
        label: "Stock transition",
        tip: language === "nl" ? "Laat de logica van de zinnen het werk doen." : "Let the logic carry the reader; drop the connector.",
      });
    }
  }

  // 4. Em dashes
  const dashSpans = findAll(/\s?—\s?/g, text, () => ({
    type: "dash",
    label: "Em dash",
    tip: language === "nl" ? "Gebruik een komma, dubbele punt of nieuwe zin." : "Use a comma, colon or full stop.",
  }));
  spans.push(...dashSpans);

  // 5. Negative parallelisms
  let negCount = 0;
  for (const re of NEG_PARALLEL) {
    const found = findAll(re, text, () => ({
      type: "parallel",
      label: "Negative parallelism",
      tip: language === "nl" ? "Zeg direct wat het wél is." : "Say what it is, without the 'not X but Y' setup.",
    }));
    negCount += found.length;
    spans.push(...found);
  }

  // 6. Triads ("X, Y and Z")
  const triadCount = (text.match(TRIAD) || []).length;

  // 7. Paragraph uniformity
  const paraCv = paragraphs.length >= 4 ? coefVar(paragraphs.map(wordCount)) : null;

  // 8. Chatbot formatting: bolded bullet labels, markdown headings
  const formatCount =
    (text.match(/^\s*(?:[-*•]|\d+\.)\s+\*\*[^*\n]+\*\*/gm) || []).length +
    (text.match(/^#{1,4} /gm) || []).length;

  const signals = [
    {
      id: "phrases",
      name: "Stock AI phrases",
      weight: 0.3,
      score: clamp01(per1k(phraseWeight) / 8),
      detail: `${Object.values(phraseHits).reduce((a, b) => a + b, 0)} hits (${per1k(phraseWeight).toFixed(1)} weighted per 1,000 words)`,
    },
    {
      id: "burstiness",
      name: "Uniform sentence length",
      weight: 0.2,
      score: sentCv === null ? null : clamp01((0.65 - sentCv) / 0.35),
      detail: sentCv === null ? "Needs at least 5 sentences" : `Variation ${sentCv.toFixed(2)} (human prose is usually above 0.5)`,
    },
    {
      id: "transitions",
      name: "Stock transitions",
      weight: 0.12,
      score: sentences.length ? clamp01(transitionCount / sentences.length / 0.2) : null,
      detail: `${transitionCount} of ${sentences.length} sentences open with a connector`,
    },
    {
      id: "dashes",
      name: "Em dashes",
      weight: 0.1,
      score: clamp01(per1k(dashSpans.length) / 6),
      detail: `${dashSpans.length} (${per1k(dashSpans.length).toFixed(1)} per 1,000 words)`,
    },
    {
      id: "parallel",
      name: "“Not X, but Y” constructions",
      weight: 0.08,
      score: clamp01(per1k(negCount) / 3),
      detail: `${negCount} found`,
    },
    {
      id: "triads",
      name: "Lists of three",
      weight: 0.08,
      score: sentences.length ? clamp01(triadCount / sentences.length / 0.3) : null,
      detail: `${triadCount} in ${sentences.length} sentences`,
    },
    {
      id: "paragraphs",
      name: "Uniform paragraphs",
      weight: 0.06,
      score: paraCv === null ? null : clamp01((0.5 - paraCv) / 0.35),
      detail: paraCv === null ? "Needs at least 4 paragraphs" : `Variation ${paraCv.toFixed(2)}`,
    },
    {
      id: "formatting",
      name: "Chatbot formatting",
      weight: 0.06,
      score: clamp01(formatCount / 4),
      detail: `${formatCount} bold-label bullets or markdown headings`,
    },
  ];

  const usable = signals.filter((s) => s.score !== null);
  const totalWeight = usable.reduce((a, s) => a + s.weight, 0);
  const score = totalWeight ? Math.round((usable.reduce((a, s) => a + s.weight * s.score, 0) / totalWeight) * 100) : 0;

  return {
    language,
    words,
    sentences: sentences.length,
    score,
    confidence: words < 80 ? "low" : words < 300 ? "medium" : "high",
    signals,
    spans: dedupeSpans(spans),
  };
}

// Keep the earliest, longest span where highlights overlap.
function dedupeSpans(spans) {
  const sorted = [...spans].sort((a, b) => a.start - b.start || b.end - a.end);
  const out = [];
  let lastEnd = -1;
  for (const s of sorted) {
    if (s.start >= lastEnd) {
      out.push(s);
      lastEnd = s.end;
    }
  }
  return out;
}

export function summarizeForPrompt(result) {
  const lines = result.signals
    .filter((s) => s.score !== null)
    .map((s) => `- ${s.name}: ${Math.round(s.score * 100)}/100 (${s.detail})`);
  return `Heuristic score ${result.score}/100, language ${result.language}, ${result.words} words.\n${lines.join("\n")}`;
}
