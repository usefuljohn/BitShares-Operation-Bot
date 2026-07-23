#!/usr/bin/env python3
"""
Autonomous Strategy Monitor
============================
Collects BitShares DEX state, evaluates trigger conditions against configurable
thresholds, and outputs recommended actions for the agent heartbeat loop.

Integrates with the existing price_index_manager (refreshes recent_price_index.json)
and sofr_rate_calculator (fetches live SOFR) rather than duplicating their work.

Usage:
    python3 strategy_monitor.py                # Human-readable summary
    python3 strategy_monitor.py --json         # Machine-readable JSON report
    python3 strategy_monitor.py --json --quiet # Suppress stderr diagnostics
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# ── Path setup ───────────────────────────────────────────────────────────────
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(SKILL_DIR))
sys.path.insert(0, PROJECT_DIR)

TRADFI_DIR = os.path.join(os.path.dirname(SKILL_DIR), "market-intel")
CREDIT_FUND_DIR = os.path.join(os.path.dirname(SKILL_DIR), "dex-credit")

STATE_FILE = os.path.join(SKILL_DIR, "strategy_state.json")
DEFAULT_RULES_FILE = os.path.join(SKILL_DIR, "strategy_rules.json")
PERSISTENT_RULES_FILE = os.path.expanduser("~/.bob/strategy_rules.json")

# ── Node list ────────────────────────────────────────────────────────────────
NODES = [
    "wss://dex.iobanker.com/ws",
    "wss://api.bts.mobi/ws",
    "wss://node.xbts.io/ws",
]


# ── RPC Client (fallback if nanobot helpers unavailable) ─────────────────────
try:
    from nanobot.utils.helpers import get_shared_rpc
except ImportError:
    import websocket as _ws_mod

    class _FallbackRPC:
        def __init__(self, nodes=None):
            self.nodes = nodes or NODES
            self.ws = None
            self.db_api = None

        def connect(self):
            from random import shuffle
            nodes = self.nodes[:]
            shuffle(nodes)
            for node in nodes:
                try:
                    self.ws = _ws_mod.create_connection(node, timeout=10)
                    self.db_api = self._call(1, "database", [])
                    print(f"[+] Connected to {node}", file=sys.stderr)
                    return True
                except Exception as e:
                    print(f"[-] Failed: {node}: {e}", file=sys.stderr)
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
                raise RuntimeError(f"RPC Error: {resp['error']}")
            return resp.get("result")

        def db(self, method, params):
            return self._call(self.db_api, method, params)

        def get_objects(self, ids):
            return self.db("get_objects", [ids])

        def get_pool_stats(self, pool_id):
            """Fetch a pool object by ID — compatible with price_index_manager."""
            objs = self.get_objects([pool_id])
            if not objs or not objs[0]:
                return None
            return objs[0]

        def close(self):
            if self.ws:
                self.ws.close()

    def get_shared_rpc():
        rpc = _FallbackRPC()
        if not rpc.connect():
            raise RuntimeError("Failed to connect to any BitShares node")
        return rpc


# ── Price index refresh ──────────────────────────────────────────────────────
def refresh_price_index(rpc, quiet=False):
    """Run the market-intel price_index_manager to update recent_price_index.json."""
    sys.path.insert(0, TRADFI_DIR)
    try:
        from price_index_manager import update_recent_price_index
        update_recent_price_index(rpc)
        if not quiet:
            print("[*] Price index refreshed.", file=sys.stderr)
    except Exception as e:
        print(f"[!] Failed to refresh price index: {e}", file=sys.stderr)
    finally:
        # Remove market-intel from path to avoid contamination
        if TRADFI_DIR in sys.path:
            sys.path.remove(TRADFI_DIR)


def load_price_index():
    """Load current prices from recent_price_index.json."""
    search_paths = [
        os.path.expanduser("~/.bob/workspace/recent_price_index.json"),
        os.path.join(TRADFI_DIR, "recent_price_index.json"),
        "recent_price_index.json",
    ]
    for path in search_paths:
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    data = json.load(f)
                return data.get("prices", {})
        except Exception:
            continue
    return {}


# ── SOFR fetch ───────────────────────────────────────────────────────────────
def fetch_sofr(quiet=False):
    """Fetch SOFR via the dex-credit sofr_rate_calculator."""
    sys.path.insert(0, CREDIT_FUND_DIR)
    try:
        from sofr_rate_calculator import fetch_sofr as _fetch
        return _fetch(quiet=quiet)
    except Exception as e:
        print(f"[!] Failed to fetch SOFR: {e}", file=sys.stderr)
        return None
    finally:
        if CREDIT_FUND_DIR in sys.path:
            sys.path.remove(CREDIT_FUND_DIR)


# ── Credit offer state ───────────────────────────────────────────────────────
def load_credit_fund_config():
    """Load the dex-credit config.json for offer and daemon info."""
    config_path = os.path.join(CREDIT_FUND_DIR, "config.json")
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[!] Failed to load dex-credit config: {e}", file=sys.stderr)
        return {}


def get_credit_offer_states(rpc, config):
    """Fetch current balance for all monitored credit offers."""
    daemon_cfg = config.get("daemon", {})
    strategy_map = daemon_cfg.get("strategy_map", {})

    offer_ids = set()
    offer_to_account = {}
    for account_name, strat in strategy_map.items():
        for oid in strat.get("monitored_offers", []):
            offer_ids.add(oid)
            offer_to_account[oid] = account_name

    if not offer_ids:
        return {}

    try:
        objects = rpc.db("get_objects", [list(offer_ids)])
    except Exception as e:
        print(f"[!] Failed to fetch credit offers: {e}", file=sys.stderr)
        return {}

    result = {}
    for obj in objects:
        if not obj:
            continue
        oid = obj["id"]
        balance = int(obj.get("current_balance", 0))
        min_deal = int(obj.get("min_deal_amount", 0))
        fee_rate = int(obj.get("fee_rate", 0))
        result[oid] = {
            "balance": balance,
            "min_deal_amount": min_deal,
            "fee_rate": fee_rate,
            "account": offer_to_account.get(oid, "unknown"),
        }
    return result


# ── State management ────────────────────────────────────────────────────────
def load_previous_state():
    """Load the previous run's state snapshot."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def save_state(state):
    """Save the current state snapshot for next run's delta comparison."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[!] Failed to save state: {e}", file=sys.stderr)


def load_rules():
    """Load strategy rules from persistent location, falling back to default."""
    # If persistent rules file doesn't exist yet, copy default to persistent location
    if not os.path.exists(PERSISTENT_RULES_FILE):
        try:
            if os.path.exists(DEFAULT_RULES_FILE):
                os.makedirs(os.path.dirname(PERSISTENT_RULES_FILE), exist_ok=True)
                import shutil
                shutil.copy2(DEFAULT_RULES_FILE, PERSISTENT_RULES_FILE)
                print(f"[*] Initialized persistent rules file at {PERSISTENT_RULES_FILE}", file=sys.stderr)
        except Exception as e:
            print(f"[!] Failed to copy default rules to persistent storage: {e}", file=sys.stderr)

    target_file = PERSISTENT_RULES_FILE if os.path.exists(PERSISTENT_RULES_FILE) else DEFAULT_RULES_FILE
    try:
        with open(target_file, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[!] Failed to load rules from {target_file}: {e}", file=sys.stderr)
        return {}


# ── Delta calculations ───────────────────────────────────────────────────────
def pct_change(old, new):
    """Calculate absolute percentage change between two values."""
    if old is None or old == 0:
        return None
    return abs((new - old) / old) * 100.0


# ── Cooldown check ───────────────────────────────────────────────────────────
def is_on_cooldown(action_type, previous_state, cooldowns):
    """Check if an action type is within its cooldown window."""
    last_actions = (previous_state or {}).get("last_actions", {})
    last_ts = last_actions.get(action_type)
    if not last_ts:
        return False

    min_key = f"{action_type}_min_interval_minutes"
    min_minutes = cooldowns.get(min_key, 0)
    if min_minutes <= 0:
        return False

    try:
        last_dt = datetime.fromisoformat(last_ts)
        # Handle both aware and naive datetimes
        now = datetime.now(timezone.utc)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        elapsed_minutes = (now - last_dt).total_seconds() / 60.0
        return elapsed_minutes < min_minutes
    except Exception:
        return False


# ── Rule evaluation ──────────────────────────────────────────────────────────
def evaluate_triggers(current_state, previous_state, rules):
    """Evaluate all trigger conditions and return list of triggered actions."""
    actions = []
    cooldowns = rules.get("cooldowns", {})
    prices = current_state.get("prices", {})
    prev_prices = (previous_state or {}).get("prices", {})

    # ── Credit Fund triggers ─────────────────────────────────────────────
    cf_rules = rules.get("credit_fund", {})
    if cf_rules.get("enabled", True):
        cf_cooldown = is_on_cooldown("credit_fund", previous_state, cooldowns)

        # Trigger: offer balance < min_deal_amount
        if cf_rules.get("trigger_offer_below_min_deal", True):
            for oid, info in current_state.get("credit_offers", {}).items():
                if info["balance"] < info["min_deal_amount"]:
                    actions.append({
                        "action": "credit_fund",
                        "trigger": "offer_depleted",
                        "detail": (
                            f"Offer {oid} balance ({info['balance']}) "
                            f"< min_deal_amount ({info['min_deal_amount']})"
                        ),
                        "account": info["account"],
                        "offer_id": oid,
                        "on_cooldown": cf_cooldown,
                    })

        # Trigger: SOFR drift > threshold
        sofr_threshold = cf_rules.get("trigger_sofr_drift_pct", 0.1)
        prev_sofr = (previous_state or {}).get("sofr_pct")
        curr_sofr = current_state.get("sofr_pct")
        if prev_sofr is not None and curr_sofr is not None:
            sofr_delta = abs(curr_sofr - prev_sofr)
            if sofr_delta >= sofr_threshold:
                actions.append({
                    "action": "credit_fund",
                    "trigger": "sofr_drift",
                    "detail": (
                        f"SOFR changed {sofr_delta:.4f}% "
                        f"({prev_sofr:.4f}% → {curr_sofr:.4f}%), "
                        f"exceeds {sofr_threshold}% threshold"
                    ),
                    "accounts": cf_rules.get("accounts", []),
                    "on_cooldown": cf_cooldown,
                })

        # Trigger: BTC price movement > threshold
        btc_threshold = cf_rules.get("trigger_btc_price_movement_pct", 5.0)
        btc_delta = pct_change(prev_prices.get("BTC"), prices.get("BTC"))
        if btc_delta is not None and btc_delta >= btc_threshold:
            actions.append({
                "action": "credit_fund",
                "trigger": "btc_price_movement",
                "detail": (
                    f"BTC moved {btc_delta:.2f}% "
                    f"({prev_prices.get('BTC'):.2f} → {prices.get('BTC'):.2f}), "
                    f"exceeds {btc_threshold}% threshold"
                ),
                "accounts": cf_rules.get("accounts", []),
                "on_cooldown": cf_cooldown,
            })

        # Trigger: BTS price movement > threshold
        bts_threshold = cf_rules.get("trigger_bts_price_movement_pct", 5.0)
        bts_delta = pct_change(prev_prices.get("BTS"), prices.get("BTS"))
        if bts_delta is not None and bts_delta >= bts_threshold:
            actions.append({
                "action": "credit_fund",
                "trigger": "bts_price_movement",
                "detail": (
                    f"BTS moved {bts_delta:.2f}% "
                    f"({prev_prices.get('BTS'):.8f} → {prices.get('BTS'):.8f}), "
                    f"exceeds {bts_threshold}% threshold"
                ),
                "accounts": cf_rules.get("accounts", []),
                "on_cooldown": cf_cooldown,
            })

    # ── Cascade triggers ─────────────────────────────────────────────────
    casc_rules = rules.get("cascade", {})
    if casc_rules.get("enabled", False):
        casc_cooldown = is_on_cooldown("cascade", previous_state, cooldowns)
        target_price = casc_rules.get("target_price_bts_usd", 0)
        bts_price = prices.get("BTS")
        if bts_price is not None and target_price > 0 and bts_price <= target_price:
            actions.append({
                "action": "cascade",
                "trigger": "price_threshold",
                "detail": (
                    f"BTS price ({bts_price:.8f}) ≤ target "
                    f"({target_price:.8f})"
                ),
                "account": casc_rules.get("account", "johnr"),
                "target_pool": casc_rules.get("target_pool", "1.19.48"),
                "on_cooldown": casc_cooldown,
            })

    # ── Straddle triggers (Option C: time-based with delta gate) ─────────
    strad_rules = rules.get("straddle", {})
    if strad_rules.get("enabled", True):
        strad_cooldown = is_on_cooldown("straddle", previous_state, cooldowns)
        markets_map = strad_rules.get("markets", {})

        # Option C: Require BOTH minimum time elapsed AND minimum price
        # movement from the price at which the straddle was last executed.
        refresh_hours = strad_rules.get("refresh_interval_hours", 6)
        min_delta_pct = strad_rules.get("min_delta_from_execution_pct", 2.0)

        # Load anchor prices from when straddle was last executed
        last_straddle_prices = (previous_state or {}).get("last_straddle_prices", {})

        # Check if enough time has passed since last straddle execution
        last_straddle_ts = (previous_state or {}).get("last_actions", {}).get("straddle")
        time_gate_open = True
        if last_straddle_ts:
            try:
                last_dt = datetime.fromisoformat(last_straddle_ts)
                now_dt = datetime.now(timezone.utc)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                hours_elapsed = (now_dt - last_dt).total_seconds() / 3600.0
                time_gate_open = hours_elapsed >= refresh_hours
            except Exception:
                time_gate_open = True

        if time_gate_open:
            # Check each tracked asset against its execution anchor price
            asset_price_keys = {
                "BTC": "BTC",
                "XRP": "XRP",
                "XAUT": "Gold",
            }

            for asset_key, price_key in asset_price_keys.items():
                current_price = prices.get(price_key)
                anchor_price = last_straddle_prices.get(price_key)

                if current_price is None:
                    continue

                # First run or no anchor: always trigger to establish positions
                if anchor_price is None or anchor_price == 0:
                    delta = None
                    detail = (
                        f"{asset_key}: No previous execution anchor — "
                        f"initial straddle placement at {current_price}"
                    )
                else:
                    delta = pct_change(anchor_price, current_price)
                    if delta is None or delta < min_delta_pct:
                        continue
                    detail = (
                        f"{asset_key} moved {delta:.2f}% from last execution "
                        f"({anchor_price:.8f} → {current_price:.8f}), "
                        f"exceeds {min_delta_pct}% gate"
                    )

                actions.append({
                    "action": "straddle_refresh",
                    "trigger": f"{asset_key.lower()}_execution_drift",
                    "detail": detail,
                    "markets": markets_map.get(asset_key, []),
                    "account": strad_rules.get("account", "johnr"),
                    "spread_pct": strad_rules.get("default_spread_pct", 2.0),
                    "on_cooldown": strad_cooldown,
                })

    return actions



# ── Main ─────────────────────────────────────────────────────────────────────
def run_monitor(json_mode=False, quiet=False):
    """Execute one monitoring cycle."""
    now = datetime.now(timezone.utc).isoformat()

    # Load rules
    rules = load_rules()
    if not rules:
        print("No strategy_rules.json found. Exiting.", file=sys.stderr)
        return None

    # Connect to BitShares
    rpc = get_shared_rpc()
    try:
        # Step 1: Refresh shared price index
        refresh_price_index(rpc, quiet=quiet)

        # Step 2: Load current prices from refreshed index
        prices = load_price_index()

        # Step 3: Fetch SOFR
        sofr_pct = fetch_sofr(quiet=quiet)

        # Step 4: Fetch credit offer states
        cf_config = load_credit_fund_config()
        credit_offers = get_credit_offer_states(rpc, cf_config)

    finally:
        rpc.close()

    # Step 5: Load previous state for delta comparison
    previous_state = load_previous_state()

    # Step 6: Build current state
    current_state = {
        "timestamp": now,
        "prices": prices,
        "sofr_pct": sofr_pct,
        "credit_offers": credit_offers,
    }

    # Step 7: Evaluate triggers
    actions = evaluate_triggers(current_state, previous_state, rules)

    # Step 8: Save state snapshot for next run
    save_data = {
        "timestamp": now,
        "prices": prices,
        "sofr_pct": sofr_pct,
        "last_actions": (previous_state or {}).get("last_actions", {}),
        "last_straddle_prices": (previous_state or {}).get("last_straddle_prices", {}),
    }
    # Update last_action timestamps for any triggered (non-cooldown) actions
    straddle_triggered = False
    for a in actions:
        if not a.get("on_cooldown", False):
            action_type = a["action"]
            # Map straddle_refresh → straddle for cooldown tracking
            if action_type == "straddle_refresh":
                action_type = "straddle"
                straddle_triggered = True
            save_data["last_actions"][action_type] = now

    # When straddle triggers fire, snapshot current prices as the new anchor
    if straddle_triggered:
        save_data["last_straddle_prices"] = {
            k: v for k, v in prices.items()
            if k in ("BTC", "XRP", "Gold")
        }
    save_state(save_data)

    # Step 9: Build report
    # Compute deltas for display
    deltas = {}
    prev_prices = (previous_state or {}).get("prices", {})
    for key in ["BTC", "BTS", "XRP", "Gold"]:
        delta = pct_change(prev_prices.get(key), prices.get(key))
        if delta is not None:
            deltas[f"{key}_pct"] = round(delta, 4)
    prev_sofr = (previous_state or {}).get("sofr_pct")
    if prev_sofr is not None and sofr_pct is not None:
        deltas["SOFR_abs"] = round(abs(sofr_pct - prev_sofr), 4)

    is_first_run = previous_state is None

    report = {
        "timestamp": now,
        "first_run": is_first_run,
        "current_state": {
            "prices": prices,
            "sofr_pct": sofr_pct,
            "credit_offers": credit_offers,
        },
        "deltas": deltas,
        "actions_triggered": [a for a in actions if not a.get("on_cooldown", False)],
        "actions_on_cooldown": [a for a in actions if a.get("on_cooldown", False)],
    }

    # Step 10: Output
    if json_mode:
        # Clean up on_cooldown flags from output for clarity
        for a in report["actions_triggered"]:
            a.pop("on_cooldown", None)
        for a in report["actions_on_cooldown"]:
            a.pop("on_cooldown", None)
        print(json.dumps(report, indent=2))
    else:
        _print_human_readable(report, is_first_run)

    return report


def _print_human_readable(report, is_first_run):
    """Print a human-friendly summary."""
    prices = report["current_state"]["prices"]
    sofr = report["current_state"]["sofr_pct"]
    offers = report["current_state"]["credit_offers"]
    deltas = report["deltas"]
    actions = report["actions_triggered"]
    cooldown_actions = report["actions_on_cooldown"]

    print(f"\n{'='*60}")
    print(f"  STRATEGY MONITOR — {report['timestamp'][:19]}")
    print(f"{'='*60}")

    if is_first_run:
        print(f"\n  ⚑ First run — establishing baseline snapshot")
        print(f"    No delta comparison available until next cycle.\n")

    # Prices
    print(f"\n  Prices:")
    for key in ["BTC", "BTS", "XRP", "Gold"]:
        price = prices.get(key, "N/A")
        delta = deltas.get(f"{key}_pct")
        delta_str = f"  ({delta:+.2f}%)" if delta is not None else ""
        if key == "BTS":
            print(f"    {key:>6}: ${price:.8f}{delta_str}")
        elif key == "Gold":
            print(f"    {'XAUT':>6}: ${price:.2f}{delta_str}")
        else:
            print(f"    {key:>6}: ${price:,.2f}{delta_str}")

    # SOFR
    sofr_delta = deltas.get("SOFR_abs")
    sofr_str = f"  (Δ {sofr_delta:.4f}%)" if sofr_delta is not None else ""
    print(f"\n  SOFR: {sofr:.4f}%{sofr_str}" if sofr else "\n  SOFR: unavailable")

    # Credit offers
    if offers:
        print(f"\n  Credit Offers:")
        for oid, info in offers.items():
            status = "⚠ DEPLETED" if info["balance"] < info["min_deal_amount"] else "OK"
            print(f"    {oid}: balance={info['balance']:>12,} [{status}] ({info['account']})")

    # Actions
    if actions:
        print(f"\n  ▶ Actions Triggered ({len(actions)}):")
        for a in actions:
            print(f"    • [{a['action']}] {a['trigger']}: {a['detail']}")
    elif not is_first_run:
        print(f"\n  ✓ No actions triggered.")

    if cooldown_actions:
        print(f"\n  ⏳ On Cooldown ({len(cooldown_actions)}):")
        for a in cooldown_actions:
            print(f"    • [{a['action']}] {a['trigger']}: {a['detail']}")

    print(f"\n{'='*60}\n")


# ── CLI ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="BOB Autonomous Strategy Monitor"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON output"
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress diagnostic output on stderr"
    )
    args = parser.parse_args()

    report = run_monitor(json_mode=args.json, quiet=args.quiet or args.json)
    if report and report.get("actions_triggered"):
        sys.exit(0)  # Actions to take
    elif report and report.get("first_run"):
        sys.exit(0)  # First run — baseline established
    else:
        sys.exit(0)  # No actions — still success


if __name__ == "__main__":
    main()
