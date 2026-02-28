# Week 3 — Yahoo Finance MCP Server

A local MCP server that wraps the Yahoo Finance API via `yfinance`. It exposes two tools for fetching stock news and price history, and runs over STDIO so it can be discovered directly by Claude Desktop.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Environment Setup

No API key is required. Yahoo Finance is accessed without authentication via the `yfinance` library.

### Install dependencies

```bash
# from the repo root
uv pip install yfinance "mcp[cli]"
```

Or with pip:

```bash
pip install yfinance "mcp[cli]"
```

## Running the Server

### Smoke test (optional)

Run the server directly to verify it starts without errors. It will block waiting for STDIO input — `Ctrl+C` to exit.

```bash
uv run week3/server/main.py
```

Log output goes to stderr, so you should see nothing on stdout. This is intentional for STDIO transport compatibility.

## Claude Desktop Configuration

Add the server to your Claude Desktop config file:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "yahoo_finance": {
      "command": "uv",
        "args": [
        "--directory",
        "/ABSOLUTE/PATH/TO/PARENT/FOLDER/week3/server",
        "run",
        "main.py"
      ]
    }
  }
}
```

Replace `/absolute/path/to/` with the actual path on your machine. Then restart Claude Desktop. You should see a hammer icon indicating the tools are available.

## Tool Reference

### `get_topk_news`

Fetches the latest news articles for one or more stock symbols.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbols` | `list[str]` | required | List of ticker symbols, e.g. `["AAPL", "TSLA"]` |
| `topk` | `int` | `10` | Maximum number of articles to return per symbol |

**Example input:**

```json
{
  "symbols": ["NVDA", "MSFT"],
  "topk": 3
}
```

**Example output:**

```json
{
  "NVDA": [
    {
      "title": "Nvidia posts record revenue as AI demand surges",
      "summary": "Nvidia reported quarterly revenue of $26 billion...",
      "pubDate": "2024-05-22T20:32:00Z",
      "provider": "Reuters",
      "url": "https://www.reuters.com/..."
    }
  ],
  "MSFT": [
    {
      "title": "Microsoft Azure growth beats estimates",
      "summary": "Azure cloud revenue grew 31% year-over-year...",
      "pubDate": "2024-05-21T18:00:00Z",
      "provider": "Bloomberg",
      "url": "https://www.bloomberg.com/..."
    }
  ]
}
```

**Expected behavior:**
- Returns up to `topk` articles per symbol, ordered by recency.
- If a news item is missing required fields it is silently skipped and a warning is logged to stderr.
- If the request fails entirely, an error message string is returned instead of JSON.

---

### `get_recent_price_history`

Fetches the last 30 days of daily OHLCV (Open, High, Low, Close, Volume) price data for a single symbol.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | `str` | required | A single ticker symbol, e.g. `"AAPL"` |

**Example input:**

```json
{
  "symbol": "AAPL"
}
```

**Example output** (CSV):

```
Date,Open,High,Low,Close,Volume
2024-04-25,169.39,170.61,168.16,169.89,50340200
2024-04-26,169.89,171.35,168.96,170.77,44054800
...
```

**Expected behavior:**
- Returns CSV with a `Date` index (formatted `YYYY-MM-DD`) and five columns: `Open`, `High`, `Low`, `Close`, `Volume`. All price values are rounded to 2 decimal places.
- If the symbol is invalid or no data is available, a plain-text error message is returned.
- If the request fails, an error message string is returned.

## Error Handling

All errors are caught at the tool level and returned as plain-text messages so the MCP client always receives a valid response. Detailed tracebacks are written to stderr and visible in the Claude Desktop log viewer (`Help → Open Logs Folder`).

| Scenario | Behavior |
|----------|----------|
| Invalid ticker symbol | Returns `"No price data found for symbol: XYZ"` |
| Malformed news item | Skips item, logs `WARNING` to stderr |
| Network / API failure | Returns `"Error fetching ...: <reason>"`, logs `ERROR` with traceback |