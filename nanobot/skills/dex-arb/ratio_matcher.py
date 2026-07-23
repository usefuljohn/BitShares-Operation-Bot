#!/usr/bin/env python3
"""
BitShares Ratio Matcher & Arbitrage Swapper
===========================================
Queries the reserves of:
- Pool A (1.19.539): BTS / BTWTY.BTC
- Pool B (1.19.58): BTS / XBTSX.BTC

Determines which BTC asset is overvalued relative to the other (higher price in BTS).
Calculates the exact trade size needed to bring both pools to equilibrium using binary search.
Generates a two-hop Beet deep link and transaction bundle to execute the arbitrage.
"""

import os
import sys
import json
import uuid
import argparse
from datetime import datetime, timedelta
from urllib.parse import quote
from websocket import create_connection

# Resolve current script directory for default config path
script_dir = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(script_dir, "config.json")


class RPCClient:
    def __init__(self, url):
        self.ws = create_connection(url, timeout=15)
        self._rid = 1

    def call(self, method, params):
        payload = {
            "method": method,
            "params": params,
            "jsonrpc": "2.0",
            "id": self._rid
        }
        self._rid += 1
        self.ws.send(json.dumps(payload))
        resp = json.loads(self.ws.recv())
        if "error" in resp:
            raise RuntimeError(f"RPC error: {resp['error']}")
        return resp["result"]

    def get_objects(self, ids):
        return self.call("get_objects", [ids])

    def get_balances(self, acct, assets):
        raw = self.call("get_account_balances", [acct, assets])
        return {b["asset_id"]: int(b["amount"]) for b in raw}

    def get_dynamic_props(self):
        return self.call("get_dynamic_global_properties", [])

    def get_account_id(self, name_or_id):
        if name_or_id.startswith("1.2."):
            return name_or_id
        try:
            res = self.call("lookup_account_names", [[name_or_id]])
            if res and res[0]:
                return res[0]["id"]
        except Exception:
            pass
        try:
            res = self.call("get_account_by_name", [name_or_id])
            if res and "id" in res:
                return res["id"]
        except Exception:
            pass
        raise RuntimeError(f"Could not resolve account name '{name_or_id}' to a BitShares ID")

    def close(self):
        self.ws.close()


def pool_swap_output(pool, amount_in, asset_in_id):
    """Constant-product swap: dy = (y * dx_after_fee) / (x + dx_after_fee)"""
    is_a = pool["asset_a"] == asset_in_id
    bal_in = int(pool["balance_a"] if is_a else pool["balance_b"])
    bal_out = int(pool["balance_b"] if is_a else pool["balance_a"])
    fee_pct = int(pool.get("taker_fee_percent", 0))
    dx = amount_in * (10_000 - fee_pct) // 10_000
    return (bal_out * dx) // (bal_in + dx)


def find_equilibrium_size(pool_over, pool_under, over_asset_id, under_asset_id, bts_id):
    """
    Finds the trade size (in satoshis of over_asset_id) that brings pool_over and pool_under
    into equilibrium. R1_new(dy) = R2_new(dy).
    """
    # Overvalued pool reserve of over_asset_id
    is_a_over = pool_over["asset_a"] == over_asset_id
    over_res = int(pool_over["balance_a"] if is_a_over else pool_over["balance_b"])
    
    # Binary search bounds
    low = 0
    high = int(over_res * 0.95)  # Cap at 95% of pool reserve to avoid drainage issues
    
    best_dy = 0
    
    for _ in range(60):
        mid = (low + high) // 2
        if mid == low or mid == high:
            break
            
        # Sim swap 1: sell overvalued BTC for BTS
        dx_bts = pool_swap_output(pool_over, mid, over_asset_id)
        
        # Post reserves of pool_over
        x1_new = int(pool_over["balance_b"] if is_a_over else pool_over["balance_a"]) - dx_bts
        y1_new = int(pool_over["balance_a"] if is_a_over else pool_over["balance_b"]) + mid
        r1_new = x1_new / y1_new
        
        # Sim swap 2: sell BTS for undervalued BTC
        is_a_under = pool_under["asset_a"] == bts_id
        dy_under = pool_swap_output(pool_under, dx_bts, bts_id)
        
        x2_new = int(pool_under["balance_a"] if is_a_under else pool_under["balance_b"]) + dx_bts
        y2_new = int(pool_under["balance_b"] if is_a_under else pool_under["balance_a"]) - dy_under
        
        if y2_new <= 0:
            high = mid
            continue
            
        r2_new = x2_new / y2_new
        
        if r1_new > r2_new:
            # Pool over is still overvalued; swap more
            low = mid
            best_dy = mid
        else:
            # Swapped too much; swap less
            high = mid
            
    return best_dy


def op_pool_swap(account_id, pool_id, sell_amt, sell_asset, min_receive, buy_asset, bts_id="1.3.0"):
    return [63, {
        "fee": {"amount": "0", "asset_id": bts_id},
        "account": account_id,
        "pool": pool_id,
        "amount_to_sell":  {"amount": str(int(sell_amt)),    "asset_id": sell_asset},
        "min_to_receive":  {"amount": str(int(min_receive)), "asset_id": buy_asset},
        "extensions": []
    }]


def build_deep_link(rpc, operations, app_name="Ratio Matcher Arbitrage"):
    props = rpc.get_dynamic_props()
    exp = (datetime.strptime(props["time"], "%Y-%m-%dT%H:%M:%S")
           + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    tr = {
        "ref_block_num": 0,
        "ref_block_prefix": 0,
        "expiration": exp,
        "operations": operations,
        "extensions": [],
        "signatures": []
    }
    request = {
        "type": "api",
        "id": str(uuid.uuid4()),
        "payload": {
            "method": "injectedCall",
            "params": ["signAndBroadcast", json.dumps(tr), []],
            "appName": app_name,
            "chain": "BTS",
            "browser": "web browser",
            "origin": "localhost",
            "memo": False
        }
    }
    link = f"rawbeeteos://api?chain=BTS&request={quote(json.dumps(request))}"
    return link, request


def main():
    parser = argparse.ArgumentParser(description="BitShares LP Ratio Matching Arbitrage App")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to config.json")
    parser.add_argument("--account", default="johnr", help="BitShares account name or ID (default: johnr)")
    parser.add_argument("--node", help="BitShares WebSocket node URL override")
    parser.add_argument("--slippage", type=float, help="Slippage tolerance (e.g. 0.01 for 1.0%%)")
    parser.add_argument("--amount", type=float, help="Manual swap amount in BTC (skips equilibrium logic)")
    parser.add_argument("--output-dir", default=None, help="Directory to write output files (default: script directory)")
    parser.add_argument("--emit-deeplink", action="store_true", help="Also write a deeplink .txt file")
    parser.add_argument("--force", action="store_true", help="Generate outputs even if trade is unprofitable")
    parser.add_argument("--dry-run", action="store_true", help="Print calculations without writing files")
    args = parser.parse_args()

    # Load configuration
    if not os.path.exists(args.config):
        print(f"[!] Error: Config file not found at {args.config}")
        sys.exit(1)

    with open(args.config, "r") as f:
        config = json.load(f)

    node_url = args.node or config.get("node_url", "wss://dex.iobanker.com/ws")
    account_input = args.account
    slippage_tol = args.slippage or config.get("default_slippage_tolerance", 0.01)

    pool_btwty_id = config["pool_btwty_btc"]
    pool_xbtsx_id = config["pool_xbtsx_btc"]
    bts_id = config["asset_bts"]
    btwty_btc_id = config["asset_btwty_btc"]
    xbtsx_btc_id = config["asset_xbtsx_btc"]
    decimals = config["decimals"]

    print(f"[*] Connecting to BitShares node: {node_url}")
    rpc = RPCClient(node_url)

    try:
        # Resolve account
        account_id = rpc.get_account_id(account_input)
        print(f"[*] Account: {account_input} ({account_id})")

        # Fetch pool objects and balances
        print(f"[*] Fetching live pool states and account balances...")
        pools = rpc.get_objects([pool_btwty_id, pool_xbtsx_id])
        pool_btwty = pools[0]
        pool_xbtsx = pools[1]

        if not pool_btwty or not pool_xbtsx:
            print("[!] Error: Could not fetch pool objects from blockchain.")
            sys.exit(1)

        balances = rpc.get_balances(account_id, [bts_id, btwty_btc_id, xbtsx_btc_id])
        bal_bts = balances.get(bts_id, 0)
        bal_btwty = balances.get(btwty_btc_id, 0)
        bal_xbtsx = balances.get(xbtsx_btc_id, 0)

        # Print current pool reserves
        bts_in_btwty = int(pool_btwty["balance_a"] if pool_btwty["asset_a"] == bts_id else pool_btwty["balance_b"])
        btc_in_btwty = int(pool_btwty["balance_b"] if pool_btwty["asset_a"] == bts_id else pool_btwty["balance_a"])
        
        bts_in_xbtsx = int(pool_xbtsx["balance_a"] if pool_xbtsx["asset_a"] == bts_id else pool_xbtsx["balance_b"])
        btc_in_xbtsx = int(pool_xbtsx["balance_b"] if pool_xbtsx["asset_a"] == bts_id else pool_xbtsx["balance_a"])

        # Calculate current real prices (BTS per BTC)
        price_btwty = (bts_in_btwty / 10**decimals[bts_id]) / (btc_in_btwty / 10**decimals[btwty_btc_id])
        price_xbtsx = (bts_in_xbtsx / 10**decimals[bts_id]) / (btc_in_xbtsx / 10**decimals[xbtsx_btc_id])

        print(f"\n=== Live Market Summary ===")
        print(f"Pool A ({pool_btwty_id}) BTS:BTWTY.BTC reserves:")
        print(f"  BTS        : {bts_in_btwty / 10**decimals[bts_id]:,.5f}")
        print(f"  BTWTY.BTC  : {btc_in_btwty / 10**decimals[btwty_btc_id]:.8f}")
        print(f"  Price Ratio: {price_btwty:,.5f} BTS/BTC")
        print(f"Pool B ({pool_xbtsx_id}) BTS:XBTSX.BTC reserves:")
        print(f"  BTS        : {bts_in_xbtsx / 10**decimals[bts_id]:,.5f}")
        print(f"  XBTSX.BTC  : {btc_in_xbtsx / 10**decimals[xbtsx_btc_id]:.8f}")
        print(f"  Price Ratio: {price_xbtsx:,.5f} BTS/BTC")
        print(f"===========================\n")

        print(f"Account Balances:")
        print(f"  BTS        : {bal_bts / 10**decimals[bts_id]:,.5f}")
        print(f"  BTWTY.BTC  : {bal_btwty / 10**decimals[btwty_btc_id]:.8f}")
        print(f"  XBTSX.BTC  : {bal_xbtsx / 10**decimals[xbtsx_btc_id]:.8f}\n")

        # Determine overvalued vs undervalued BTC
        if price_btwty > price_xbtsx:
            over_symbol = "BTWTY.BTC"
            over_id = btwty_btc_id
            over_pool_id = pool_btwty_id
            over_pool = pool_btwty
            over_bal = bal_btwty

            under_symbol = "XBTSX.BTC"
            under_id = xbtsx_btc_id
            under_pool_id = pool_xbtsx_id
            under_pool = pool_xbtsx
            under_bal = bal_xbtsx
        else:
            over_symbol = "XBTSX.BTC"
            over_id = xbtsx_btc_id
            over_pool_id = pool_xbtsx_id
            over_pool = pool_xbtsx
            over_bal = bal_xbtsx

            under_symbol = "BTWTY.BTC"
            under_id = btwty_btc_id
            under_pool_id = pool_btwty_id
            under_pool = pool_btwty
            under_bal = bal_btwty

        ratio_diff_pct = abs(price_btwty - price_xbtsx) / min(price_btwty, price_xbtsx) * 100
        print(f"Overvalued Asset : {over_symbol} (costs {max(price_btwty, price_xbtsx):,.5f} BTS)")
        print(f"Undervalued Asset: {under_symbol} (costs {min(price_btwty, price_xbtsx):,.5f} BTS)")
        print(f"Price Disparity  : {ratio_diff_pct:.4f}%\n")

        # Check available balance of the overvalued BTC asset
        if over_bal <= 0:
            print(f"[!] ERROR: Account available balance of overvalued asset {over_symbol} is 0. Cannot perform swap.")
            sys.exit(1)

        # Calculate swap amount
        if args.amount is not None:
            # Manual trade size
            swap_size_sat = int(args.amount * 10**decimals[over_id])
            print(f"[*] Using manually specified swap size: {args.amount:.8f} {over_symbol}")
            if swap_size_sat > over_bal:
                print(f"[!] NOTICE: Manually specified amount ({args.amount:.8f} {over_symbol}) exceeds available account balance ({over_bal / 10**decimals[over_id]:.8f} {over_symbol}).")
                print(f"[*] Capping trade size to available balance of {over_bal / 10**decimals[over_id]:.8f} {over_symbol}.")
                swap_size_sat = over_bal
        else:
            # Dynamic equilibrium size
            print("[*] Estimating equilibrium trade size using binary search...")
            eq_size_sat = find_equilibrium_size(over_pool, under_pool, over_id, under_id, bts_id)
            print(f"[*] Equilibrium trade size: {eq_size_sat / 10**decimals[over_id]:.8f} {over_symbol}")
            
            if eq_size_sat == 0:
                print("[!] Ratios are already in equilibrium or difference is too small. Exiting.")
                sys.exit(0)

            # Cap trade size at available account balance
            if eq_size_sat > over_bal:
                print(f"[!] NOTICE: Calculated equilibrium size ({eq_size_sat / 10**decimals[over_id]:.8f} {over_symbol}) exceeds available account balance ({over_bal / 10**decimals[over_id]:.8f} {over_symbol}).")
                print(f"[*] Capping trade size to available balance of {over_bal / 10**decimals[over_id]:.8f} {over_symbol}.")
                swap_size_sat = over_bal
            else:
                swap_size_sat = eq_size_sat

        print(f"[*] Target trade size: {swap_size_sat / 10**decimals[over_id]:.8f} {over_symbol}")

        # Simulate swaps
        # Step 1: swap overvalued BTC to BTS in overvalued pool
        bts_out_expected = pool_swap_output(over_pool, swap_size_sat, over_id)
        min_bts_out = int(bts_out_expected * (1.0 - slippage_tol))
        
        # Step 2: swap to undervalued BTC in undervalued pool
        # Expected: assumes no slippage on first hop
        under_out_expected = pool_swap_output(under_pool, bts_out_expected, bts_id)
        
        # Determine execution path based on available BTS balance to cover slippage gap between hops
        slippage_gap = bts_out_expected - min_bts_out
        under_out_from_min_bts = pool_swap_output(under_pool, min_bts_out, bts_id)

        if bal_bts >= slippage_gap:
            has_slippage_buffer = True
            second_sell_amt = bts_out_expected
            min_under_out = int(under_out_expected * (1.0 - slippage_tol))
        else:
            has_slippage_buffer = False
            second_sell_amt = min_bts_out
            min_under_out = int(under_out_from_min_bts * (1.0 - slippage_tol))

        expected_gain = under_out_expected - swap_size_sat
        gain_pct = (expected_gain / swap_size_sat) * 100

        min_gain = min_under_out - swap_size_sat
        min_gain_pct = (min_gain / swap_size_sat) * 100

        print(f"\n=== Simulation Results ===")
        print(f"Sell Amount           : {swap_size_sat / 10**decimals[over_id]:.8f} {over_symbol}")
        print(f"Expected Intermediate : {bts_out_expected / 10**decimals[bts_id]:,.5f} BTS  (Min Guaranteed: {min_bts_out / 10**decimals[bts_id]:,.5f} BTS)")
        print(f"Second Leg Input Size : {second_sell_amt / 10**decimals[bts_id]:,.5f} BTS")
        print(f"Expected Final        : {under_out_expected / 10**decimals[under_id]:.8f} {under_symbol} (Min Guaranteed: {min_under_out / 10**decimals[under_id]:.8f} {under_symbol})")
        print(f"Expected Net Gain/Loss: {expected_gain / 10**decimals[over_id]:+.8f} BTC ({gain_pct:+.4f}%)")
        print(f"Min Guaranteed Gain   : {min_gain / 10**decimals[over_id]:+.8f} BTC ({min_gain_pct:+.4f}%)")
        if has_slippage_buffer:
            print(f"[*] Note: Account has sufficient BTS balance ({bal_bts / 10**decimals[bts_id]:,.5f} BTS) to cover the potential slippage gap of {slippage_gap / 10**decimals[bts_id]:,.5f} BTS.")
        else:
            print(f"[!] Note: Capped second leg input to min_bts_out due to low account BTS balance.")
        print(f"==========================\n")

        # Profitability check (check expected gain, but warn about min guaranteed gain as well)
        if expected_gain <= 0:
            print(f"[WARNING] This trade is UNPROFITABLE. Expected net loss of {abs(expected_gain) / 10**decimals[over_id]:.8f} BTC.")
            if not args.force:
                print("[!] Refusing to write transaction outputs. Use --force to override.")
                sys.exit(1)
            else:
                print("[*] Continuing anyway due to --force flag.")
        elif min_gain <= 0:
            print(f"[WARNING] Under worst-case slippage ({slippage_tol*100}%), this trade could result in a net loss of {abs(min_gain) / 10**decimals[over_id]:.8f} BTC.")

        # Build operations
        # Operation 1: Sell overvalued BTC, receive BTS (min_bts_out minimum)
        op1 = op_pool_swap(account_id, over_pool_id, swap_size_sat, over_id, min_bts_out, bts_id, bts_id)
        # Operation 2: Sell second_sell_amt BTS, receive undervalued BTC (min_under_out minimum)
        op2 = op_pool_swap(account_id, under_pool_id, second_sell_amt, bts_id, min_under_out, under_id, bts_id)
        ops = [op1, op2]

        # Build Beet deep link
        link, request_data = build_deep_link(rpc, ops)

        print(f"=== Transaction Summary ===")
        print(f"Operation 1: Swap {swap_size_sat / 10**decimals[over_id]:.8f} {over_symbol} -> min {min_bts_out / 10**decimals[bts_id]:,.5f} BTS")
        print(f"Operation 2: Swap {second_sell_amt / 10**decimals[bts_id]:,.5f} BTS -> min {min_under_out / 10**decimals[under_id]:.8f} {under_symbol}")
        print(f"===========================\n")

        if args.dry_run:
            print("[DRY RUN] No files written.")
            return

        # Write files — use account name for file naming
        acct_name = account_input
        out_dir = args.output_dir or script_dir
        os.makedirs(out_dir, exist_ok=True)

        # Always write the JSON bundle
        bundle_path = os.path.join(out_dir, f"ratio_{acct_name}.json")
        with open(bundle_path, "w") as f:
            json.dump(request_data, f, indent=4)
        print(f"\n[+] JSON bundle → {bundle_path}")

        files = [bundle_path]

        # Optionally write deeplink
        if args.emit_deeplink:
            link_path = os.path.join(out_dir, f"deeplink_ratio_{acct_name}.txt")
            with open(link_path, "w") as f:
                f.write(link)
            print(f"[+] Deep link  → {link_path}")
            files.append(link_path)

        # Print JSON summary for agent consumption
        print(json.dumps({"status": "ok", "files": files}, indent=2))

    finally:
        rpc.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[+] Exited by user.")
        sys.exit(0)
