import base64
import unittest
from unittest.mock import patch

from pdf_source import (
    PdfSourceError,
    canonical_repo,
    safe_pdf_path,
    validate_pdf,
    load_bundled_pdf,
    load_github_pdf,
)


class PdfSourceTests(unittest.TestCase):
    def test_repository_parser(self):
        self.assertEqual(canonical_repo("https://github.com/peterDataScientia/GA"), "peterDataScientia/GA")
        self.assertEqual(canonical_repo("peterDataScientia/GA"), "peterDataScientia/GA")
        with self.assertRaises(PdfSourceError):
            canonical_repo("https://evil.invalid/peterDataScientia/GA")

    def test_pdf_path_validation(self):
        self.assertEqual(safe_pdf_path("outputs/main.pdf"), "outputs/main.pdf")
        for value in ("../main.pdf", "/main.pdf", "foo\\main.pdf", "main.tex"):
            with self.assertRaises(PdfSourceError):
                safe_pdf_path(value)

    def test_pdf_magic(self):
        with self.assertRaises(PdfSourceError):
            validate_pdf(b"Not a PDF")
        self.assertEqual(validate_pdf(b"%PDF-1.7\n%%EOF"), b"%PDF-1.7\n%%EOF")

    def test_bundled(self):
        value = load_bundled_pdf("peterDataScientia/GA", "graphical_abstract.pdf")
        self.assertTrue(value.content.startswith(b"%PDF-"))
        self.assertGreater(len(value.content), 100000)
        with self.assertRaises(PdfSourceError):
            load_bundled_pdf("someone/other", "graphical_abstract.pdf")

    def test_inline_github(self):
        payload = b"%PDF-1.4\n%%EOF"
        inline = {"type":"file", "encoding":"base64", "sha":"a"*40, "content":base64.b64encode(payload).decode()}
        with patch("pdf_source._request_json", return_value=inline) as req:
            pdf = load_github_pdf("user/repo", "graphical_abstract.pdf", token="secret")
            self.assertEqual(pdf.content, payload)
            self.assertEqual(req.call_count, 1)

    def test_large_file_blob_fallback(self):
        payload = b"%PDF-1.5\n%%EOF"
        first = {"type":"file", "encoding":"none", "sha":"b"*40}
        second = {"encoding":"base64", "content":base64.b64encode(payload).decode()}
        with patch("pdf_source._request_json", side_effect=[first,second]) as req:
            pdf = load_github_pdf("user/repo", "out/figure.pdf")
            self.assertEqual(pdf.content, payload)
            self.assertEqual(req.call_count, 2)


if __name__ == "__main__":
    unittest.main()
