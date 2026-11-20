import unittest

from agent_toolbox import registry


class TestRegistry(unittest.TestCase):
    def test_bundled_tools_registered(self):
        self.assertIn("fetch_url", registry.names())

    def test_function_definition_shape(self):
        defs = {d["function"]["name"]: d for d in registry.function_definitions()}
        self.assertEqual(defs["fetch_url"]["type"], "function")
        params = defs["fetch_url"]["function"]["parameters"]
        self.assertIn("url", params["properties"])
        self.assertEqual(params["required"], ["url"])

    def test_call_unknown_tool(self):
        with self.assertRaises(KeyError):
            registry.call("does_not_exist", {})

    def test_call_accepts_json_string(self):
        # fetch_url with an invalid scheme raises before any network use,
        # which proves dispatch + JSON parsing happened.
        with self.assertRaises(ValueError):
            registry.call("fetch_url", '{"url": "ftp://example.com"}')


if __name__ == "__main__":
    unittest.main()
