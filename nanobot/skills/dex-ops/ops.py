import argparse
import json
import sys
from datetime import datetime, timedelta
from rpc_client import get_client

def get_tx_header(client):
    props = client.get_dynamic_global_properties()
    head_block_number = props["head_block_number"]
    head_block_id = props["head_block_id"]
    head_block_time = props["time"]

    ref_block_num = head_block_number & 0xFFFF
    # Get bytes 4-8 of head_block_id (8-16 in hex)
    import struct
    prefix_hex = head_block_id[8:16]
    # Little-endian uint32
    ref_block_prefix = struct.unpack("<I", bytes.fromhex(prefix_hex))[0]

    # Expiration: time + 120s
    exp_time = datetime.strptime(head_block_time, "%Y-%m-%dT%H:%M:%S")
    expiration = (exp_time + timedelta(seconds=120)).strftime("%Y-%m-%dT%H:%M:%S")

    return {
        "ref_block_num": ref_block_num,
        "ref_block_prefix": ref_block_prefix,
        "expiration": expiration
    }

def construct_tx(client, ops):
    header = get_tx_header(client)
    tx = {
        "ref_block_num": header["ref_block_num"],
        "ref_block_prefix": header["ref_block_prefix"],
        "expiration": header["expiration"],
        "operations": ops,
        "extensions": [],
        "signatures": []
    }
    return tx

import os

# Ensure PROJECT_DIR is in sys.path
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

try:
    from nanobot.utils.helpers import (
        generate_deeplink,
        load_price_index,
        resolve_usd_price,
    )
except ImportError:
    def generate_deeplink(tx, app_name="BitShares Ops Tool"):
        import uuid
        from urllib.parse import quote
        request = {
            "type": "api",
            "id":   str(uuid.uuid4()),
            "payload": {
                "method": "injectedCall",
                "params": ["signAndBroadcast", json.dumps(tx), []],
                "appName": app_name,
                "chain":   "BTS",
                "browser": "web browser",
                "origin":  "localhost",
                "memo":    False
            }
        }
        return f"rawbeeteos://api?chain=BTS&request={quote(json.dumps(request))}"

    def load_price_index(output_dir=None, skill_dir=None, max_age_seconds=1800):
        paths = []
        if output_dir:
            paths.append(os.path.join(output_dir, "recent_price_index.json"))
        paths.append(os.path.expanduser("~/.bob/workspace/recent_price_index.json"))
        paths.append("recent_price_index.json")
        if skill_dir:
            paths.append(os.path.join(skill_dir, "recent_price_index.json"))
        paths.append(os.path.join(os.path.dirname(__file__), "..", "market-intel", "recent_price_index.json"))
        for path in paths:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                        prices = data.get("prices", {})
                        if prices:
                            return prices
                except Exception:
                    pass
        return {}

    _FALLBACK_PRICES = {"BTS": 0.0012, "BTC": 73000.0, "ETH": 2500.0, "XRP": 2.50, "Gold": 4500.0}

    def resolve_usd_price(symbol, prices):
        symbol_upper = symbol.upper()
        _INDEX_MAP = {"BTS": "BTS", "XBTSX.BTC": "BTC", "XBTSX.XAUT": "Gold",
                      "XBTSX.ETH": "ETH", "IOB.XRP": "XRP", "XBTSX.USDT": "USD", "HONEST.USD": "USD"}
        key = _INDEX_MAP.get(symbol_upper)
        if not key and "." in symbol_upper:
            suffix = symbol_upper.split(".", 1)[1]
            if suffix in ("USDT", "USD"):
                return 1.0
        if key == "USD":
            return 1.0
        if key and key in prices:
            return float(prices[key])
        return _FALLBACK_PRICES.get(key or symbol_upper)

# Sibling market-intel skill directory for price index discovery
_TRADFI_SKILL_DIR = os.path.join(os.path.dirname(__file__), "..", "market-intel")

def main():
    parser = argparse.ArgumentParser(description="BOB BitShares Operations Tool")
    parser.add_argument("--op", required=True, choices=["transfer", "balance", "limit_order", "credit_accept", "credit_repay"])
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--from", dest="from_acct")
    parser.add_argument("--to", dest="to_acct")
    parser.add_argument("--amount", type=float)
    parser.add_argument("--asset", default="BTS")
    parser.add_argument("--target_asset", help="Target asset for limit orders")
    parser.add_argument("--min_receive", type=float, help="Min to receive for limit orders")
    parser.add_argument("--slippage", type=float, default=None, help="Slippage percentage for automatic calculations (e.g. 1.0 for 1%)")
    parser.add_argument("--offer_id", help="Credit offer ID")
    parser.add_argument("--deal_id", help="Credit deal ID")
    parser.add_argument("--collateral", type=float)
    parser.add_argument("--collateral_asset", default="BTS")
    parser.add_argument("--output-dir", help="Directory to write transaction files")

    args = parser.parse_args()
    client = get_client(mock=args.mock)

    try:
        result = {}

        if args.op == "transfer":
            from_obj = client.get_account_by_name(args.from_acct)
            to_obj = client.get_account_by_name(args.to_acct)
            asset_obj = client.get_asset_by_symbol(args.asset)

            amount_int = int(args.amount * (10 ** asset_obj["precision"]))
            
            op = [0, {
                "fee": {"amount": 0, "asset_id": "1.3.0"},
                "from": from_obj["id"],
                "to": to_obj["id"],
                "amount": {"amount": amount_int, "asset_id": asset_obj["id"]},
                "extensions": []
            }]
            
            tx = construct_tx(client, [op])
            result = {
                "status": "success",
                "operation": "transfer",
                "summary": f"Transfer {args.amount} {args.asset} from {args.from_acct} to {args.to_acct}",
                "tx": tx,
                "deeplink": generate_deeplink(tx, "BitShares Ops Tool")
            }

        elif args.op == "balance":
            acct_obj = client.get_account_by_name(args.from_acct)
            result = {
                "status": "success",
                "account": args.from_acct,
                "id": acct_obj["id"],
                "message": f"Balance for {args.from_acct} requested. (Mock environment: 1000.00 BTS)"
            }

        elif args.op == "limit_order":
            from_obj = client.get_account_by_name(args.from_acct)
            sell_asset = client.get_asset_by_symbol(args.asset)
            receive_asset = client.get_asset_by_symbol(args.target_asset)
            
            # Resolve prices if min_receive is not specified
            if args.min_receive is None:
                if args.slippage is None:
                    raise ValueError("Either --min_receive or --slippage must be provided for limit orders.")
                
                prices = load_price_index(
                    output_dir=args.output_dir,
                    skill_dir=_TRADFI_SKILL_DIR,
                )
                price_sell = resolve_usd_price(sell_asset["symbol"], prices)
                price_recv = resolve_usd_price(receive_asset["symbol"], prices)
                
                if not price_sell or not price_recv:
                    raise ValueError(f"Could not resolve price for {sell_asset['symbol']} or {receive_asset['symbol']}")
                
                # Exchange rate: target units per 1 source unit
                rate = price_sell / price_recv
                
                # Calculate expected receive amount
                expected_receive = args.amount * rate
                
                # Apply slippage (sells: receive AT LEAST expected * (1 - slippage/100))
                min_receive_val = expected_receive * (1.0 - (args.slippage / 100.0))
                args.min_receive = round(min_receive_val, receive_asset["precision"])
                
                print(f"[*] Auto-resolved prices: {sell_asset['symbol']}={price_sell} USD, {receive_asset['symbol']}={price_recv} USD", file=sys.stderr)
                print(f"[*] Base exchange rate: {rate:.8f} {receive_asset['symbol']}/{sell_asset['symbol']}", file=sys.stderr)
                print(f"[*] Calculated target receive: {expected_receive:.6f} (with {args.slippage}% slippage limit: {args.min_receive:.6f})", file=sys.stderr)

            sell_amt = int(args.amount * (10 ** sell_asset["precision"]))
            recv_amt = int(args.min_receive * (10 ** receive_asset["precision"]))

            op = [1, {
                "fee": {"amount": 0, "asset_id": "1.3.0"},
                "seller": from_obj["id"],
                "amount_to_sell": {"amount": sell_amt, "asset_id": sell_asset["id"]},
                "min_to_receive": {"amount": recv_amt, "asset_id": receive_asset["id"]},
                "expiration": (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%S"),
                "fill_or_kill": False,
                "extensions": []
            }]
            
            tx = construct_tx(client, [op])
            result = {
                "status": "success",
                "operation": "limit_order_create",
                "summary": f"Sell {args.amount} {args.asset} for at least {args.min_receive} {args.target_asset}",
                "tx": tx,
                "deeplink": generate_deeplink(tx, "BitShares Ops Tool")
            }

        elif args.op == "credit_accept":
            borrower = client.get_account_by_name(args.from_acct)
            asset_obj = client.get_asset_by_symbol(args.asset)
            collateral_obj = client.get_asset_by_symbol(args.collateral_asset)

            op = [75, {
                "fee": {"amount": 0, "asset_id": "1.3.0"},
                "borrower": borrower["id"],
                "offer_id": args.offer_id,
                "borrow_amount": {"amount": int(args.amount * 10**asset_obj["precision"]), "asset_id": asset_obj["id"]},
                "collateral": {"amount": int(args.collateral * 10**collateral_obj["precision"]), "asset_id": collateral_obj["id"]},
                "max_fee_rate": 1000,
                "min_duration_seconds": 3600,
                "extensions": []
            }]
            
            tx = construct_tx(client, [op])
            result = {
                "status": "success",
                "operation": "credit_offer_accept",
                "summary": f"Accept credit offer {args.offer_id} for {args.amount} {args.asset}",
                "tx": tx,
                "deeplink": generate_deeplink(tx, "BitShares Ops Tool")
            }

        # Handle output directory file writing
        if "tx" in result and args.output_dir:
            import os
            os.makedirs(args.output_dir, exist_ok=True)
            prefix = f"{args.op}_{args.from_acct}"
            json_file = os.path.join(args.output_dir, f"bundle_{prefix}.json")
            with open(json_file, "w") as f:
                json.dump(result["tx"], f, indent=4)
            
            link_file = os.path.join(args.output_dir, f"deeplink_{prefix}.txt")
            with open(link_file, "w") as f:
                f.write(result["deeplink"])
                
            result["files"] = [os.path.abspath(json_file), os.path.abspath(link_file)]

        print(json.dumps(result, indent=2))

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, indent=2))
    finally:
        client.close()

if __name__ == "__main__":
    main()
