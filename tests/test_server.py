import base64
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import documents  # noqa: E402
import server  # noqa: E402
from helpers import fake_client, make_docx, make_pptx  # noqa: E402

REVIEW = {
    "ai_likelihood": 140,
    "verdict": "likely_ai",
    "language": "en",
    "summary": "Generic phrasing throughout.",
    "passages": [{"quote": "plays a crucial role", "reason": "Stock phrase", "rewrite": "matters"}],
    "feedback": [],
    "strengths": [],
}


def humanize(text):
    return text.replace("Moreover, synergy unlocks the full potential of teams.", "Teams work better together.") if "Moreover" in text else None


class ReviewTests(unittest.TestCase):
    def test_parses_and_clamps_review(self):
        client = fake_client(review=REVIEW)
        result = server.review_document(client, "Tech plays a crucial role.", "score 80")
        self.assertEqual(result["ai_likelihood"], 100)
        self.assertEqual(result["model"], "claude-opus-5-5")
        call = client.beta.messages.calls[0]
        self.assertIn("<heuristics>", call["messages"][0]["content"])
        self.assertEqual(call["output_config"]["format"]["type"], "json_schema")

    def test_refusal_is_reported(self):
        with self.assertRaises(server.ReviewError) as ctx:
            server.review_document(fake_client(review=REVIEW, stop_reason="refusal"), "text")
        self.assertEqual(ctx.exception.status, 422)

    def test_truncation_is_reported(self):
        with self.assertRaises(server.ReviewError):
            server.review_document(fake_client(review=REVIEW, stop_reason="max_tokens"), "text")


class CleanTests(unittest.TestCase):
    def test_cleans_pptx_in_place(self):
        client = fake_client(rewrite=humanize)
        doc = documents.load("deck.pptx", make_pptx())
        self.assertEqual(server.clean_document(client, doc)[0], 1)
        texts = [u.text for u in documents.load("deck.pptx", doc.save()).units]
        self.assertIn("Teams work better together.", texts)
        self.assertIn("Budget: €40,000", texts)
        sent = json.loads(client.beta.messages.calls[0]["messages"][0]["content"])
        self.assertEqual(sent[0], {"id": 0, "text": "Quarterly plan", "where": "Slide 1"})

    def test_long_documents_are_split_into_chunks(self):
        paras = [f"Paragraph {i} " + "x" * 3000 for i in range(10)]
        client = fake_client(rewrite=lambda t: t.replace("x", "y"))
        doc = documents.load("long.docx", make_docx(paras))
        self.assertEqual(server.clean_document(client, doc)[0], 10)
        self.assertGreater(len(client.beta.messages.calls), 1)
        self.assertTrue(all("x" not in u.text for u in doc.units))

    def test_refusal_while_cleaning(self):
        doc = documents.load("a.txt", b"Moreover, synergy.")
        with self.assertRaises(server.ReviewError) as ctx:
            server.clean_document(fake_client(stop_reason="refusal"), doc)
        self.assertEqual(ctx.exception.status, 422)


class EnvFileTests(unittest.TestCase):
    def test_loads_without_overriding(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text('# comment\nAIC_TEST_A=one\nexport AIC_TEST_B="two words"\nAIC_TEST_C=from-file\nbroken line\n')
            os.environ["AIC_TEST_C"] = "from-env"
            try:
                server.load_env_file(path)
                self.assertEqual(os.environ["AIC_TEST_A"], "one")
                self.assertEqual(os.environ["AIC_TEST_B"], "two words")
                self.assertEqual(os.environ["AIC_TEST_C"], "from-env")
            finally:
                for key in ("AIC_TEST_A", "AIC_TEST_B", "AIC_TEST_C"):
                    os.environ.pop(key, None)
            server.load_env_file(Path(tmp) / "missing.env")


class ExtractTests(unittest.TestCase):
    def test_docx(self):
        self.assertEqual(server.extract_text("a.DOCX", make_docx()), "First para.\n\nSecond para.")

    def test_pptx(self):
        self.assertIn("[Slide 1 notes]", server.extract_text("deck.pptx", make_pptx()))

    def test_bad_and_unsupported(self):
        for name, data in [("a.docx", b"not a zip"), ("a.pdf", b"")]:
            with self.assertRaises(server.ReviewError) as ctx:
                server.extract_text(name, data)
            self.assertEqual(ctx.exception.status, 415)

    def test_empty_document(self):
        with self.assertRaises(server.ReviewError) as ctx:
            server.extract_text("a.txt", b"  \n ")
        self.assertEqual(ctx.exception.status, 400)


class ServerCase(unittest.TestCase):
    password = None

    @classmethod
    def setUpClass(cls):
        server.Handler.client = fake_client(review=REVIEW, rewrite=humanize)
        server.Handler.password = cls.password
        server.Handler.log_message = lambda *a: None
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        server.Handler.client = None
        server.Handler.password = None

    def request(self, path, body=None, headers=None, password=None):
        method = "POST" if body is not None else "GET"
        req = urllib.request.Request(self.base + path, data=body, headers=headers or {}, method=method)
        if password is not None:
            req.add_header("Authorization", "Basic " + base64.b64encode(f"user:{password}".encode()).decode())
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()


class HttpTests(ServerCase):
    def post_json(self, path, body, headers=None):
        status, _, raw = self.request(path, body, headers)
        return status, json.loads(raw)

    def test_serves_page_and_health(self):
        self.assertIn(b"AI Document Checker", self.request("/")[2])
        self.assertTrue(json.loads(self.request("/api/health")[2])["claude"])

    def test_review_endpoint(self):
        status, data = self.post_json("/api/review", json.dumps({"text": "Hello world."}).encode())
        self.assertEqual((status, data["verdict"]), (200, "likely_ai"))

    def test_review_rejects_empty_and_huge(self):
        self.assertEqual(self.post_json("/api/review", b'{"text": "  "}')[0], 400)
        huge = json.dumps({"text": "a" * (server.MAX_CHARS + 1)}).encode()
        self.assertEqual(self.post_json("/api/review", huge)[0], 413)

    def test_extract_endpoint_with_unicode_filename(self):
        status, data = self.post_json("/api/extract", make_pptx(), {"X-Filename": urllib.parse.quote("één.pptx")})
        self.assertEqual(status, 200)
        self.assertIn("Quarterly plan", data["text"])

    def test_clean_endpoint_returns_clean_file(self):
        status, data = self.post_json("/api/clean", make_pptx(), {"X-Filename": "deck.pptx"})
        self.assertEqual(status, 200)
        self.assertEqual(
            (data["filename"], data["changed"], data["total"], data["kind"]), ("deck (clean).pptx", 1, 5, "pptx")
        )
        self.assertIn("presentationml", data["mime"])
        cleaned = documents.load("deck.pptx", base64.b64decode(data["file"]))
        self.assertIn("Teams work better together.", cleaned.review_text())
        self.assertEqual(cleaned.review_text(), data["text"])

    def test_clean_plain_text(self):
        body = b"Moreover, synergy unlocks the full potential of teams."
        status, data = self.post_json("/api/clean", body, {"X-Filename": "notes.txt"})
        self.assertEqual((status, base64.b64decode(data["file"])), (200, b"Teams work better together.\n"))


class AuthTests(ServerCase):
    password = "s3cret"

    def test_requires_password(self):
        status, headers, _ = self.request("/")
        self.assertEqual(status, 401)
        self.assertIn("Basic", headers["WWW-Authenticate"])
        self.assertEqual(self.request("/", password="wrong")[0], 401)
        self.assertEqual(self.request("/api/clean", b"x", {"X-Filename": "a.txt"})[0], 401)

    def test_correct_password(self):
        status, headers, _ = self.request("/index.html", password="s3cret")
        self.assertEqual(status, 200)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])

    def test_healthz_is_open(self):
        self.assertEqual(self.request("/healthz")[0], 200)


if __name__ == "__main__":
    unittest.main()
