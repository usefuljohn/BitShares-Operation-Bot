#!/usr/bin/env python3
"""
Recent Price Index Manager

Fetches the latest prices for BTC, ETH, XRP, Gold (XAUT) from Pyth Network,
and BTS from BitShares Liquidity Pool 1.19.48.
Saves the results to recent_price_index.json.
"""

import sys
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

import json
import logging
from datetime import datetime
import requests

try:
    from nanobot.utils.helpers import get_shared_rpc
except ImportError:
    class RPC:
        """Minimal BitShares WebSocket RPC client fallback."""
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

        def get_pool_stats(self, pool_id):
            objs = self.db("get_objects", [[pool_id]])
            if not objs or not objs[0]:
                return None
            return objs[0]

        def close(self):
            if self.ws:
                self.ws.close()

    def get_shared_rpc():
        rpc = RPC()
        if not rpc.connect():
            raise Exception("Failed to connect to any BitShares node")
        return rpc

# Configure logging to match daemon
logger = logging.getLogger("NanobotDaemon")

# Paths
# Prioritize ~/.bob/workspace if available
workspace_dir = os.path.expanduser("~/.bob/workspace")
if os.path.isdir(workspace_dir):
    INDEX_FILE = os.path.join(workspace_dir, "recent_price_index.json")
elif os.access(".", os.W_OK) and not os.path.exists(os.path.join(os.path.dirname(__file__), "SKILL.md")):
    # If we are NOT in the skill directory but have write access, use CWD
    INDEX_FILE = "recent_price_index.json"
else:
    # Default to skill directory
    INDEX_FILE = os.path.join(os.path.dirname(__file__), "recent_price_index.json")

os.makedirs(os.path.dirname(os.path.abspath(INDEX_FILE)), exist_ok=True)

# Pyth Feed IDs
PYTH_FEEDS = {
    "BTC": "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
    "ETH": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
    "XRP": "ec5d399846a9209f3fe5881d70aae9268c94339ff9817e8d18ff19fa05eea1c8",
    "Gold": "765d2ba906dbc32ca17cc11f5310a89e9ee1f6420508c63861f2f8ba4ee34bb2",  # XAUT
}

def update_recent_price_index(rpc: RPC):
    """
    Fetches latest prices from Pyth and LP 1.19.48, and writes to JSON.
    Failures are logged quietly to nanobot.log.
    """
    prices = {}
    
    # 1. Fetch Pyth Prices
    endpoint = "https://hermes.pyth.network/api/latest_price_feeds"
    params = [("ids[]", feed_id) for feed_id in PYTH_FEEDS.values()]
    
    try:
        resp = requests.get(endpoint, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        feed_to_symbol = {v: k for k, v in PYTH_FEEDS.items()}
        
        for item in data:
            symbol = feed_to_symbol.get(item["id"])
            if symbol:
                try:
                    price = float(item["price"]["price"]) * (10 ** int(item["price"]["expo"]))
                    prices[symbol] = round(price, 8)
                except (KeyError, ValueError):
                    pass
    except Exception as e:
        logger.error(f"Price Index: Failed to fetch Pyth Network prices: {e}")

    # 2. Fetch BitShares BTS/USD Price from LP 1.19.48
    try:
        stats = rpc.get_pool_stats("1.19.48")
        if stats:
            # asset_a is 1.3.0 (BTS) precision 5
            # asset_b is 1.3.5589 (USDT) precision 6
            bal_a = float(stats["balance_a"]) / (10 ** 5)
            bal_b = float(stats["balance_b"]) / (10 ** 6)
            
            if bal_a > 0:
                bts_price = bal_b / bal_a
                prices["BTS"] = round(bts_price, 8)
        else:
            logger.error("Price Index: Could not fetch LP 1.19.48 stats.")
    except Exception as e:
        logger.error(f"Price Index: Failed to fetch BTS pool price: {e}")

    # 3. Save to JSON if we got any prices
    if prices:
        output = {
            "timestamp": datetime.now().isoformat(),
            "prices": prices
        }
        
        # Load existing if available to preserve any missing fields during a partial failure
        try:
            if os.path.exists(INDEX_FILE):
                with open(INDEX_FILE, "r") as f:
                    existing = json.load(f)
                    # Merge new prices over old ones to prevent complete data loss if one API fails
                    if "prices" in existing:
                        for k, v in prices.items():
                            existing["prices"][k] = v
                        output["prices"] = existing["prices"]
        except Exception:
            pass

        try:
            with open(INDEX_FILE, "w") as f:
                json.dump(output, f, indent=2)
            logger.info(f"Price Index updated successfully: {list(prices.keys())}")
        except Exception as e:
            logger.error(f"Price Index: Failed to write JSON file: {e}")
    else:
        logger.error("Price Index: No prices fetched, JSON not updated.")

if __name__ == "__main__":
    rpc_client = get_shared_rpc()
    update_recent_price_index(rpc_client)
    rpc_client.close()
