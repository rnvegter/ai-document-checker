#!/usr/bin/env python3
"""Web server for the AI document checker.

Serves the app in ./static and these endpoints:
  POST /api/review   deep check with Claude (needs ANTHROPIC_API_KEY)
  POST /api/clean    rewrite a document without AI traces; returns the cleaned file
  POST /api/extract  plain text from an uploaded .docx/.pptx/.txt/.md file
  GET  /api/health   whether Claude is configured
  GET  /healthz      liveness probe for hosting platforms (no password)

Settings come from environment variables or a .env file next to this script;
see .env.example. Set APP_PASSWORD to put the whole app behind a password.
"""
import argparse
import base64
import binascii
import hmac
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import anthropic

import documents


def load_env_file(path):
    """Read KEY=VALUE lines into os.environ without overriding real variables."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


load_env_file(Path(__file__).parent / ".env")

STATIC_DIR = Path(__file__).parent / "static"
MODEL = os.environ.get("AI_CHECKER_MODEL") or "claude-opus-5-5"
EFFORT = os.environ.get("AI_CHECKER_EFFORT") or "medium"
MAX_CHARS = int(os.environ.get("MAX_DOCUMENT_CHARS") or 200_000)
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB") or 20) * 1024 * 1024
CLEAN_AUTHOR = os.environ.get("CLEAN_AUTHOR", "")
CLEAN_CONCURRENCY = int(os.environ.get("CLEAN_CONCURRENCY") or 4)
CLEAN_CHUNK_CHARS = 12_000
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = """You review written documents in English or Dutch. You do two jobs at once.

1. Judge how likely it is that the text was generated or heavily edited by an AI model.
   Look for: stock phrases ("delve", "tapestry", "in today's fast-paced world",
   "speelt een cruciale rol", "in het huidige digitale landschap"), uniform sentence
   rhythm, formulaic transitions, "not X but Y" constructions, reflexive lists of three,
   em dashes, generic claims without concrete detail, hedged everything-is-balanced
   conclusions, and chatbot formatting. Weigh against human tells: specific facts,
   names, numbers, idiosyncratic word choice, uneven rhythm, small errors, a clear opinion.
   No detector is reliable. Use "uncertain" when the evidence is thin, never claim proof,
   and remember that formal or non-native human writing can look machine-like.

2. Review the writing itself for clarity, structure, tone, concision and grammar.

Rules:
- Every "quote" must be copied exactly, character for character, from the document so it
  can be found and highlighted. Keep quotes short (one sentence or less).
- Write every "rewrite" and "suggestion" in the document's own language.
  Rewrites must keep the meaning and every factual claim; never invent facts.
- Write "summary", "reason" and "issue" in the document's language as well.
- ai_likelihood is an integer from 0 (certainly human) to 100 (certainly AI).
- Flag at most 12 passages and 12 feedback items, most important first."""

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "ai_likelihood": {"type": "integer"},
        "verdict": {"type": "string", "enum": ["likely_human", "mixed", "likely_ai", "uncertain"]},
        "language": {"type": "string"},
        "summary": {"type": "string"},
        "passages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string"},
                    "reason": {"type": "string"},
                    "rewrite": {"type": "string"},
                },
                "required": ["quote", "reason", "rewrite"],
                "additionalProperties": False,
            },
        },
        "feedback": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["clarity", "structure", "tone", "concision", "grammar", "other"],
                    },
                    "quote": {"type": "string"},
                    "issue": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["category", "quote", "issue", "suggestion"],
                "additionalProperties": False,
            },
        },
        "strengths": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ai_likelihood", "verdict", "language", "summary", "passages", "feedback", "strengths"],
    "additionalProperties": False,
}


CLEAN_PROMPT = """You remove the traces of AI writing from documents in English or Dutch,
so that the result reads as if a skilled human professional wrote it.

You get a JSON list of paragraphs from one document (possibly part of a longer one).
Each has an "id", its "text" and sometimes "where" (for example a slide number).
Rewrite the paragraphs that read as machine-written:
- Replace stock AI phrases ("delve", "tapestry", "plays a crucial role", "in today's
  fast-paced world", "speelt een cruciale rol", "in het huidige digitale landschap",
  "een breed scala aan", "het is belangrijk om op te merken") with plain, specific wording.
- Remove em dashes; use a comma, colon, parentheses or a new sentence instead.
- Cut formulaic connectors ("Moreover", "Furthermore", "Additionally", "Bovendien",
  "Daarnaast", "Kortom"), "not X but Y" constructions, reflexive lists of three,
  inflated adjectives, filler hedges, generic summaries and chatbot sign-offs.
- Vary sentence length the way a person does. Prefer active voice and concrete verbs.

Rules:
- Keep the document's language. Dutch stays Dutch, English stays English.
- Keep the meaning and every fact: names, numbers, dates, amounts, references, URLs,
  quotes, defined terms, legal wording and caveats stay exactly as they are.
  Never add facts, examples or opinions.
- One paragraph in, one paragraph out: never merge, split or reorder paragraphs.
  Headings, titles, labels and table cells stay short; change them only if they contain
  an AI tell. Do not add markdown, bullets or numbering; the layout already has them.
- Keep roughly the same length; shorter is fine when you cut filler.
- Return only the paragraphs you changed, with their original id."""

CLEAN_SCHEMA = {
    "type": "object",
    "properties": {
        "paragraphs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["paragraphs"],
    "additionalProperties": False,
}


class ReviewError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


@contextmanager
def claude_errors():
    """Turn Anthropic SDK errors into ReviewErrors with a user-facing message."""
    try:
        yield
    except anthropic.AuthenticationError:
        raise ReviewError(HTTPStatus.UNAUTHORIZED, "The Anthropic API key was rejected.")
    except anthropic.RateLimitError:
        raise ReviewError(HTTPStatus.TOO_MANY_REQUESTS, "Rate limited by the Anthropic API. Try again shortly.")
    except anthropic.BadRequestError as e:
        raise ReviewError(HTTPStatus.BAD_REQUEST, f"Claude rejected the request: {e.message}")
    except anthropic.APIStatusError as e:
        raise ReviewError(HTTPStatus.BAD_GATEWAY, f"Anthropic API error ({e.status_code}): {e.message}")
    except anthropic.APIConnectionError:
        raise ReviewError(HTTPStatus.BAD_GATEWAY, "Could not reach the Anthropic API.")


def final_json(response, action):
    """Parse the structured-output JSON of a response, checking why it stopped."""
    if response.stop_reason == "refusal":
        raise ReviewError(HTTPStatus.UNPROCESSABLE_ENTITY, f"Claude declined to {action} this document.")
    if response.stop_reason == "max_tokens":
        raise ReviewError(HTTPStatus.BAD_GATEWAY, f"Claude's answer was cut off while trying to {action} this document.")
    raw = next((b.text for b in response.content if b.type == "text"), None)
    if raw is None:
        raise ReviewError(HTTPStatus.BAD_GATEWAY, "Claude returned an empty answer.")
    return json.loads(raw)


def review_document(client, text, heuristics=""):
    """Ask Claude for an AI-likelihood judgement and writing feedback."""
    user = f"<document>\n{text}\n</document>"
    if heuristics:
        user += (
            "\n\nAutomated heuristic signals for this document (crude, may be wrong):\n"
            f"<heuristics>\n{heuristics}\n</heuristics>"
        )
    with claude_errors():
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            system=SYSTEM_PROMPT,
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": REVIEW_SCHEMA}},
            messages=[{"role": "user", "content": user}],
        )
    result = final_json(response, "review")
    result["ai_likelihood"] = max(0, min(100, int(result["ai_likelihood"])))
    result["model"] = response.model
    return result


def _chunks(units, max_chars=CLEAN_CHUNK_CHARS):
    chunk, size = [], 0
    for unit in units:
        if chunk and size + len(unit.text) > max_chars:
            yield chunk
            chunk, size = [], 0
        chunk.append(unit)
        size += len(unit.text)
    if chunk:
        yield chunk


def _rewrite_chunk(client, units):
    paragraphs = [{"id": u.id, "text": u.text, **({"where": u.location} if u.location else {})} for u in units]
    with claude_errors():
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=32000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            system=CLEAN_PROMPT,
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": CLEAN_SCHEMA}},
            messages=[{"role": "user", "content": json.dumps(paragraphs, ensure_ascii=False)}],
        ) as stream:
            response = stream.get_final_message()
    valid = {u.id for u in units}
    return {p["id"]: p["text"] for p in final_json(response, "clean")["paragraphs"] if p["id"] in valid}


def clean_document(client, doc):
    """Rewrite AI-sounding paragraphs in place and remove hidden traces.

    Returns (number of paragraphs rewritten, report of traces removed).
    """
    rewrites = {}
    with ThreadPoolExecutor(max_workers=max(1, CLEAN_CONCURRENCY)) as pool:
        for part in pool.map(lambda chunk: _rewrite_chunk(client, chunk), list(_chunks(doc.units))):
            rewrites.update(part)
    changed = doc.apply(rewrites)
    return changed, doc.scrub(CLEAN_AUTHOR)


def load_document(filename, data):
    try:
        doc = documents.load(filename, data)
    except documents.UnsupportedDocument as e:
        raise ReviewError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, str(e))
    if not doc.units:
        raise ReviewError(HTTPStatus.BAD_REQUEST, "The document contains no text.")
    return doc


def extract_text(filename, data):
    """Return the plain text of a .docx, .pptx, .txt or .md upload."""
    return load_document(filename, data).review_text()


CSP = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
)


class Handler(SimpleHTTPRequestHandler):
    client = None
    password = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def authorized(self):
        if not self.password:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            _, _, given = base64.b64decode(header[6:], validate=True).decode().partition(":")
        except (binascii.Error, UnicodeDecodeError):
            return False
        return hmac.compare_digest(given.encode(), self.password.encode())

    def require_auth(self):
        """Send a 401 and return False unless the request carries the app password."""
        if self.authorized():
            return True
        body = b"Password required"
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="AI Document Checker", charset="UTF-8"')
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return False

    def send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def filename(self, default=""):
        return unquote(self.headers.get("X-Filename", "")) or default

    def read_body(self, limit):
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            raise ReviewError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "The upload is too large.")
        return self.rfile.read(length)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            self.send_json(HTTPStatus.OK, {"ok": True})
            return
        if not self.require_auth():
            return
        if path == "/api/health":
            self.send_json(HTTPStatus.OK, {"claude": self.client is not None, "model": MODEL})
            return
        super().do_GET()

    def do_HEAD(self):
        if self.require_auth():
            super().do_HEAD()

    def do_POST(self):
        if not self.require_auth():
            return
        path = urlsplit(self.path).path
        try:
            if path == "/api/review":
                self.handle_review()
            elif path == "/api/extract":
                self.handle_extract()
            elif path == "/api/clean":
                self.handle_clean()
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
        except ReviewError as e:
            self.send_json(e.status, {"error": e.message})

    def handle_review(self):
        if self.client is None:
            raise ReviewError(HTTPStatus.SERVICE_UNAVAILABLE, "No ANTHROPIC_API_KEY configured on the server.")
        try:
            payload = json.loads(self.read_body(MAX_CHARS * 4 + 65536))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ReviewError(HTTPStatus.BAD_REQUEST, "Request body must be JSON.")
        text = str(payload.get("text", "")).strip()
        if not text:
            raise ReviewError(HTTPStatus.BAD_REQUEST, "There is no text to check.")
        if len(text) > MAX_CHARS:
            raise ReviewError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                f"The document has {len(text):,} characters; the limit is {MAX_CHARS:,}. Split it up.",
            )
        result = review_document(self.client, text, str(payload.get("heuristics", "")))
        self.send_json(HTTPStatus.OK, result)

    def handle_extract(self):
        text = extract_text(self.filename(), self.read_body(MAX_UPLOAD_BYTES))
        self.send_json(HTTPStatus.OK, {"text": text})

    def handle_clean(self):
        if self.client is None:
            raise ReviewError(HTTPStatus.SERVICE_UNAVAILABLE, "No ANTHROPIC_API_KEY configured on the server.")
        doc = load_document(self.filename("document.txt"), self.read_body(MAX_UPLOAD_BYTES))
        size = sum(len(u.text) for u in doc.units)
        if size > MAX_CHARS:
            raise ReviewError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                f"The document has {size:,} characters; the limit is {MAX_CHARS:,}. Split it up.",
            )
        changed, traces = clean_document(self.client, doc)
        self.send_json(HTTPStatus.OK, {
            "filename": doc.clean_filename,
            "mime": doc.mime,
            "file": base64.b64encode(doc.save()).decode(),
            "text": doc.review_text(),
            "kind": doc.kind,
            "changed": changed,
            "total": len(doc.units),
            "traces": traces,
        })


def main():
    parser = argparse.ArgumentParser(description="Run the AI document checker web app.")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()

    Handler.password = os.environ.get("APP_PASSWORD") or None

    client = anthropic.Anthropic()
    if client.api_key or client.auth_token or client.credentials:
        Handler.client = client
    else:
        print("No Anthropic credentials found: running with offline heuristics only.", file=sys.stderr)
    if Handler.client and not Handler.password and args.host not in ("127.0.0.1", "localhost"):
        print("Warning: anyone who can reach this server can use your Claude API key. Set APP_PASSWORD.", file=sys.stderr)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"AI checker running on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
