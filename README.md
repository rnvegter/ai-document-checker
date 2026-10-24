# AI Document Checker

A self-contained web app that checks Word, PowerPoint and text documents (English and Dutch) for AI-sounding writing,
reviews them, and produces a clean version without AI traces.

## What it does

- **Read documents:** paste text, or upload `.docx`, `.pptx`, `.txt` or `.md`.
  For PowerPoint it reads slide text, tables and speaker notes, marked per slide.
- **Check (instant):** runs in the browser with no API key. It scores eight signals and highlights them:
  stock AI phrases ("delve", "plays a crucial role", "in het huidige digitale landschap"), uniform sentence length,
  stock transitions ("Moreover", "Bovendien"), em dashes, "not X but Y" constructions, lists of three,
  uniform paragraphs and chatbot formatting.
- **Deep check with Claude:** Claude judges how likely the text is AI-written, flags passages with a reason and a
  rewrite, and reviews clarity, structure, tone, concision and grammar. **Apply rewrite** swaps a passage into your text.
- **Clean document:** removes the traces of AI and gives you a clean file in the same format.
  - Claude rewrites every paragraph that reads as machine-written, in the document's own language, keeping every fact,
    name, number, date, reference and legal wording. It never merges or splits paragraphs.
  - A `.docx` or `.pptx` keeps its layout, styles, tables, headers and speaker notes. Within a rewritten paragraph the
    formatting of the first run is applied to the whole paragraph, so check paragraphs that mixed bold text or links.
  - **Hidden characters:** zero-width characters, text-direction controls, Unicode "tag" characters (which can hide
    whole messages), variation selectors and unusual spaces are removed everywhere, including paragraphs that were not
    rewritten. Look-alike Cyrillic or Greek letters inside Latin words, and fullwidth or "styled" letters (𝐀, Ａ),
    become normal letters. Real Greek or Cyrillic words, Dutch accents, `ĳ` and emoji are left alone.
  - **Image metadata:** embedded JPEG, PNG and WebP images lose their EXIF, XMP, IPTC, C2PA content credentials and
    comments, without being re-encoded (same pixels, same quality). EXIF stays on a photo that needs it to display
    the right way up.
  - **File metadata:** author and "last modified by" are reset (or set to `CLEAN_AUTHOR`), the comments field is
    cleared, and custom properties that tag the file as AI-made (Copilot, GPT, "GeneratedBy", "AI_…") are removed.
    Sensitivity labels and other organisational properties are kept.
  - **Report:** after cleaning, the app lists every hidden trace it removed and where.
  - **Not covered:** statistical watermarks hidden in word choice (such as SynthID-Text) can't be detected here.
    Rewriting usually weakens them, but nothing guarantees they are gone, especially in paragraphs left unchanged.
    Pixel-level watermarks in images are not touched.
  - The cleaned version is saved as a new history entry next to the original, with a before/after score.
    If you edited the text after uploading, the result is a `.txt` file instead.
- **History:** every check is saved automatically in the browser (localStorage). You can search, reopen, rename,
  delete and export it. Nothing is stored on the server.

No AI detector is reliable. Formal, templated or non-native writing can look machine-made, and edited AI text can look
human. Use the scores to improve a text, not as a verdict on a person.

## Configuration (.env)

All settings come from a `.env` file. Start from the example:

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Enables Deep check and Clean document. Without it only the instant check works. |
| `AI_CHECKER_MODEL` | `claude-opus-5-5` | Claude model. |
| `AI_CHECKER_EFFORT` | `medium` | `low`, `medium`, `high`, `xhigh` or `max`. Higher is slower and costs more. |
| `APP_PASSWORD` | none | Browser password prompt for the whole app (any username). **Set it on every public deployment.** |
| `CLEAN_AUTHOR` | empty | Author written into cleaned files. Empty clears the author field. |
| `CLEAN_CONCURRENCY` | `4` | How many parts of a long document are rewritten in parallel. |
| `MAX_UPLOAD_MB` | `20` | Largest upload. |
| `MAX_DOCUMENT_CHARS` | `200000` | Most characters of text per document for Claude. |
| `PUBLISH_PORT` | `8000` | Port on the host that Docker Compose publishes. |
| `HOST`, `PORT` | `127.0.0.1`, `8000` | Only used when running `server.py` directly. |

Real environment variables take precedence over `.env`. Never commit `.env`; it is in `.gitignore` and `.dockerignore`.

## Run with Docker

```bash
cp .env.example .env      # then edit it
docker compose up -d --build
```

Open `http://localhost:8000` (or the `PUBLISH_PORT` you chose). Stop with `docker compose down`.

Without Compose:

```bash
docker build -t ai-document-checker .
docker run -d -p 8000:8000 --env-file .env -e HOST=0.0.0.0 -e PORT=8000 ai-document-checker
```

On a hosting platform (Render, Railway, Fly.io, Google Cloud Run, a VPS), deploy from this repository's `Dockerfile`,
enter the variables from `.env.example` in the platform's settings (the API key as a secret), and use `/healthz` as
the health-check path; it answers without a password. Use the platform's HTTPS when you set a password.

Cleaning a long document makes several Claude calls and can take a few minutes, so allow long request timeouts on
your proxy or platform.

## Run without Docker

```bash
pip install -r requirements.txt
cp .env.example .env      # then edit it
python server.py          # open http://127.0.0.1:8000
```

## Tests

```bash
node --test tests/heuristics.test.mjs tests/history.test.mjs
python -m unittest discover -s tests
```

## Files

- `server.py`: web server, settings, password protection, Claude review and cleaning.
- `documents.py`: reads and writes `.docx`, `.pptx` and text, rewrites paragraphs in place and scrubs metadata.
- `traces.py`: removes hidden characters, look-alike letters and image metadata.
- `static/heuristics.js`: instant-check signals, phrase lists (EN/NL) and weights. Tune them here.
- `static/history.js`: browser-side history.
- `static/app.js`: menu and routing, checker, cleaning, history page.
- `Dockerfile`, `docker-compose.yml`, `.env.example`: deployment.
