# AI Document Checker

A local web page that checks English and Dutch documents for AI-sounding writing and suggests more human rewrites.

It works in two layers:

1. **Offline check** (instant, runs in the browser, no API key). It scores eight signals and highlights them in the text:
   stock AI phrases ("delve", "plays a crucial role", "in het huidige digitale landschap"), uniform sentence length,
   stock transitions ("Moreover", "Bovendien"), em dashes, "not X but Y" constructions, lists of three,
   uniform paragraphs and chatbot formatting.
2. **Deep check with Claude** (needs an Anthropic API key). Claude judges how likely the text is AI-written,
   flags passages with a reason and a rewrite in the document's own language, and gives writing feedback on clarity,
   structure, tone, concision and grammar. Click **Apply rewrite** to swap a passage into your text.

Neither layer is proof. Formal, templated or non-native writing can look machine-made, and edited AI text can look human.
Use the result as a prompt for revision, not as a verdict on a person.

## Run it

```bash
pip install -r ai_checker/requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # optional; without it only the offline check works
python ai_checker/server.py           # then open http://127.0.0.1:8000
```

Options: `--host`, `--port`. Set `AI_CHECKER_MODEL` to use a different Claude model (default `claude-opus-5-5`).

You can paste text or upload `.docx`, `.txt` or `.md` files.

## Tests

```bash
node --test ai_checker/tests/heuristics.test.mjs
python -m unittest discover -s ai_checker/tests
```

## Files

- `static/heuristics.js` – offline signals, phrase lists (EN/NL) and scoring weights. Tune them here.
- `static/app.js` – page logic: highlighting, Claude results, applying rewrites.
- `server.py` – serves the page, calls Claude (`/api/review`) and extracts `.docx` text (`/api/extract`).
