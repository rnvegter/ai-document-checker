# AI Document Checker

A self-contained web app that checks Word, PowerPoint and text documents (English and Dutch) for AI-sounding writing,
reviews them with Claude, and produces a clean version without AI traces.

- [Features](#features)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Installation](#installation)
- [Installing on Proxmox VE](docs/PROXMOX.md)
- [Configuration](#configuration)
- [Updating](#updating)
- [Day-to-day commands](#day-to-day-commands)
- [HTTPS and reverse proxy](#https-and-reverse-proxy)
- [Hosting platforms](#hosting-platforms)
- [Troubleshooting](#troubleshooting)
- [Security and privacy](#security-and-privacy)
- [Development](#development)

## Features

- **Read documents:** paste text, or upload `.docx`, `.pptx`, `.txt` or `.md`.
  PowerPoint slide text, tables and speaker notes are read and marked per slide.
- **Instant check:** runs in the browser, no API key needed. Scores eight signals and highlights them in the text:
  stock AI phrases ("delve", "plays a crucial role", "in het huidige digitale landschap"), uniform sentence length,
  stock transitions ("Moreover", "Bovendien"), em dashes, "not X but Y" constructions, lists of three,
  uniform paragraphs and chatbot formatting.
- **Deep check with Claude:** an AI-likelihood verdict, flagged passages with a reason and a rewrite in the
  document's own language, and feedback on clarity, structure, tone, concision and grammar.
  **Apply rewrite** swaps a passage into your text.
- **Clean document:** rewrites AI-sounding paragraphs and returns a clean file in the same format.
  - Facts, names, numbers, dates, references and legal wording are kept; paragraphs are never merged or split.
  - Word and PowerPoint files keep their layout, styles, tables, headers and speaker notes. Within a rewritten
    paragraph the formatting of the first run is applied to the whole paragraph, so check paragraphs that mixed
    bold text or links.
  - **Hidden characters** are removed (zero-width characters, text-direction controls, Unicode tag characters,
    variation selectors, unusual spaces). Look-alike Cyrillic or Greek letters inside Latin words and
    fullwidth or styled letters (𝐀, Ａ) become normal letters. Real Greek or Cyrillic words, Dutch accents,
    `ĳ` and emoji are left alone.
  - **Image metadata** (EXIF, XMP, IPTC, C2PA content credentials, comments) is removed from embedded JPEG, PNG and
    WebP images without re-encoding them. EXIF stays on a photo that needs it to display the right way up.
  - **File metadata:** author and "last modified by" are reset (or set to `CLEAN_AUTHOR`), the comments field is
    cleared, and custom properties that tag the file as AI-made are removed. Sensitivity labels stay.
  - A **report** lists every hidden trace that was removed.
- **History:** every check is saved in the browser. Search, reopen, rename, delete and export to JSON.
- **Menu:** sidebar with New check, Checker, History, How it works and recent documents; a ☰ menu on phones.
- **Password protection** for the whole app, and light and dark mode.

### Limits

No AI detector is reliable. Formal, templated or non-native writing can look machine-made, and edited AI text can
look human. Use the scores to improve a text, not as a verdict on a person.

Statistical watermarks hidden in word choice (such as SynthID-Text) can't be detected here. Rewriting usually
weakens them, but nothing guarantees they are gone, especially in paragraphs left unchanged. Pixel-level image
watermarks are not touched. Removing traces does not change any obligation to disclose AI use, for example under
the EU AI Act or a client's terms.

## Requirements

| To run with | You need |
|---|---|
| Docker (recommended) | [Docker Engine](https://docs.docker.com/engine/install/) with the Compose plugin, or Docker Desktop on Windows/macOS. Git. |
| Python directly | Python 3.10 or newer, pip, Git. |
| Claude features | An Anthropic API key from [console.anthropic.com](https://console.anthropic.com/). Without one, only the instant check works. |

The app needs outbound HTTPS access to `api.anthropic.com` for Claude features. It stores nothing on the server.

## Quick start

```bash
git clone https://github.com/rnvegter/ai-document-checker.git
cd ai-document-checker
cp .env.example .env          # then set ANTHROPIC_API_KEY and APP_PASSWORD in .env
docker compose up -d --build
```

Open <http://localhost:8000> and log in with any username and your `APP_PASSWORD`.

## Installation

### Option 1: Docker on a Linux server (recommended)

1. Install Docker and Git (Ubuntu/Debian example; see the Docker docs for other systems):

   ```bash
   sudo apt-get update
   sudo apt-get install -y git ca-certificates curl
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker "$USER"   # log out and back in afterwards
   ```

2. Get the code and create your settings file:

   ```bash
   git clone https://github.com/rnvegter/ai-document-checker.git
   cd ai-document-checker
   cp .env.example .env
   chmod 600 .env
   nano .env                         # set ANTHROPIC_API_KEY, APP_PASSWORD and anything else
   ```

3. Build and start:

   ```bash
   docker compose up -d --build
   ```

4. Check that it runs:

   ```bash
   docker compose ps                 # STATUS should show "healthy" after about 30 seconds
   curl http://localhost:8000/healthz
   ```

The container restarts automatically after a crash or reboot (`restart: unless-stopped`).
Put it behind HTTPS before exposing it to the internet; see [HTTPS and reverse proxy](#https-and-reverse-proxy).

### Option 2: Docker Desktop on Windows or macOS

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and [Git](https://git-scm.com/downloads).
2. In a terminal (PowerShell on Windows):

   ```bash
   git clone https://github.com/rnvegter/ai-document-checker.git
   cd ai-document-checker
   copy .env.example .env            # Windows; use "cp" on macOS
   notepad .env                      # Windows; use "open -e .env" on macOS
   docker compose up -d --build
   ```

3. Open <http://localhost:8000>.

### Option 3: Proxmox VE

One line in the Proxmox host shell creates a Debian LXC container with Docker and the app:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/rnvegter/ai-document-checker/main/scripts/proxmox-install.sh)"
```

The [Proxmox installation manual](docs/PROXMOX.md) explains the questions it asks and how to run it without
questions. It also covers manual installation: an LXC container with Docker
(recommended), a virtual machine with Docker, and a lightweight LXC container without Docker, plus updates,
snapshots, backups and HTTPS.

### Option 4: Python without Docker

```bash
git clone https://github.com/rnvegter/ai-document-checker.git
cd ai-document-checker
python3 -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                  # then edit it
python server.py                      # http://127.0.0.1:8000
```

`server.py` reads `.env` from its own folder. Use `HOST=0.0.0.0` in `.env` to accept connections from other
machines (and set `APP_PASSWORD`).

To keep it running on a Linux server without Docker, create `/etc/systemd/system/ai-checker.service`
(adjust the user and paths):

```ini
[Unit]
Description=AI Document Checker
After=network-online.target

[Service]
User=aichecker
WorkingDirectory=/opt/ai-document-checker
ExecStart=/opt/ai-document-checker/.venv/bin/python server.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ai-checker
```

## Configuration

All settings live in `.env`. `.env.example` lists and explains every variable.

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Enables Deep check and Clean document. |
| `AI_CHECKER_MODEL` | `claude-opus-5-5` | Claude model. |
| `AI_CHECKER_EFFORT` | `medium` | `low`, `medium`, `high`, `xhigh` or `max`. Higher is slower and costs more. |
| `APP_PASSWORD` | none | Password for the whole app (any username). **Set it on every shared or public deployment.** |
| `CLEAN_AUTHOR` | empty | Author written into cleaned files. Empty clears the author field. |
| `CLEAN_CONCURRENCY` | `4` | How many parts of a long document are rewritten in parallel. |
| `MAX_UPLOAD_MB` | `20` | Largest upload. |
| `MAX_DOCUMENT_CHARS` | `200000` | Most characters of text per document sent to Claude. |
| `PUBLISH_PORT` | `8000` | Host port that Docker Compose publishes. |
| `HOST`, `PORT` | `127.0.0.1`, `8000` | Only used when running `server.py` directly. Inside Docker the app always listens on `0.0.0.0:8000`. |

Real environment variables take precedence over `.env`.

After changing `.env`, apply it:

```bash
docker compose up -d                  # recreates the container with the new settings
# without Docker: stop and start server.py again (sudo systemctl restart ai-checker)
```

## Updating

Your settings in `.env` are not tracked by Git, so updating never overwrites them. History lives in each
user's browser and is not affected by updates.

### With Docker

```bash
cd ai-document-checker
git pull
docker compose up -d --build
docker image prune -f                 # optional: remove the old image layers
```

Check the result with `docker compose ps` and `docker compose logs --tail 20`.

After updating, compare your `.env` with `.env.example` for new settings:

```bash
diff <(grep -o '^[A-Z_]*=' .env.example | sort) <(grep -o '^[A-Z_]*=' .env | sort)
```

Lines starting with `<` are settings you don't have yet; copy them from `.env.example` if you want to change their
defaults.

### Without Docker

```bash
cd ai-document-checker
git pull
source .venv/bin/activate             # Windows: .venv\Scripts\activate
pip install -r requirements.txt --upgrade
sudo systemctl restart ai-checker     # or stop and start "python server.py" yourself
```

### Roll back to an earlier version

```bash
git log --oneline -10                 # find the commit you want
git checkout <commit>
docker compose up -d --build          # without Docker: restart server.py
git checkout main                     # later, to return to the latest version
```

### Update the base image only

To pick up security fixes in Python and the libraries without code changes:

```bash
docker compose build --pull --no-cache
docker compose up -d
```

## Day-to-day commands

| Task | Docker | Without Docker (systemd) |
|---|---|---|
| Start | `docker compose up -d` | `sudo systemctl start ai-checker` |
| Stop | `docker compose down` | `sudo systemctl stop ai-checker` |
| Restart | `docker compose restart` | `sudo systemctl restart ai-checker` |
| Status | `docker compose ps` | `systemctl status ai-checker` |
| Logs | `docker compose logs -f --tail 100` | `journalctl -u ai-checker -f` |
| Health | `curl http://localhost:8000/healthz` | same |

## HTTPS and reverse proxy

Run the app behind HTTPS whenever it is reachable from other machines: the password is sent with every request.

**Caddy** (gets certificates automatically). `/etc/caddy/Caddyfile`:

```
checker.example.com {
    request_body {
        max_size 25MB
    }
    reverse_proxy localhost:8000 {
        transport http {
            read_timeout 10m
        }
    }
}
```

**nginx:**

```nginx
server {
    listen 443 ssl;
    server_name checker.example.com;
    # ssl_certificate ...; ssl_certificate_key ...;

    client_max_body_size 25m;          # at least MAX_UPLOAD_MB
    proxy_read_timeout 600s;           # cleaning long documents can take minutes

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
}
```

When a reverse proxy runs on the same machine, publish the app on localhost only by changing the port line in
`docker-compose.yml` to `"127.0.0.1:${PUBLISH_PORT:-8000}:8000"`.

## Hosting platforms

Render, Railway, Fly.io, Google Cloud Run and similar platforms can build the `Dockerfile` directly:

1. Create a new service from this GitHub repository (Docker runtime).
2. Add the variables from `.env.example` in the platform's settings; store `ANTHROPIC_API_KEY` as a secret.
   Most platforms set `PORT` themselves; the app listens on it.
3. Set the health-check path to `/healthz` (it answers without a password).
4. Allow request timeouts of several minutes, because cleaning long documents makes several Claude calls.

To update, push to the repository (or press the platform's redeploy button).

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "Deep check" and "Clean document" are greyed out | No API key reached the app. Check `ANTHROPIC_API_KEY` in `.env`, then `docker compose up -d`. |
| "The Anthropic API key was rejected." | The key is wrong or revoked. Create a new one in the Anthropic Console. |
| "Could not reach the Anthropic API." | The server has no outbound HTTPS access to `api.anthropic.com`. Check firewall or proxy settings. |
| "Rate limited by the Anthropic API." | Too many requests for your account's limits. Wait a minute, or lower `CLEAN_CONCURRENCY`. |
| "The upload is too large." | Raise `MAX_UPLOAD_MB` (and your reverse proxy's body size limit). |
| Cleaning stops with a timeout error | Your proxy or platform cut the request off. Raise its timeout to 10 minutes. |
| The browser keeps asking for a password | Use any username and exactly the `APP_PASSWORD` value. |
| Port 8000 is already in use | Set `PUBLISH_PORT` in `.env` to another port and run `docker compose up -d`. |
| History is gone | History is stored per browser. Private windows and clearing site data remove it. Use **Export** on the History page to keep a copy. |
| Old `.doc` or `.ppt` file rejected | Save it as `.docx` or `.pptx` first. |

## Security and privacy

- Set `APP_PASSWORD` and use HTTPS on any deployment others can reach.
- `.env` holds your API key: keep it out of Git (it is in `.gitignore`), and restrict it with `chmod 600 .env`.
- The container runs as a non-root user and sends security headers (Content Security Policy, no-sniff, no referrer).
- Documents are processed in memory and never written to disk or logs. The instant check stays in the browser.
  Deep check and Clean document send the text to the Anthropic API.
- History is stored only in each user's browser.

## Development

Run the tests:

```bash
pip install -r requirements.txt
python -m unittest discover -s tests
node --test tests/heuristics.test.mjs tests/history.test.mjs
```

Project structure:

| Path | Purpose |
|---|---|
| `server.py` | Web server, settings, password protection, Claude review and cleaning. |
| `documents.py` | Reads and writes `.docx`, `.pptx` and text; rewrites paragraphs in place; scrubs metadata. |
| `traces.py` | Removes hidden characters, look-alike letters and image metadata. |
| `static/heuristics.js` | Instant-check signals, phrase lists (EN/NL) and weights. |
| `static/history.js` | Browser-side history. |
| `static/app.js` | Menu and routing, checker, cleaning, history page. |
| `static/style.css` | Colours, layout and themes. |
| `Dockerfile`, `docker-compose.yml`, `.env.example` | Deployment. |
| `docs/PROXMOX.md` | Installation manual for Proxmox VE. |
| `scripts/proxmox-install.sh` | One-line installer for Proxmox VE. |
| `tests/` | Python and JavaScript tests. |
