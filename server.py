"""
Finnhub MCP Server
Exposes stock news, quotes, analyst recommendations, and price targets
to any MCP-compatible client (e.g. CustomGPT custom actions).

Deploy to Railway, Render, or run locally with ngrok.
Requires: FINNHUB_API_KEY environment variable
"""

import os
from datetime import date, timedelta

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Finnhub Stock Data")

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
BASE = "https://finnhub.io/api/v1"


async def _get(path: str, params: dict) -> dict | list:
    if not FINNHUB_KEY:
        raise ValueError("FINNHUB_API_KEY environment variable is not set")
    params["token"] = FINNHUB_KEY
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{BASE}{path}", params=params)
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def get_stock_quote(symbol: str) -> str:
    """
    Get the current stock price and daily change for a ticker symbol.
    Examples: AAPL, TSLA, MSFT, NVDA
    """
    data = await _get("/quote", {"symbol": symbol.upper()})
    if not data or data.get("c") == 0:
        return f"No quote data found for {symbol.upper()}. Check that the ticker is valid."
    return (
        f"{symbol.upper()} Quote:\n"
        f"  Current Price : ${data['c']:.2f}\n"
        f"  Open          : ${data['o']:.2f}\n"
        f"  High          : ${data['h']:.2f}\n"
        f"  Low           : ${data['l']:.2f}\n"
        f"  Prev Close    : ${data['pc']:.2f}\n"
        f"  Change        : {data['d']:+.2f} ({data['dp']:+.2f}%)"
    )


@mcp.tool()
async def get_company_news(symbol: str, days_back: int = 7) -> str:
    """
    Get the latest news articles for a specific stock.
    Returns up to 5 headlines with source and link.
    Examples: AAPL, TSLA, AMZN
    """
    to_date = date.today().isoformat()
    from_date = (date.today() - timedelta(days=days_back)).isoformat()
    data = await _get("/company-news", {
        "symbol": symbol.upper(),
        "from": from_date,
        "to": to_date,
    })
    if not data:
        return f"No news found for {symbol.upper()} in the last {days_back} days."
    lines = [f"Latest news for {symbol.upper()} (last {days_back} days):\n"]
    for article in data[:5]:
        lines.append(f"• {article['headline']}")
        lines.append(f"  {article['source']} — {article['url']}\n")
    return "\n".join(lines)


@mcp.tool()
async def get_market_news(category: str = "general") -> str:
    """
    Get broad market news headlines.
    Category options: general, forex, crypto, merger
    """
    valid = {"general", "forex", "crypto", "merger"}
    if category not in valid:
        return f"Invalid category '{category}'. Choose from: {', '.join(valid)}"
    data = await _get("/news", {"category": category})
    if not data:
        return f"No {category} market news found."
    lines = [f"Market News — {category.title()}:\n"]
    for article in data[:5]:
        lines.append(f"• {article['headline']}")
        lines.append(f"  {article['source']} — {article['url']}\n")
    return "\n".join(lines)


@mcp.tool()
async def get_analyst_recommendations(symbol: str) -> str:
    """
    Get the latest analyst buy/sell/hold consensus for a stock.
    Returns strong buy, buy, hold, sell, strong sell counts.
    Examples: AAPL, TSLA, GOOGL
    """
    data = await _get("/stock/recommendation", {"symbol": symbol.upper()})
    if not data:
        return f"No analyst recommendation data found for {symbol.upper()}."
    latest = data[0]
    total = sum([
        latest.get("strongBuy", 0),
        latest.get("buy", 0),
        latest.get("hold", 0),
        latest.get("sell", 0),
        latest.get("strongSell", 0),
    ])
    return (
        f"Analyst Recommendations for {symbol.upper()} — {latest['period']}:\n"
        f"  Strong Buy  : {latest.get('strongBuy', 0)}\n"
        f"  Buy         : {latest.get('buy', 0)}\n"
        f"  Hold        : {latest.get('hold', 0)}\n"
        f"  Sell        : {latest.get('sell', 0)}\n"
        f"  Strong Sell : {latest.get('strongSell', 0)}\n"
        f"  Total Analysts: {total}"
    )


@mcp.tool()
async def get_price_target(symbol: str) -> str:
    """
    Get analyst consensus price targets for a stock.
    Returns average, high, and low price targets.
    Examples: AAPL, TSLA, NVDA
    """
    data = await _get("/stock/price-target", {"symbol": symbol.upper()})
    if not data or not data.get("targetMean"):
        return f"No price target data found for {symbol.upper()}."
    return (
        f"Analyst Price Targets for {symbol.upper()}:\n"
        f"  Average Target : ${data['targetMean']:.2f}\n"
        f"  High Target    : ${data['targetHigh']:.2f}\n"
        f"  Low Target     : ${data['targetLow']:.2f}\n"
        f"  Last Updated   : {data.get('lastUpdated', 'N/A')}"
    )


@mcp.tool()
async def get_earnings_calendar(symbol: str) -> str:
    """
    Get upcoming earnings dates and EPS estimates for a stock.
    Examples: AAPL, TSLA, AMZN
    """
    to_date = (date.today() + timedelta(days=90)).isoformat()
    from_date = date.today().isoformat()
    data = await _get("/calendar/earnings", {
        "symbol": symbol.upper(),
        "from": from_date,
        "to": to_date,
    })
    earnings = data.get("earningsCalendar", [])
    if not earnings:
        return f"No upcoming earnings found for {symbol.upper()} in the next 90 days."
    lines = [f"Upcoming Earnings for {symbol.upper()}:\n"]
    for e in earnings[:3]:
        lines.append(
            f"• Date: {e.get('date', 'TBD')} | "
            f"EPS Est: {e.get('epsEstimate', 'N/A')} | "
            f"Revenue Est: {e.get('revenueEstimate', 'N/A')}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
