#!/usr/bin/env python3
"""Local web server for the AI document checker.

Serves the page in ./static and two JSON endpoints:
  POST /api/review   deep check with Claude (needs ANTHROPIC_API_KEY)
  POST /api/extract  plain text from an uploaded .docx/.txt/.md file
"""
import argparse
import io
import json
import os
import re
import sys
import zipfile
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.etree import ElementTree

import anthropic

STATIC_DIR = Path(__file__).parent / "static"
MODEL = os.environ.get("AI_CHECKER_MODEL", "claude-opus-5-5")
MAX_CHARS = 200_000
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

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


class ReviewError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def review_document(client, text, heuristics=""):
    """Ask Claude for an AI-likelihood judgement and writing feedback."""
    user = f"<document>\n{text}\n</document>"
    if heuristics:
        user += (
            "\n\nAutomated heuristic signals for this document (crude, may be wrong):\n"
            f"<heuristics>\n{heuristics}\n</heuristics>"
        )
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM_PROMPT,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": REVIEW_SCHEMA}},
            messages=[{"role": "user", "content": user}],
        )
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

    if response.stop_reason == "refusal":
        raise ReviewError(HTTPStatus.UNPROCESSABLE_ENTITY, "Claude declined to review this document.")
    if response.stop_reason == "max_tokens":
        raise ReviewError(HTTPStatus.BAD_GATEWAY, "The review was cut off. Try a shorter document.")
    raw = next((b.text for b in response.content if b.type == "text"), None)
    if raw is None:
        raise ReviewError(HTTPStatus.BAD_GATEWAY, "Claude returned no review.")
    result = json.loads(raw)
    result["ai_likelihood"] = max(0, min(100, int(result["ai_likelihood"])))
    result["model"] = response.model
    return result


def extract_text(filename, data):
    """Return the plain text of a .docx, .txt or .md upload."""
    name = filename.lower()
    if name.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                xml = z.read("word/document.xml")
        except (zipfile.BadZipFile, KeyError):
            raise ReviewError(HTTPStatus.BAD_REQUEST, "That .docx file could not be read.")
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paragraphs = []
        for p in ElementTree.fromstring(xml).iter(f"{ns}p"):
            parts = []
            for node in p.iter():
                if node.tag == f"{ns}t":
                    parts.append(node.text or "")
                elif node.tag == f"{ns}tab":
                    parts.append("\t")
                elif node.tag in (f"{ns}br", f"{ns}cr"):
                    parts.append("\n")
            paragraphs.append("".join(parts))
        text = "\n\n".join(p for p in paragraphs if p.strip())
        return re.sub(r"\n{3,}", "\n\n", text)
    if name.endswith((".txt", ".md", ".markdown")):
        return data.decode("utf-8", errors="replace")
    raise ReviewError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Upload a .docx, .txt or .md file.")


class Handler(SimpleHTTPRequestHandler):
    client = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self, limit):
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            raise ReviewError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "The upload is too large.")
        return self.rfile.read(length)

    def do_GET(self):
        if self.path == "/api/health":
            self.send_json(HTTPStatus.OK, {"claude": self.client is not None, "model": MODEL})
            return
        super().do_GET()

    def do_POST(self):
        try:
            if self.path == "/api/review":
                self.handle_review()
            elif self.path == "/api/extract":
                self.handle_extract()
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
        filename = self.headers.get("X-Filename", "")
        text = extract_text(filename, self.read_body(MAX_UPLOAD_BYTES))
        self.send_json(HTTPStatus.OK, {"text": text})


def main():
    parser = argparse.ArgumentParser(description="Run the AI document checker web page.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    client = anthropic.Anthropic()
    if client.api_key or client.auth_token or client.credentials:
        Handler.client = client
    else:
        print("No Anthropic credentials found: running with offline heuristics only.", file=sys.stderr)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"AI checker running on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
