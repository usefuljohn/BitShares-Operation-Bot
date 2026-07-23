#!/usr/bin/env python3
"""
Autonomous Strategy Monitor
============================
Collects BitShares DEX state, evaluates trigger conditions against configurable
thresholds, and outputs recommended actions for the agent heartbeat loop.

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

STATE_FILE = os.path.join(SKILL_DIR, "strategy_state.json")
DEFAULT_RULES_FILE = os.path.join(SKILL_DIR, "strategy_rules.json")
PERSISTENT_RULES_FILE = os.path.expanduser("~/.bob/strategy_rules.json")

# ── Node list ────────────────────────────────────────────────────────────────
NODES = [
    "wss://dex.iobanker.com/ws",
    "wss://api.bts.mobi/ws",
    "wss://node.xbts.io/ws",
]


# ── RPC Client ───────────────────────────────────────────────────────────────
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
        now = datetime.now(timezone.utc)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        elapsed_minutes = (now - last_dt).total_seconds() / 60.0
        return elapsed_minutes < min_minutes
    except Exception:
        return False


# ── Rule evaluation ──────────────────────────────────────────────────────────
def evaluate_triggers(current_state, previous_state, rules):
    """Evaluate strategy rules against current and previous states."""
    actions = []
    cooldowns = rules.get("cooldowns", {})
    prices = current_state.get("prices", {})
    prev_prices = (previous_state or {}).get("prices", {})

    # Price Index Triggers
    pi_rules = rules.get("price_index", {})
    if pi_rules.get("enabled", True):
        pi_cooldown = is_on_cooldown("price_index", previous_state, cooldowns)

        btc_threshold = pi_rules.get("trigger_btc_price_movement_pct", 2.0)
        btc_delta = pct_change(prev_prices.get("BTC"), prices.get("BTC"))
        if btc_delta is not None and btc_delta >= btc_threshold:
            actions.append({
                "action": "price_index_update",
                "trigger": "btc_price_movement",
                "detail": (
                    f"BTC moved {btc_delta:.2f}% "
                    f"({prev_prices.get('BTC'):.2f} → {prices.get('BTC'):.2f}), "
                    f"exceeds {btc_threshold}% threshold"
                ),
                "on_cooldown": pi_cooldown,
            })

        bts_threshold = pi_rules.get("trigger_bts_price_movement_pct", 5.0)
        bts_delta = pct_change(prev_prices.get("BTS"), prices.get("BTS"))
        if bts_delta is not None and bts_delta >= bts_threshold:
            actions.append({
                "action": "price_index_update",
                "trigger": "bts_price_movement",
                "detail": (
                    f"BTS moved {bts_delta:.2f}% "
                    f"({prev_prices.get('BTS'):.8f} → {prices.get('BTS'):.8f}), "
                    f"exceeds {bts_threshold}% threshold"
                ),
                "on_cooldown": pi_cooldown,
            })

    return actions


# ── Main ─────────────────────────────────────────────────────────────────────
def run_monitor(json_mode=False, quiet=False):
    """Execute one monitoring cycle."""
    now = datetime.now(timezone.utc).isoformat()

    rules = load_rules()
    if not rules:
        print("No strategy_rules.json found. Exiting.", file=sys.stderr)
        return None

    rpc = get_shared_rpc()
    try:
        refresh_price_index(rpc, quiet=quiet)
        prices = load_price_index()
    finally:
        rpc.close()

    previous_state = load_previous_state()

    current_state = {
        "timestamp": now,
        "prices": prices,
    }

    actions = evaluate_triggers(current_state, previous_state, rules)

    save_data = {
        "timestamp": now,
        "prices": prices,
        "last_actions": (previous_state or {}).get("last_actions", {}),
    }

    for a in actions:
        if not a.get("on_cooldown", False):
            save_data["last_actions"][a["action"]] = now

    save_state(save_data)

    deltas = {}
    prev_prices = (previous_state or {}).get("prices", {})
    for key in ["BTC", "BTS", "XRP", "Gold"]:
        delta = pct_change(prev_prices.get(key), prices.get(key))
        if delta is not None:
            deltas[f"{key}_pct"] = round(delta, 4)

    is_first_run = previous_state is None

    report = {
        "timestamp": now,
        "first_run": is_first_run,
        "current_state": {
            "prices": prices,
        },
        "deltas": deltas,
        "actions_triggered": [a for a in actions if not a.get("on_cooldown", False)],
        "actions_on_cooldown": [a for a in actions if a.get("on_cooldown", False)],
    }

    if json_mode:
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
    deltas = report["deltas"]
    actions = report["actions_triggered"]
    cooldown_actions = report["actions_on_cooldown"]

    print(f"\n{'='*60}")
    print(f"  STRATEGY MONITOR — {report['timestamp'][:19]}")
    print(f"{'='*60}")

    if is_first_run:
        print(f"\n  ⚑ First run — establishing baseline snapshot")
        print(f"    No delta comparison available until next cycle.\n")

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
    sys.exit(0)


if __name__ == "__main__":
    main()
