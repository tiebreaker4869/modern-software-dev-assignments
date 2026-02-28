import json
import logging
import sys
from collections import defaultdict

import yfinance as yf
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("yahoo_finance_mcp")

mcp = FastMCP("yahoo_finance")


def fetch_news(symbols: list[str], topk: int = 10) -> defaultdict[str, list[dict[str, str]]]:
    logger.info("Fetching news for symbols=%s topk=%d", symbols, topk)
    tickers = yf.Tickers(" ".join(symbols))
    news_list: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for symbol in symbols:
        for item in tickers.tickers[symbol].get_news(count=topk):
            try:
                c = item['content']
                news_list[symbol].append({
                    'title': c['title'],
                    'summary': c['summary'],
                    'pubDate': c['pubDate'],
                    'provider': c['provider']['displayName'],
                    'url': c['canonicalUrl']['url'],
                })
            except (KeyError, TypeError) as e:
                logger.warning("Skipping malformed news item for %s: %s", symbol, e)
                continue
        logger.info("Fetched %d news items for %s", len(news_list[symbol]), symbol)
    return news_list


@mcp.tool()
def get_topk_news(symbols: list[str], topk: int = 10) -> list[TextContent]:
    """
    Get latest news for one or more stock symbols.
    Returns title, summary, publication date, provider, and URL for each article.
    Use this to get recent news sentiment and events affecting a stock.
    """
    logger.info("Tool get_topk_news called: symbols=%s topk=%d", symbols, topk)
    try:
        news_list = fetch_news(symbols, topk)
        return [TextContent(type="text", text=json.dumps(dict(news_list), ensure_ascii=False, indent=2))]
    except Exception as e:
        logger.error("Failed to fetch news: %s", e, exc_info=True)
        return [TextContent(type="text", text=f"Error fetching news: {e}")]


@mcp.tool()
def get_recent_price_history(symbol: str) -> list[TextContent]:
    """
    Get recent 1 month daily OHLCV price history for a symbol.
    Use this for candlestick pattern recognition and short-term analysis.
    """
    logger.info("Tool get_recent_price_history called: symbol=%s", symbol)
    try:
        df = yf.Ticker(symbol).history(period="1mo")
        if df.empty:
            logger.warning("No price data returned for symbol=%s", symbol)
            return [TextContent(type="text", text=f"No price data found for symbol: {symbol}")]
        df.index = df.index.strftime("%Y-%m-%d")
        df = df[["Open", "High", "Low", "Close", "Volume"]].round(2)
        logger.info("Returning %d rows of price history for %s", len(df), symbol)
        return [TextContent(type="text", text=df.to_csv())]
    except Exception as e:
        logger.error("Failed to fetch price history for %s: %s", symbol, e, exc_info=True)
        return [TextContent(type="text", text=f"Error fetching price history: {e}")]


def main() -> None:
    mcp.run(transport='stdio')


if __name__ == "__main__":
    main()