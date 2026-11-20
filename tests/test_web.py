import unittest

from agent_toolbox.tools.web import extract_text

SAMPLE = """<!doctype html>
<html><head><title>Example &amp; Co</title><style>body{color:red}</style>
<script>var secret = 1;</script></head>
<body><h1>Hello</h1><p>First&nbsp;paragraph.</p>
<p>Second <b>paragraph</b> with a <a href="https://x.test">link</a>.</p>
</body></html>"""


class TestExtractText(unittest.TestCase):
    def test_title_and_text(self):
        title, text = extract_text(SAMPLE)
        self.assertEqual(title, "Example & Co")
        self.assertIn("Hello", text)
        self.assertIn("First paragraph.", text)
        self.assertIn("Second paragraph with a link.", text)

    def test_script_and_style_stripped(self):
        _, text = extract_text(SAMPLE)
        self.assertNotIn("secret", text)
        self.assertNotIn("color:red", text)


if __name__ == "__main__":
    unittest.main()
