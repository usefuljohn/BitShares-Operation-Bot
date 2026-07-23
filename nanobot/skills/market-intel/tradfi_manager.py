import json
import os
import requests
from datetime import datetime

# ─── Asset Categories & Config ──────────────────────────────────────────────

ASSET_CATEGORIES = [
    {"id": "crypto-major", "name": "Major Cryptocurrencies", "priority": 1},
    {"id": "etfs", "name": "ETFs", "priority": 2},
    {"id": "rates", "name": "Rates & Currencies", "priority": 3},
    {"id": "commodities", "name": "Commodities", "priority": 4},
    {"id": "crypto-alt", "name": "Alternative Cryptocurrencies", "priority": 5},
    {"id": "tech-stocks", "name": "Technology Stocks", "priority": 6},
    {"id": "other-stocks", "name": "Other Stocks", "priority": 7},
    {"id": "misc", "name": "DJIA ETF", "priority": 8},
]

ASSETS = {
    "BTC_USD": {
        "feedId": "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
        "symbol": "BTC/USD",
        "name": "Bitcoin",
        "category": "crypto-major",
        "priority": 1,
    },
    "XRP_USD": {
        "feedId": "ec5d399846a9209f3fe5881d70aae9268c94339ff9817e8d18ff19fa05eea1c8",
        "symbol": "XRP/USD",
        "name": "Ripple",
        "category": "crypto-major",
        "priority": 2,
    },
    "SPY_USD": {
        "feedId": "19e09bb805456ada3979a7d1cbb4b6d63babc3a0f8e8a9509f68afa5c4c11cd5",
        "symbol": "SPY/USD",
        "name": "SPDR S&P 500 ETF Trust",
        "category": "etfs",
        "priority": 1,
    },
    "QQQ_USD": {
        "feedId": "9695e2b96ea7b3859da9ed25b7a46a920a776e2fdae19a7bcfdf2b219230452d",
        "symbol": "QQQ/USD",
        "name": "Invesco QQQ ETF",
        "category": "etfs",
        "priority": 2,
    },
    "TLT_USD": {
        "feedId": "9f383d612ac09c7e6ffda24deca1502fce72e0ba58ff473fea411d9727401cc1",
        "symbol": "TLT/USD",
        "name": "iShares 20+ Year Treasury Bond ETF",
        "category": "etfs",
        "priority": 3,
    },
    "VOO_USD": {
        "feedId": "236b30dd09a9c00dfeec156c7b1efd646c0f01825a1758e3e4a0679e3bdff179",
        "symbol": "VOO/USD",
        "name": "Vanguard S&P 500 ETF",
        "category": "etfs",
        "priority": 4,
    },
    "KRE_USD": {
        "feedId": "22e1659c12192de5eb81db0c9bffb6646df2bcc05c9c04dbc0726bc491b7ac88",
        "symbol": "KRE/USD",
        "name": "Regional Banking ETF",
        "category": "etfs",
        "priority": 5,
    },
    "EUR_USD": {
        "feedId": "a995d00bb36a63cef7fd2c287dc105fc8f3d93779f062f09551b0af3e81ec30b",
        "symbol": "EUR/USD",
        "name": "Euro",
        "category": "rates",
        "priority": 1,
    },
    "SOFR_PCT": {
        "feedId": "0f5fd558019a7cad9eaa012cd7228c65f2b7ed31db3f66ec557087a769df0f67",
        "symbol": "SOFR %",
        "name": "Secured Overnight Financing Rate",
        "category": "rates",
        "priority": 2,
    },
    "US_10YR_PCT": {
        "feedId": "9c196541230ba421baa2a499214564312a46bb47fb6b61ef63db2f70d3ce34c1",
        "symbol": "US 10-YR %",
        "name": "US 10-Year Treasury Yield",
        "category": "rates",
        "priority": 3,
    },
    "XAU_USD": {
        "feedId": "765d2ba906dbc32ca17cc11f5310a89e9ee1f6420508c63861f2f8ba4ee34bb2",
        "symbol": "XAU/USD",
        "name": "Gold",
        "category": "commodities",
        "priority": 1,
    },
    "XAG_USD": {
        "feedId": "f2fb02c32b055c805e7238d628e5e9dadef274376114eb1f012337cabe93871e",
        "symbol": "XAG/USD",
        "name": "Silver",
        "category": "commodities",
        "priority": 2,
    },
    "LTC_USD": {
        "feedId": "6e3f3fa8253588df9326580180233eb791e03b443a3ba7a1d892e73874e19a54",
        "symbol": "LTC/USD",
        "name": "Litecoin",
        "category": "crypto-alt",
        "priority": 1,
    },
    "XMR_USD": {
        "feedId": "46b8cc9347f04391764a0361e0b17c3ba394b001e7c304f7650f6376e37c321d",
        "symbol": "XMR/USD",
        "name": "Monero",
        "category": "crypto-alt",
        "priority": 2,
    },
    "XLM_USD": {
        "feedId": "b7a8eba68a997cd0210c2e1e4ee811ad2d174b3611c22d9ebf16f4cb7e9ba850",
        "symbol": "XLM/USD",
        "name": "Stellar Lumens",
        "category": "crypto-alt",
        "priority": 3,
    },
    "AAPL_USD": {
        "feedId": "49f6b65cb1de6b10eaf75e7c03ca029c306d0357e91b5311b175084a5ad55688",
        "symbol": "AAPL/USD",
        "name": "Apple Inc",
        "category": "tech-stocks",
        "priority": 1,
    },
    "AMZN_USD": {
        "feedId": "b5d0e0fa58a1f8b81498ae670ce93c872d14434b72c364885d4fa1b257cbb07a",
        "symbol": "AMZN/USD",
        "name": "Amazon Inc",
        "category": "tech-stocks",
        "priority": 2,
    },
    "MSFT_USD": {
        "feedId": "d0ca23c1cc005e004ccf1db5bf76aeb6a49218f43dac3d4b275e92de12ded4d1",
        "symbol": "MSFT/USD",
        "name": "Microsoft Inc",
        "category": "tech-stocks",
        "priority": 3,
    },
    "GOOG_USD": {
        "feedId": "e65ff435be42630439c96396653a342829e877e2aafaeaf1a10d0ee5fd2cf3f2",
        "symbol": "GOOG/USD",
        "name": "Google Inc",
        "category": "tech-stocks",
        "priority": 4,
    },
    "META_USD": {
        "feedId": "78a3e3b8e676a8f73c439f5d749737034b139bbbe899ba5775216fba596607fe",
        "symbol": "META/USD",
        "name": "Meta Inc",
        "category": "tech-stocks",
        "priority": 5,
    },
    "NVDA_USD": {
        "feedId": "b1073854ed24cbc755dc527418f52b7d271f6cc967bbf8d8129112b18860a593",
        "symbol": "NVDA/USD",
        "name": "NVIDIA Inc",
        "category": "tech-stocks",
        "priority": 6,
    },
    "TSLA_USD": {
        "feedId": "16dad506d7db8da01c87581c87ca897a012a153557d4d578c3b9c9e1bc0632f1",
        "symbol": "TSLA/USD",
        "name": "Tesla Inc",
        "category": "other-stocks",
        "priority": 1,
    },
    "MSTR_USD": {
        "feedId": "e1e80251e5f5184f2195008382538e847fafc36f751896889dd3d1b1f6111f09",
        "symbol": "MSTR/USD",
        "name": "MicroStrategy",
        "category": "other-stocks",
        "priority": 2,
    },
    "SBUX_USD": {
        "feedId": "86cd9abb315081b136afc72829058cf3aaf1100d4650acb2edb6a8e39f03ef75",
        "symbol": "SBUX/USD",
        "name": "Starbucks",
        "category": "other-stocks",
        "priority": 3,
    },
    "JPM_USD": {
        "feedId": "7f4f157e57bfcccd934c566df536f34933e74338fe241a5425ce561acdab164e",
        "symbol": "JPM/USD",
        "name": "JPMorgan Chase & Co",
        "category": "other-stocks",
        "priority": 4,
    },
    "DIA_USD": {
        "feedId": "57cff3a9a4d4c87b595a2d1bd1bac0240400a84677366d632ab838bbbe56f763",
        "symbol": "DIA/USD",
        "name": "DIA",
        "category": "misc",
        "priority": 1,
    },
}

FEED_TO_KEY = {cfg["feedId"]: key for key, cfg in ASSETS.items()}

RATIOS = [
    {
        "name": "Gold / (SPY × 10)",
        "description": "Ounces of gold per 10 shares of S&P 500 ETF",
        "numerator": "XAU_USD",
        "denominator": "SPY_USD",
        "denominatorMultiplier": 10,
    },
    {
        "name": "Gold / Silver",
        "description": "Ounces of silver per ounce of gold",
        "numerator": "XAU_USD",
        "denominator": "XAG_USD",
        "denominatorMultiplier": 1,
    },
    {
        "name": "BTC / Gold",
        "description": "Ounces of gold per Bitcoin",
        "numerator": "BTC_USD",
        "denominator": "XAU_USD",
        "denominatorMultiplier": 1,
    },
    {
        "name": "Gold / QQQ",
        "description": "Gold price relative to Nasdaq 100 ETF",
        "numerator": "XAU_USD",
        "denominator": "QQQ_USD",
        "denominatorMultiplier": 1,
    },
    {
        "name": "BTC / (VOO × 100)",
        "description": "Bitcoin divided by 100 shares of Vanguard S&P 500 ETF",
        "numerator": "BTC_USD",
        "denominator": "VOO_USD",
        "denominatorMultiplier": 100,
    },
]


# ─── Fetch & Process ─────────────────────────────────────────────────────────

def _fetch_prices():
    endpoint = "https://hermes.pyth.network/api/latest_price_feeds"
    params = [("ids[]", cfg["feedId"]) for cfg in ASSETS.values()]
    
    try:
        resp = requests.get(endpoint, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Error fetching Pyth prices: {e}")
        return {}

    prices = {}
    for item in data:
        key = FEED_TO_KEY.get(item["id"])
        if key:
            try:
                # price = raw_price * 10^expo
                price = float(item["price"]["price"]) * (10 ** int(item["price"]["expo"]))
                prices[key] = price
            except (KeyError, ValueError):
                pass
    return prices

def _calculate_ratios(prices):
    results = []
    for r in RATIOS:
        num = prices.get(r["numerator"])
        den = prices.get(r["denominator"])
        if num is None or den is None:
            continue
        denom_price = den * r["denominatorMultiplier"]
        val = num / denom_price if denom_price != 0 else 0
        results.append({
            "name": r["name"],
            "description": r["description"],
            "value": val
        })
    return results

# ─── Public API ──────────────────────────────────────────────────────────────

def get_tradfi_data():
    """
    Main entry point for the TradFi skill.
    Fetches latest Pyth prices and returns a dict mapping.
    """
    prices = _fetch_prices()

    if not prices:
        return {"status": "error", "message": "Failed to fetch prices from Pyth Network"}

    result = {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "assets": {},
        "ratios": _calculate_ratios(prices)
    }

    for key, cfg in ASSETS.items():
        price = prices.get(key)
        if price is None:
            continue

        result["assets"][key] = {
            "symbol": cfg["symbol"],
            "name": cfg["name"],
            "category": cfg["category"],
            "price": price,
        }

    return result

if __name__ == "__main__":
    print(json.dumps(get_tradfi_data(), indent=2))
