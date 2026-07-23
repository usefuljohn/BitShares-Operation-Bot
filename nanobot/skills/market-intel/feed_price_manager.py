import time
import requests
import json
from datetime import datetime, timedelta, timezone

import sys
import argparse

class Logger:
    @staticmethod
    def error(msg):
        print(f"[-] ERROR: {msg}", file=sys.stderr)
    @staticmethod
    def info(msg):
        print(f"[*] {msg}", file=sys.stderr)

class RPC:
    """Minimal BitShares WebSocket RPC client."""
    def __init__(self, nodes=None):
        self.nodes = nodes or [
            "wss://api.bts.mobi/ws",
            "wss://dex.iobanker.com/ws",
            "wss://node.xbts.io/ws",
        ]
        self.ws = None
        self.db_api = None

    def connect(self):
        from websocket import create_connection
        from random import shuffle
        nodes = self.nodes[:]
        shuffle(nodes)
        for node in nodes:
            try:
                self.ws = create_connection(node, timeout=10)
                self.db_api = self._call(1, "database", [])
                return True
            except Exception:
                pass
        return False

    def _call(self, api_id, method, params):
        payload = json.dumps({
            "method": "call",
            "params": [api_id, method, params],
            "jsonrpc": "2.0",
            "id": 1
        })
        self.ws.send(payload)
        resp = json.loads(self.ws.recv())
        if "error" in resp:
            raise Exception(f"RPC Error: {resp['error']}")
        return resp.get("result")

    def db(self, method, params):
        return self._call(self.db_api, method, params)

    def rpc_call(self, method, params):
        return self.db(method, params)

    def close(self):
        if self.ws:
            self.ws.close()

def get_shared_rpc():
    rpc = RPC()
    if not rpc.connect():
        raise Exception("Failed to connect to any BitShares node")
    return rpc

ASSET_MAP = {
    "HONEST.USD": {"id": "1.3.5649", "precision": 4},
    "RUBLE": {"id": "1.3.1325", "precision": 5},
    "BTS": {"id": "1.3.0", "precision": 5}
}

def get_asset_info(rpc, symbol):
    """Fallback to fetch asset info if not in map."""
    symbol = symbol.upper()
    if symbol in ASSET_MAP:
        return ASSET_MAP[symbol]
    
    result = rpc.rpc_call("lookup_asset_symbols", [[symbol]])
    if not result or not result[0]:
        raise ValueError(f"Asset {symbol} not found.")
    
    return {
        "id": result[0]["id"],
        "precision": result[0]["precision"]
    }

def get_current_price(rpc, symbol):
    """Fetches the current price of an asset. Usually in BTS, but BTS is quoted in HONEST.USD."""
    symbol = symbol.upper()
    try:
        # If asset is BTS, we want its price in USD
        base_id = "1.3.5649" if symbol == "BTS" else "1.3.0"  # HONEST.USD if BTS, else BTS
        
        ticker = rpc.rpc_call("get_ticker", [base_id, symbol])
        if ticker and "highest_bid" in ticker and "lowest_ask" in ticker:
            bid = float(ticker["highest_bid"])
            ask = float(ticker["lowest_ask"])
            if bid > 0 and ask > 0:
                return (bid + ask) / 2
        
        if ticker and "latest" in ticker:
            return float(ticker["latest"])
        return None
    except Exception as e:
        Logger.error(f"Error fetching current price for {symbol}: {e}")
        return None

def fetch_kibana_prices(asset_id, start_ts, stop_ts):
    """Fetches feed prices from Kibana over the past 7 days."""
    url = "https://es.bitshares.dev/bitshares-*/_async_search"
    
    # ISO string without timezone info, suitable for strict_date_optional_time
    start_iso = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    stop_iso = datetime.fromtimestamp(stop_ts, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')

    request_data = {
        "size": 3000,
        "_source": False,
        "fields": [
            "operation_history.op_object.feed.settlement_price.base.amount",
            "operation_history.op_object.feed.settlement_price.quote.amount"
        ],
        "query": {
            "bool": {
                "filter": [
                    { "match": { "operation_history.op_object.feed.settlement_price.base.asset_id": asset_id } },
                    { "range": { "block_data.block_time": { "gte": start_iso, "lte": stop_iso } } }
                ]
            }
        }
    }

    try:
        response = requests.post(url, json=request_data, headers={'Content-Type': 'application/json'}, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # If it's running, poll it
        if data.get("is_running"):
            poll_url = f"https://es.bitshares.dev/_async_search/{data['id']}?wait_for_completion_timeout=10s"
            poll_resp = requests.get(poll_url, headers={'Content-Type': 'application/json'}, timeout=15)
            data = poll_resp.json()
        
        hits = data.get("response", {}).get("hits", {}).get("hits", [])
        
        results = []
        for hit in hits:
            fields = hit.get("fields", {})
            base_arr = fields.get("operation_history.op_object.feed.settlement_price.base.amount")
            quote_arr = fields.get("operation_history.op_object.feed.settlement_price.quote.amount")
            
            if base_arr and quote_arr:
                results.append({
                    "base": int(base_arr[0]),
                    "quote": int(quote_arr[0])
                })
        return results
    except Exception as e:
        Logger.error(f"Error fetching kibana prices: {e}")
        return []

def get_7day_average(rpc, symbol):
    """Calculates the 7-day average price for an asset."""
    symbol = symbol.upper()
    try:
        asset_info = get_asset_info(rpc, symbol)
        bts_info = get_asset_info(rpc, "BTS")
        
        now = time.time()
        start_time = now - (7 * 24 * 60 * 60)
        
        results = fetch_kibana_prices(asset_info["id"], start_time, now)
        if not results:
            return None
        
        prices = []
        for r in results:
            base_val = r["base"] / (10 ** asset_info["precision"])
            quote_val = r["quote"] / (10 ** bts_info["precision"])
            if base_val > 0:
                prices.append(quote_val / base_val)
        
        if prices:
            return sum(prices) / len(prices)
        return None
    except Exception as e:
        Logger.error(f"Error calculating 7-day average for {symbol}: {e}")
        return None

def query_feed_prices(assets=None):
    """
    Main entry point for feed prices tool.
    Returns the latest price and 7-day average for the specified assets.
    """
    if assets is None:
        assets = ["HONEST.USD", "RUBLE"]
        
    rpc = get_shared_rpc()
    results = {}
    
    for asset in assets:
        asset = asset.strip().upper()
        current_price = get_current_price(rpc, asset)
        avg_price = get_7day_average(rpc, asset)
        
        results[asset] = {
            "current_price": round(current_price, 5) if current_price else None,
            "average_7d_bts": round(avg_price, 5) if avg_price else None,
        }
        
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "prices": results
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query Feed Prices from BitShares/Kibana")
    parser.add_argument("--assets", nargs="+", help="Assets to query (default: HONEST.USD RUBLE)")
    args = parser.parse_args()

    print(json.dumps(query_feed_prices(assets=args.assets), indent=2))
