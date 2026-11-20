# agent-toolbox

**Ready-to-use tools for AI agents** — a small, dependency-free Python library that gives an LLM agent practical abilities (fetching web pages, working with files, remembering things, running code) through one uniform interface.

Every tool is a plain Python function registered with a JSON-schema description, so the same tool can be:

- passed to an LLM as an **OpenAI-style function definition**,
- called directly from Python, and
- served over **MCP (Model Context Protocol)** — see the Day 5 roadmap item.

Built in public, one increment per day.

## Quickstart

```bash
git clone https://github.com/dodonquixote/agent-toolbox
cd agent-toolbox
python examples/demo.py
```

```python
from agent_toolbox import registry

# What tools exist, in LLM-ready format:
print(registry.function_definitions())

# Call one:
page = registry.call("fetch_url", {"url": "https://example.com"})
print(page["title"], page["text"][:200])
```

## Tools

| Tool | Day | What it does |
| --- | --- | --- |
| `fetch_url` | 1 | Fetch a web page and return clean readable text (scripts/styles stripped) for the LLM to read. |
| `read_file` / `write_file` / `list_dir` | 2 | Sandboxed file access, restricted to a workspace root. |
| `remember` / `recall` / `search_memory` | 3 | Persistent memory for agents, backed by SQLite. |
| `run_python` | 4 | Run a Python snippet in a sandboxed subprocess with a timeout. |
| `repair_json` | 4 | Repair malformed JSON (a common LLM output problem) and validate it. |
| MCP server | 5 | Expose every tool over the Model Context Protocol (stdio). |


## Design notes

- **Standard library only** for the core: no dependency surprises when an agent environment installs it.
- **One registry, many front doors**: function calling today, MCP tomorrow, same tool code.
- **Safety first**: tools that touch the filesystem or execute code are sandboxed and explicit about their limits (Days 2 and 4).

## Tests

```bash
python -m unittest discover -s tests
```

## License

MIT
