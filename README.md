# AI Document Checker

A self-contained web app that checks English and Dutch documents for AI-sounding writing and suggests more human rewrites.

- **Checker:** paste text or upload a `.docx`, `.txt` or `.md` file.
  - **Check** runs instantly in the browser with no API key. It scores eight signals and highlights them in the text:
    stock AI phrases ("delve", "plays a crucial role", "in het huidige digitale landschap"), uniform sentence length,
    stock transitions ("Moreover", "Bovendien"), em dashes, "not X but Y" constructions, lists of three,
    uniform paragraphs and chatbot formatting.
  - **Deep check with Claude** needs an Anthropic API key on the server. Claude judges how likely the text is AI-written,
    flags passages with a reason and a rewrite in the document's own language, and gives feedback on clarity, structure,
    tone, concision and grammar. **Apply rewrite** swaps a passage into your text.
- **History:** every check is saved automatically. You can search, reopen, rename (edit the title), delete or export to JSON.
  History lives in each visitor's browser (localStorage). Nothing is stored on the server.
- **Menu:** a sidebar with New check, Checker, History, How it works and your most recent documents.
  It collapses into a ☰ menu on phones.

Neither check is proof. Formal, templated or non-native writing can look machine-made, and edited AI text can look human.
Use the result to improve a text, not as a verdict on a person.

## Run locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # optional; without it only the instant check works
python server.py                  # open http://127.0.0.1:8000
```

## Deploy

The app is one small Python process with a single dependency (`anthropic`), packaged as a Docker image.

```bash
cd ai-document-checker
docker build -t ai-checker .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... -e APP_PASSWORD=choose-one ai-checker
```

On a hosting platform (Render, Railway, Fly.io, Google Cloud Run, a VPS):

1. Point the service at this repository. It builds from the `Dockerfile` in the root.
2. Set the environment variables below. Store the API key as a secret.
3. Use `/healthz` as the health-check path. It answers without a password.

The platform's HTTPS is needed when you set a password, because basic auth sends it with every request.

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Enables the deep check. Without it the instant check still works. |
| `APP_PASSWORD` | none | Puts the whole app behind a browser password prompt (any username). **Set this on any public URL**, or anyone can spend your Claude credit. |
| `PORT` | `8000` | Port to listen on. Most platforms set this for you. |
| `HOST` | `0.0.0.0` in Docker, `127.0.0.1` otherwise | Interface to bind. |
| `AI_CHECKER_MODEL` | `claude-opus-5-5` | Claude model for the deep check. |

Documents sent to the deep check go to the Anthropic API through the server. The server does not log or store them.

## Tests

```bash
node --test tests/heuristics.test.mjs tests/history.test.mjs
python -m unittest discover -s tests
```

## Files

- `static/heuristics.js`: offline signals, phrase lists (EN/NL) and scoring weights. Tune them here.
- `static/history.js`: browser-side history storage.
- `static/app.js`: menu and routing, the checker, the history page.
- `server.py`: serves the app, password protection, Claude review (`/api/review`), `.docx` extraction (`/api/extract`).
- `Dockerfile`: production image (runs as a non-root user, with a health check).
