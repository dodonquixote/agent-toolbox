# agent-toolbox

**Tools AI agents don't come with** — a small, dependency-free Python library of *non-basic* tools for AI agents. Not another fetch/file/memory clone: every tool here does a job that agent frameworks don't ship built in, aimed at real agent pain points — hallucinated citations, pages that change silently, feeds that repeat themselves, and data locked inside HTML tables.

Every tool is a plain Python function registered with a JSON-schema description, so the same tool can be:

- passed to an LLM as an **OpenAI-style function definition**,
- called directly from Python, and
- served over **MCP (Model Context Protocol)** — see the
  [MCP server](#mcp-server) section below.

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
| `fetch_url` | 1 | Foundation primitive: fetch a web page and return clean readable text (scripts/styles stripped). The higher-level tools below build on it. |
| `verify_citations` | 2 | Fact-check an LLM's sources: given claims with their cited URLs, it fetches each source and scores whether the source text actually supports the claim — flagging dead links and unsupported citations. |
| `watch_page` | 3 | Persistent page-change monitor: snapshots a page and, on later checks, reports exactly which lines were added or removed. |
| `feed_digest` | 4 | RSS/Atom reader with memory: returns only the items you have not seen before, deduplicated across runs. |
| `extract_tables` | 4 | Pull the HTML tables out of a page as structured JSON rows an agent can compute on. |
| MCP server | 5 | Expose every tool over the Model Context Protocol (stdio). |


## Design notes

- **Deliberately not basic**: no file read/write, shell, or generic memory tools — agents already have those. Each tool here adds a capability agents lack: verification, persistent monitoring, deduplication, structured extraction.
- **Standard library only** for the core: no dependency surprises when an agent environment installs it.
- **One registry, many front doors**: function calling today, MCP tomorrow, same tool code.
- **State where it matters**: monitoring and dedupe tools keep their own persistent state (SQLite), so an agent with no memory still gets continuity.

## Persistent state

`watch_page` (and, from Day 4, `feed_digest`) keep their own snapshots in
a small SQLite database, so an agent with no memory still gets continuity
between runs. The database lives outside the project:

- default: `~/.agent-toolbox/state.db`
- override: set the `AGENT_TOOLBOX_STATE` environment variable to a path.

## MCP server

Every registered tool is also available over the Model Context
Protocol, served over stdio by `agent_toolbox/server.py` — standard
library only, no MCP SDK required. It speaks JSON-RPC 2.0 and
implements `initialize`, `tools/list`, `tools/call` and `ping`.

Run it directly:

```bash
python -m agent_toolbox.server
```

Or point an MCP client (Claude Code, Cursor, Copilot, …) at it:

```json
{
  "mcpServers": {
    "agent-toolbox": {
      "command": "python",
      "args": ["-m", "agent_toolbox.server"],
      "cwd": "/path/to/agent-toolbox"
    }
  }
}
```

Restart the client and the agent-toolbox tools appear alongside its
built-in ones. Any tool added to the registry is automatically exposed
— nothing extra to wire up.

## Tests

```bash
python -m unittest discover -s tests
```

Try the chained example (watch a changelog, then verify a claim about
the change — no API key needed):

```bash
python examples/agent_example.py
```

## License

MIT
