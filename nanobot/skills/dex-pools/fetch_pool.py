import websocket
import json
import math
import argparse
import sys
import csv
import os
from datetime import datetime

# Ensure PROJECT_DIR is in sys.path
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

WSS_URL = "wss://dex.iobanker.com/ws"
# Default log file path relative to the script directory
DEFAULT_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lp_yield_history.csv")

try:
    from nanobot.utils.helpers import BitSharesRPC as BaseRPC
    class BitSharesRPC(BaseRPC):
        def __init__(self, url):
            super().__init__(nodes=[url] if url else None)
            if not self.connect():
                print(f"Could not connect to {url}")
                sys.exit(1)
        def call(self, method, params):
            return self.db(method, params)
except ImportError:
    class BitSharesRPC:
        def __init__(self, url):
            self.url = url
            try:
                self.ws = websocket.create_connection(url, timeout=15)
            except Exception as e:
                print(f"Could not connect to {url}: {e}")
                sys.exit(1)
            self.request_id = 1
            
        def call(self, method, params):
            payload = {"jsonrpc": "2.0", "method": "call", "params": [0, method, params], "id": self.request_id}
            self.ws.send(json.dumps(payload))
            response = json.loads(self.ws.recv())
            self.request_id += 1
            return response.get("result")

        def close(self):
            self.ws.close()

def get_last_entry(pool_id, log_file):
    """Returns (pps, timestamp) for a pool_id from the CSV log."""
    if not os.path.exists(log_file):
        return None, None
    try:
        with open(log_file, mode='r') as f:
            reader = list(csv.DictReader(f))
            pool_entries = [row for row in reader if row['pool_id'] == pool_id]
            if pool_entries:
                last = pool_entries[-1]
                return float(last['pps']), datetime.fromisoformat(last['timestamp'])
    except Exception as e:
        print(f"Warning: Could not read log: {e}")
    return None, None

def log_to_csv(data, log_file):
    file_exists = os.path.exists(log_file)
    fieldnames = ['timestamp', 'pool_id', 'pair', 'pps', 'tvl', 'price']
    with open(log_file, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(data)

def process_pool(rpc, pool_id, log=False, log_file=DEFAULT_LOG_FILE):
    try:
        pool_data = rpc.call("get_objects", [[pool_id]])[0]
        assets = rpc.call("get_objects", [[pool_data["asset_a"], pool_data["asset_b"], pool_data["share_asset"]]])
        asset_a, asset_b, share_asset = assets
        share_dyn = rpc.call("get_objects", [[share_asset["dynamic_asset_data_id"]]])[0]
        
        bal_a = int(pool_data["balance_a"]) / (10 ** asset_a["precision"])
        bal_b = int(pool_data["balance_b"]) / (10 ** asset_b["precision"])
        supply = int(share_dyn["current_supply"]) / (10 ** share_asset["precision"])
        
        price_a_in_b = bal_b / bal_a if bal_a > 0 else 0
        pps = math.sqrt(bal_a * bal_b) / supply if supply > 0 else 0
        
        symbol_a, symbol_b = asset_a["symbol"], asset_b["symbol"]
        tvl_val = bal_b * 2
        
        # APR Logic
        last_pps, last_time = get_last_entry(pool_id, log_file)
        now = datetime.now()
        
        print("\n" + "=" * 60)
        print(f"POOL: {symbol_a}/{symbol_b} ({pool_id})")
        print("-" * 60)
        print(f"TVL:          {tvl_val:>18,.2f} {symbol_b}-equiv")
        print(f"PPS Index:    {pps:>18.10f}")
        
        if last_pps and last_time:
            yield_pct = ((pps / last_pps) - 1) * 100
            time_diff = now - last_time
            hours = time_diff.total_seconds() / 3600
            
            print(f"Yield Change: {yield_pct:>18.6f} %")
            print(f"Time Elapsed: {hours:>18.2f} hours")
            
            if hours > 0.01: # Avoid division by near-zero
                # Annualize: (Yield / Hours) * 8760 hours in a year
                apr = (yield_pct / hours) * 8760
                print(f"Estimated APR: {apr:>17.2f} %")
            else:
                print(f"Estimated APR: {'N/A (Too soon)':>18}")
        else:
            print(f"Status:       {'First Log Entry (Historical data not found)':>18}")

        if log:
            log_to_csv({
                'timestamp': now.isoformat(),
                'pool_id': pool_id,
                'pair': f"{symbol_a}/{symbol_b}",
                'pps': pps,
                'tvl': tvl_val,
                'price': price_a_in_b
            }, log_file)

    except Exception as e:
        print(f"Error processing {pool_id}: {e}")

def main():
    default_pools = ["1.19.0", "1.19.48", "1.19.277"]
    parser = argparse.ArgumentParser()
    parser.add_argument("pools", nargs="*", default=default_pools, help="Pool IDs to process")
    parser.add_argument("--log", action="store_true", help="Log data to CSV")
    parser.add_argument("--log-file", default=DEFAULT_LOG_FILE, help="Path to log file")
    args = parser.parse_args()

    rpc = BitSharesRPC(WSS_URL)
    for pid in args.pools:
        process_pool(rpc, pid, log=args.log, log_file=args.log_file)
    rpc.close()

if __name__ == "__main__":
    main()
