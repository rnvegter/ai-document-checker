import io
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402

REVIEW = {
    "ai_likelihood": 140,
    "verdict": "likely_ai",
    "language": "en",
    "summary": "Generic phrasing throughout.",
    "passages": [{"quote": "plays a crucial role", "reason": "Stock phrase", "rewrite": "matters"}],
    "feedback": [],
    "strengths": [],
}


class FakeMessages:
    def __init__(self, stop_reason="end_turn", text=json.dumps(REVIEW)):
        self.stop_reason = stop_reason
        self.text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            model="claude-opus-5-5",
            content=[SimpleNamespace(type="text", text=self.text)],
        )


def fake_client(**kwargs):
    return SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages(**kwargs)))


def make_docx(paragraphs):
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = f'<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


class ReviewTests(unittest.TestCase):
    def test_parses_and_clamps_review(self):
        client = fake_client()
        result = server.review_document(client, "Tech plays a crucial role.", "score 80")
        self.assertEqual(result["ai_likelihood"], 100)
        self.assertEqual(result["model"], "claude-opus-5-5")
        call = client.beta.messages.calls[0]
        self.assertIn("<heuristics>", call["messages"][0]["content"])
        self.assertEqual(call["output_config"]["format"]["type"], "json_schema")

    def test_refusal_is_reported(self):
        with self.assertRaises(server.ReviewError) as ctx:
            server.review_document(fake_client(stop_reason="refusal"), "text")
        self.assertEqual(ctx.exception.status, 422)

    def test_truncation_is_reported(self):
        with self.assertRaises(server.ReviewError):
            server.review_document(fake_client(stop_reason="max_tokens"), "text")


class ExtractTests(unittest.TestCase):
    def test_docx(self):
        text = server.extract_text("a.DOCX", make_docx(["First para.", "", "Second para."]))
        self.assertEqual(text, "First para.\n\nSecond para.")

    def test_bad_docx(self):
        with self.assertRaises(server.ReviewError):
            server.extract_text("a.docx", b"not a zip")

    def test_unsupported(self):
        with self.assertRaises(server.ReviewError) as ctx:
            server.extract_text("a.pdf", b"")
        self.assertEqual(ctx.exception.status, 415)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.Handler.client = fake_client()
        server.Handler.log_message = lambda *a: None
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        server.Handler.client = None

    def post(self, path, body, headers=None):
        req = urllib.request.Request(self.base + path, data=body, headers=headers or {}, method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_serves_page_and_health(self):
        with urllib.request.urlopen(self.base + "/") as r:
            self.assertIn(b"AI Document Checker", r.read())
        with urllib.request.urlopen(self.base + "/api/health") as r:
            self.assertTrue(json.loads(r.read())["claude"])

    def test_review_endpoint(self):
        status, data = self.post("/api/review", json.dumps({"text": "Hello world."}).encode())
        self.assertEqual(status, 200)
        self.assertEqual(data["verdict"], "likely_ai")

    def test_review_rejects_empty_and_huge(self):
        self.assertEqual(self.post("/api/review", b'{"text": "  "}')[0], 400)
        huge = json.dumps({"text": "a" * (server.MAX_CHARS + 1)}).encode()
        self.assertEqual(self.post("/api/review", huge)[0], 413)

    def test_extract_endpoint(self):
        status, data = self.post("/api/extract", make_docx(["Hoi."]), {"X-Filename": "x.docx"})
        self.assertEqual((status, data["text"]), (200, "Hoi."))


if __name__ == "__main__":
    unittest.main()
