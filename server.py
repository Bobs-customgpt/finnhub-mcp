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

_port = int(os.environ.get("PORT", 8000))
mcp = FastMCP("Finnhub Stock Data", host="0.0.0.0", port=_port)

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
    Get analyst consensus price targets for a stock: average, high, and low targets,
    number of analysts, and implied upside from current price.
    Examples: AAPL, TSLA, NVDA
    """
    import yfinance as yf
    ticker = yf.Ticker(symbol.upper())

    try:
        targets = ticker.analyst_price_targets
        info = ticker.info
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")

        if targets is None or not hasattr(targets, "get"):
            return f"No price target data available for {symbol.upper()}."

        mean = targets.get("mean")
        high = targets.get("high")
        low = targets.get("low")
        num_analysts = targets.get("numberOfAnalysts")

        if not mean:
            return f"No price target data available for {symbol.upper()}."

        lines = [f"Analyst Price Targets for {symbol.upper()}:\n"]
        lines.append(f"  Average Target   : ${mean:.2f}")
        lines.append(f"  High Target      : ${high:.2f}" if high else "  High Target      : N/A")
        lines.append(f"  Low Target       : ${low:.2f}" if low else "  Low Target       : N/A")
        if num_analysts:
            lines.append(f"  # of Analysts    : {num_analysts}")
        if current_price and mean:
            upside = (mean - current_price) / current_price * 100
            lines.append(f"  Current Price    : ${current_price:.2f}")
            lines.append(f"  Upside to Target : {upside:+.1f}%")
        return "\n".join(lines)

    except Exception as e:
        return f"Could not retrieve price target data for {symbol.upper()}: {str(e)}"


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


@mcp.tool()
async def get_company_profile(symbol: str) -> str:
    """
    Get company profile: sector, industry, market cap, country, exchange,
    description, IPO date, and website.
    Examples: AAPL, TSLA, NVDA
    """
    data = await _get("/stock/profile2", {"symbol": symbol.upper()})
    if not data or not data.get("name"):
        return f"No company profile found for {symbol.upper()}."
    mc = data.get("marketCapitalization", 0)
    mc_str = f"${mc/1000:.1f}B" if mc >= 1000 else f"${mc:.0f}M"
    return (
        f"Company Profile — {data.get('name', symbol.upper())} ({symbol.upper()}):\n"
        f"  Exchange        : {data.get('exchange', 'N/A')}\n"
        f"  Sector          : {data.get('finnhubIndustry', 'N/A')}\n"
        f"  Country         : {data.get('country', 'N/A')}\n"
        f"  Market Cap      : {mc_str}\n"
        f"  IPO Date        : {data.get('ipo', 'N/A')}\n"
        f"  Website         : {data.get('weburl', 'N/A')}\n"
        f"  Shares Out      : {data.get('shareOutstanding', 'N/A')}M"
    )


@mcp.tool()
async def get_financial_metrics(symbol: str) -> str:
    """
    Get key financial metrics and valuation ratios for a stock.
    Includes P/E, EPS, beta, 52-week range, profit margin, ROE, debt/equity,
    revenue growth, and more.
    Examples: AAPL, TSLA, NVDA
    """
    import yfinance as yf

    # Finnhub for valuation ratios + 52-week range
    data = await _get("/stock/metric", {"symbol": symbol.upper(), "metric": "all"})
    m = data.get("metric", {})

    # yfinance for profitability metrics (more reliably populated)
    yf_info = {}
    try:
        ticker = yf.Ticker(symbol.upper())
        yf_info = ticker.info or {}
    except Exception:
        pass

    def fmt(val, prefix="", suffix="", decimals=2):
        if val is None:
            return "N/A"
        try:
            return f"{prefix}{float(val):.{decimals}f}{suffix}"
        except (TypeError, ValueError):
            return "N/A"

    def pct(val):
        """Format a decimal (0.45) or whole number (45) as a percentage string."""
        if val is None:
            return "N/A"
        try:
            v = float(val)
            # yfinance returns decimals (0.45 = 45%), Finnhub returns whole numbers
            if abs(v) < 2:
                v = v * 100
            return f"{v:.1f}%"
        except (TypeError, ValueError):
            return "N/A"

    # Pull profitability from yfinance, fall back to Finnhub annual fields
    gross_margin = yf_info.get("grossMargins") or m.get("grossMarginAnnual") or m.get("grossMarginTTM")
    net_margin   = yf_info.get("profitMargins") or m.get("netProfitMarginAnnual") or m.get("netProfitMarginTTM")
    roe          = yf_info.get("returnOnEquity") or m.get("roeAnnual") or m.get("roeTTM")
    roa          = yf_info.get("returnOnAssets") or m.get("roaAnnual") or m.get("roaTTM")
    ev_ebitda    = yf_info.get("enterpriseToEbitda") or m.get("evEbitdaTTM") or m.get("evEbitdaAnnual")
    ps_ratio     = yf_info.get("priceToSalesTrailing12Months") or m.get("psTTM")
    rev_growth   = yf_info.get("revenueGrowth") or m.get("revenueGrowthTTMYoy")
    eps_growth   = yf_info.get("earningsGrowth") or m.get("epsGrowthTTMYoy")
    debt_eq      = yf_info.get("debtToEquity") or m.get("totalDebt/totalEquityAnnual")
    current_r    = yf_info.get("currentRatio") or m.get("currentRatioAnnual")

    return (
        f"Financial Metrics — {symbol.upper()}:\n"
        f"\n  --- Valuation ---\n"
        f"  P/E (TTM)            : {fmt(m.get('peBasicExclExtraTTM') or yf_info.get('trailingPE'))}x\n"
        f"  P/E (Forward)        : {fmt(m.get('peNormalizedAnnual') or yf_info.get('forwardPE'))}x\n"
        f"  EPS (TTM)            : {fmt(m.get('epsBasicExclExtraItemsTTM') or yf_info.get('trailingEps'), prefix='$')}\n"
        f"  Price/Sales (TTM)    : {fmt(ps_ratio)}x\n"
        f"  Price/Book           : {fmt(m.get('pbAnnual') or yf_info.get('priceToBook'))}x\n"
        f"  EV/EBITDA            : {fmt(ev_ebitda)}x\n"
        f"\n  --- 52-Week Range ---\n"
        f"  52-Week High         : {fmt(m.get('52WeekHigh') or yf_info.get('fiftyTwoWeekHigh'), prefix='$')}\n"
        f"  52-Week Low          : {fmt(m.get('52WeekLow') or yf_info.get('fiftyTwoWeekLow'), prefix='$')}\n"
        f"  52-Week Return       : {fmt(m.get('52WeekPriceReturnDaily'), suffix='%')}\n"
        f"\n  --- Profitability ---\n"
        f"  Gross Margin         : {pct(gross_margin)}\n"
        f"  Net Margin           : {pct(net_margin)}\n"
        f"  ROE                  : {pct(roe)}\n"
        f"  ROA                  : {pct(roa)}\n"
        f"\n  --- Growth ---\n"
        f"  Revenue Growth (YoY) : {pct(rev_growth)}\n"
        f"  EPS Growth (YoY)     : {pct(eps_growth)}\n"
        f"\n  --- Risk ---\n"
        f"  Beta                 : {fmt(m.get('beta') or yf_info.get('beta'))}\n"
        f"  Debt/Equity          : {fmt(debt_eq)}x\n"
        f"  Current Ratio        : {fmt(current_r)}x"
    )


@mcp.tool()
async def get_historical_earnings(symbol: str) -> str:
    """
    Get the last 8 quarters of earnings results: actual vs estimated EPS
    and the surprise percentage. Shows whether a company consistently beats
    or misses Wall Street expectations.
    Examples: AAPL, TSLA, NVDA
    """
    data = await _get("/stock/earnings", {"symbol": symbol.upper(), "limit": 8})
    if not data:
        return f"No historical earnings data found for {symbol.upper()}."

    lines = [f"Historical Earnings — {symbol.upper()} (last {len(data)} quarters):\n"]
    beats = 0
    total_surprise = 0.0
    count = 0

    for e in data:
        actual = e.get("actual")
        est = e.get("estimate")
        period = e.get("period", "N/A")
        surprise_pct = e.get("surprisePercent")

        if actual is not None and est is not None:
            beat = "BEAT" if actual >= est else "MISS"
            if actual >= est:
                beats += 1
        else:
            beat = "N/A"

        sp_str = f"{surprise_pct:+.1f}%" if surprise_pct is not None else "N/A"
        actual_str = f"${actual:.2f}" if actual is not None else "N/A"
        est_str = f"${est:.2f}" if est is not None else "N/A"

        if surprise_pct is not None:
            total_surprise += surprise_pct
            count += 1

        lines.append(
            f"  {period} | Actual: {actual_str} | Est: {est_str} | "
            f"Surprise: {sp_str} | {beat}"
        )

    if count > 0:
        avg_surprise = total_surprise / count
        lines.append(
            f"\n  Beat rate: {beats}/{len(data)} quarters | "
            f"Avg surprise: {avg_surprise:+.1f}%"
        )
    return "\n".join(lines)


@mcp.tool()
async def get_stock_peers(symbol: str) -> str:
    """
    Get a list of peer/comparable companies in the same sector as the given stock.
    Useful for relative valuation analysis.
    Examples: AAPL, TSLA, NVDA
    """
    data = await _get("/stock/peers", {"symbol": symbol.upper()})
    if not data:
        return f"No peer data found for {symbol.upper()}."
    peers = [p for p in data if p != symbol.upper()]
    return (
        f"Peer Companies for {symbol.upper()}:\n"
        f"  {', '.join(peers[:12])}\n\n"
        f"  Tip: Run get_financial_metrics or compare_stocks on these tickers "
        f"for relative valuation analysis."
    )


@mcp.tool()
async def get_insider_sentiment(symbol: str) -> str:
    """
    Get a summary of insider buying vs selling activity over the last 3 months.
    Net insider buying is a bullish signal; net selling can indicate overvaluation
    or lack of insider conviction.
    Examples: AAPL, TSLA, NVDA
    """
    import yfinance as yf
    ticker = yf.Ticker(symbol.upper())

    try:
        transactions = ticker.insider_transactions
        if transactions is None or transactions.empty:
            return f"No insider transaction data found for {symbol.upper()} in the last 90 days."

        cutoff = date.today() - timedelta(days=90)
        transactions["Start Date"] = transactions["Start Date"].apply(
            lambda x: x.date() if hasattr(x, "date") else x
        )
        recent = transactions[transactions["Start Date"] >= cutoff]

        if recent.empty:
            return f"No insider transactions found for {symbol.upper()} in the last 90 days."

        buys = recent[recent["Transaction"].str.contains("Buy|Purchase", case=False, na=False)]
        sells = recent[recent["Transaction"].str.contains("Sell|Sale", case=False, na=False)]

        buy_shares = buys["Shares"].sum() if not buys.empty else 0
        sell_shares = sells["Shares"].sum() if not sells.empty else 0
        net_shares = buy_shares - sell_shares
        signal = "BULLISH (net buyers)" if net_shares > 0 else "BEARISH (net sellers)"

        lines = [f"Insider Activity — {symbol.upper()} (last 90 days):\n"]
        lines.append(f"  Purchases : {len(buys)} transactions | {buy_shares:,.0f} shares")
        lines.append(f"  Sales     : {len(sells)} transactions | {sell_shares:,.0f} shares")
        lines.append(f"  Net Shares: {net_shares:+,.0f}")
        lines.append(f"  Signal    : {signal}")

        if not buys.empty:
            lines.append(f"\n  Notable buys:")
            for _, row in buys.head(3).iterrows():
                lines.append(
                    f"    • {row.get('Insider', 'Unknown')} ({row.get('Start Date', 'N/A')}): "
                    f"{row.get('Shares', 0):,.0f} shares"
                )
        return "\n".join(lines)

    except Exception as e:
        return f"Could not retrieve insider data for {symbol.upper()}: {str(e)}"


@mcp.tool()
async def compare_stocks(symbols: str) -> str:
    """
    Compare multiple stocks side-by-side on key metrics: current price,
    analyst consensus, price target upside %, and analyst buy/hold/sell breakdown.
    Pass a comma-separated list of up to 5 tickers.
    Example: 'AAPL,MSFT,GOOGL,AMZN' or 'NVDA,AMD,INTC'
    """
    import asyncio

    tickers = [s.strip().upper() for s in symbols.split(",") if s.strip()][:5]
    if not tickers:
        return "Please provide at least one ticker symbol."

    import yfinance as yf

    async def fetch_one(sym: str):
        try:
            quote, recs = await asyncio.gather(
                _get("/quote", {"symbol": sym}),
                _get("/stock/recommendation", {"symbol": sym}),
            )
            # yfinance for price target (Finnhub free tier blocks /stock/price-target)
            try:
                ticker = yf.Ticker(sym)
                targets = ticker.analyst_price_targets or {}
                yf_price = (ticker.info or {}).get("currentPrice", 0)
            except Exception:
                targets = {}
                yf_price = 0
            return sym, quote, recs, targets, yf_price
        except Exception:
            return sym, {}, [], {}, 0

    results = await asyncio.gather(*[fetch_one(t) for t in tickers])

    lines = ["Stock Comparison:\n"]
    lines.append(f"  {'Ticker':<8} {'Price':>8} {'Analyst':>10} {'Target':>8} {'Upside':>8} {'B/H/S':>12}")
    lines.append("  " + "-" * 58)

    for sym, quote, recs, targets, yf_price in results:
        price = quote.get("c", 0) or yf_price
        price_str = f"${price:.2f}" if price else "N/A"

        # Consensus label
        if recs:
            r = recs[0]
            sb = r.get("strongBuy", 0)
            b = r.get("buy", 0)
            h = r.get("hold", 0)
            s = r.get("sell", 0)
            ss = r.get("strongSell", 0)
            total = sb + b + h + s + ss
            buy_pct = (sb + b) / total * 100 if total else 0
            if buy_pct >= 70:
                consensus = "Strong Buy"
            elif buy_pct >= 50:
                consensus = "Buy"
            elif (s + ss) / total * 100 >= 30 if total else False:
                consensus = "Sell"
            else:
                consensus = "Hold"
            bhs = f"{sb+b}/{h}/{s+ss}"
        else:
            consensus = "N/A"
            bhs = "N/A"

        # Price target upside (from yfinance)
        mean_target = targets.get("mean", 0)
        if mean_target and price:
            upside = (mean_target - price) / price * 100
            target_str = f"${mean_target:.2f}"
            upside_str = f"{upside:+.1f}%"
        else:
            target_str = "N/A"
            upside_str = "N/A"

        lines.append(
            f"  {sym:<8} {price_str:>8} {consensus:>10} {target_str:>8} {upside_str:>8} {bhs:>12}"
        )

    lines.append("\n  B/H/S = Buy / Hold / Sell analyst count")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
