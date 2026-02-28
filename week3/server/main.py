from mcp.server.fastmcp import FastMCP
import yfinance as yf
from collections import defaultdict
from mcp.types import TextContent
import json

mcp = FastMCP("yahoo_finance")


def fetch_news(symbols: list[str], topk: int = 10) -> defaultdict[str, list]:
    tickers = yf.Tickers(" ".join(symbols))
    news_list = defaultdict(list)
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
            except (KeyError, TypeError):
                continue
    return news_list


@mcp.tool()
def get_topk_news(symbols: list[str], topk: int = 10) -> list[TextContent]:
    """
    Get latest news for one or more stock symbols.
    Returns title, summary, publication date, provider, and URL for each article.
    Use this to get recent news sentiment and events affecting a stock.
    """
    news_list = fetch_news(symbols, topk)
    return [TextContent(type="text", text=json.dumps(dict(news_list), ensure_ascii=False, indent=2))]


@mcp.tool()
def get_recent_price_history(symbol: str) -> list[TextContent]:
    """
    Get recent 1 month daily OHLCV price history for a symbol.
    Use this for candlestick pattern recognition and short-term analysis.
    """
    df = yf.Ticker(symbol).history(period="1mo")
    df.index = df.index.strftime("%Y-%m-%d")
    df = df[["Open", "High", "Low", "Close", "Volume"]].round(2)
    return [TextContent(type="text", text=df.to_csv())]


def main():
    mcp.run(transport='stdio')


if __name__ == "__main__":
    main()