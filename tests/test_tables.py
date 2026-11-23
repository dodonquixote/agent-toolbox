import unittest
from unittest import mock

from agent_toolbox import registry
from agent_toolbox.tools import tables
from agent_toolbox.tools.tables import extract_tables_from_html

PAGE_URL = "https://example.test/prices"

HTML_WITH_HEADER = """<html><body>
<h1>Prices</h1>
<table>
  <tr><th>Product</th><th>Price</th></tr>
  <tr><td>Widget</td><td>10</td></tr>
  <tr><td>Gadget</td><td>25</td></tr>
</table>
</body></html>"""

HTML_NO_HEADER = """<html><body>
<table>
  <tr><td>Alice</td><td>30</td></tr>
  <tr><td>Bob</td><td>42</td></tr>
</table>
</body></html>"""

HTML_TWO_TABLES = """<html><body>
<table><tr><th>Name</th></tr><tr><td>One</td></tr></table>
<p>between</p>
<table><tr><td>x</td><td>y</td></tr></table>
</body></html>"""

HTML_MESSY_CELLS = """<html><body>
<table>
  <tr><th>  Item  </th><th>Notes</th></tr>
  <tr><td><b>Bold</b> text</td><td>line&nbsp;one<br/>line two</td></tr>
  <tr><td></td><td>empty first cell</td></tr>
</table>
</body></html>"""

HTML_NO_TABLES = "<html><body><p>No tables here.</p></body></html>"

HTML_EMPTY_TABLE = "<html><body><table></table><p>hi</p></body></html>"


class ExtractTablesTestCase(unittest.TestCase):
    def _run_with_stub(self, html, url=PAGE_URL, **kwargs):
        with mock.patch.object(tables, "_fetch_html", return_value=html):
            return tables.extract_tables(url, **kwargs)

    def test_header_row_becomes_header(self):
        result = self._run_with_stub(HTML_WITH_HEADER)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["table_count"], 1)
        table = result["tables"][0]
        self.assertEqual(table["header"], ["Product", "Price"])
        self.assertEqual(table["rows"], [["Widget", "10"], ["Gadget", "25"]])
        self.assertIsNone(result["error"])

    def test_table_without_th_has_no_header(self):
        result = self._run_with_stub(HTML_NO_HEADER)
        table = result["tables"][0]
        self.assertIsNone(table["header"])
        self.assertEqual(table["rows"], [["Alice", "30"], ["Bob", "42"]])

    def test_multiple_tables_returned_in_order(self):
        result = self._run_with_stub(HTML_TWO_TABLES)
        self.assertEqual(result["table_count"], 2)
        self.assertEqual(result["tables"][0]["header"], ["Name"])
        self.assertEqual(result["tables"][0]["rows"], [["One"]])
        self.assertIsNone(result["tables"][1]["header"])
        self.assertEqual(result["tables"][1]["rows"], [["x", "y"]])

    def test_cell_text_cleaned_and_nested_markup_stripped(self):
        result = self._run_with_stub(HTML_MESSY_CELLS)
        table = result["tables"][0]
        self.assertEqual(table["header"], ["Item", "Notes"])
        self.assertEqual(table["rows"][0], ["Bold text", "line one line two"])
        self.assertEqual(table["rows"][1], ["", "empty first cell"])

    def test_max_tables_limits_results(self):
        result = self._run_with_stub(HTML_TWO_TABLES, max_tables=1)
        self.assertEqual(result["table_count"], 1)

    def test_page_without_tables(self):
        result = self._run_with_stub(HTML_NO_TABLES)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["table_count"], 0)
        self.assertEqual(result["tables"], [])

    def test_empty_table_ignored(self):
        result = self._run_with_stub(HTML_EMPTY_TABLE)
        self.assertEqual(result["table_count"], 0)

    def test_fetch_failure_returns_error(self):
        with mock.patch.object(tables, "_fetch_html",
                               side_effect=ValueError("boom")):
            result = tables.extract_tables(PAGE_URL)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["tables"], [])
        self.assertIn("ValueError", result["error"])

    def test_registered_in_registry(self):
        self.assertIn("extract_tables", registry.names())
        defs = {d["function"]["name"]: d for d in registry.function_definitions()}
        self.assertEqual(defs["extract_tables"]["function"]["parameters"]["required"],
                         ["url"])

    def test_callable_via_registry(self):
        result = registry.call("extract_tables", {"url": "ftp://example.test/x"})
        self.assertEqual(result["status"], "error")


class TestExtractTablesFromHtml(unittest.TestCase):
    def test_mixed_th_td_row_is_not_a_header(self):
        html = ("<table><tr><th>Name</th><td>value</td></tr>"
                "<tr><td>a</td><td>b</td></tr></table>")
        tables_list = extract_tables_from_html(html)
        self.assertIsNone(tables_list[0]["header"])
        self.assertEqual(tables_list[0]["rows"],
                         [["Name", "value"], ["a", "b"]])

    def test_header_only_table_has_empty_rows(self):
        html = "<table><tr><th>A</th><th>B</th></tr></table>"
        tables_list = extract_tables_from_html(html)
        self.assertEqual(tables_list[0]["header"], ["A", "B"])
        self.assertEqual(tables_list[0]["rows"], [])


if __name__ == "__main__":
    unittest.main()
