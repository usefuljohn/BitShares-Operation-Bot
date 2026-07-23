import sys
import json
import argparse
from poolmap import main as find_best_path

def main():
    parser = argparse.ArgumentParser(description="BitShares Liquidity Pool Router Tool")
    parser.add_argument("--from", dest="from_token", required=True, help="Token to trade from (e.g., BTS)")
    parser.add_argument("--to", dest="to_token", required=True, help="Token to trade to (e.g., HONEST.MONEY)")
    parser.add_argument("--amount", type=float, default=1.0, help="Amount of 'from' token to trade")
    parser.add_argument("--mock", action="store_true", help="Use mock data (for testing)")

    args = parser.parse_args()

    result_holder = {}
    try:
        find_best_path(
            from_token=args.from_token,
            to_token=args.to_token,
            input_amount=args.amount,
            mock=args.mock,
            result_holder=result_holder,
            plot=False
        )

        if "result" in result_holder:
            price, token_path, pool_path, balances, fees = result_holder["result"]
            cache = result_holder.get("cache", {})
            
            # Map IDs to symbols
            symbol_path = [cache.get(f"1.3.{i}", {}).get("symbol", str(i)) for i in token_path]
            
            # Formulate a clean response
            output = {
                "status": "success",
                "from": args.from_token,
                "to": args.to_token,
                "input_amount": args.amount,
                "output_amount": float(price),
                "path": symbol_path,
                "pools": pool_path,
                "summary": f"Trade {args.amount} {args.from_token} for approx {price:.6f} {args.to_token}"
            }
            print(json.dumps(output, indent=2))
        else:
            print(json.dumps({
                "status": "error",
                "message": f"No path found from {args.from_token} to {args.to_token}"
            }, indent=2))

    except Exception as e:
        print(json.dumps({
            "status": "error",
            "message": str(e)
        }, indent=2))

if __name__ == "__main__":
    main()
