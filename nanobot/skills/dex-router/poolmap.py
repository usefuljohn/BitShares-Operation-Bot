import argparse
import heapq
import itertools
import json
import math
import ssl
from collections import defaultdict

import networkx as nx
import numpy as np
import requests

from min_to_receive import wrapper
from rpc import rpc_get_objects, wss_handshake


def constant_product_output(dx, x_reserve, y_reserve):
    """Uniswap-style formula"""
    return (y_reserve / x_reserve) * dx


def build_graph(pools):
    """
    Builds a MultiGraph where each edge represents a liquidity pool between two assets.
    """
    G = nx.MultiGraph()
    for pool_id, (bal_a, bal_b, asset_a, asset_b, fee, _) in pools.items():
        if bal_a and bal_b:
            G.add_edge(
                asset_a,
                asset_b,
                pool=pool_id,
                bal_a=bal_a,
                bal_b=bal_b,
                asset_a=asset_a,
                asset_b=asset_b,
                fee=fee,
            )
    return G


def get_slippage(rpc, amount, fee, balance_a, balance_b, a_id, b_id, from_asset, cer_prices):
    if from_asset == a_id:
        balance_a, balance_b = balance_b, balance_a
        a_id, b_id = b_id, a_id

    cer = cer_prices[b_id] if cer_prices else None

    a_id, b_id = f"1.3.{a_id}", f"1.3.{b_id}"

    instant_price = balance_a / balance_b

    actual_out = wrapper(rpc, amount, fee, balance_a, balance_b, a_id, b_id, a_id)
    actual_price = (balance_a + amount) / (balance_b - actual_out)

    effective_out = max(0, actual_out - ((1 / cer) if cer_prices else 0))
    effective_price = (balance_a + amount) / (balance_b - effective_out)

    slippage = instant_price / effective_price

    return slippage, actual_price


def bootstrap_prices_from_core(rpc, input_amount, G, base_token, cer_prices=None):
    """
    Bootstraps token prices by propagating outward from a base token.
    """
    prices = {base_token: 1.0}
    token_paths = {base_token: [base_token]}
    pool_paths = {base_token: []}
    minimum_slippage = defaultdict(lambda: float("-inf"))
    visited = set()
    heap = []

    # we came from nowhere with 0 slippage and started at base_token.
    heapq.heappush(heap, (0, base_token, 1, [base_token], []))

    while heap:
        (
            base_slippage,
            known,
            price_to_here,
            token_path,
            pool_path,
        ) = heapq.heappop(heap)

        for _, _, data in G.edges(data=True):
            if (
                (known not in (data["asset_a"], data["asset_b"]))
                or (not data["bal_a"])
                or (not data["bal_b"])
                or (data["pool"] in visited)
            ):
                continue

            visited.add(data["pool"])

            a_is_known = data["asset_a"] == known

            unknown = data["asset_b"] if a_is_known else data["asset_a"]

            slippage, price = get_slippage(
                rpc,
                amount=price_to_here * input_amount,
                fee=data["fee"],
                balance_a=data["bal_a"],
                balance_b=data["bal_b"],
                a_id=data["asset_a"],
                b_id=data["asset_b"],
                from_asset=known,
                cer_prices=cer_prices,
            )

            core_slippage = (1 - base_slippage) * slippage
            core_price = price_to_here * price

            if minimum_slippage[unknown] < core_slippage:
                minimum_slippage[unknown] = core_slippage

                prices[unknown] = core_price
                token_paths[unknown] = token_path + [unknown]
                pool_paths[unknown] = pool_path + [data["pool"]]

                heapq.heappush(
                    heap,
                    (
                        # the heap selects the smallest item, so we want the largest remaining amount
                        1 - core_slippage,
                        unknown,
                        core_price,
                        token_paths[unknown],
                        pool_paths[unknown],
                    ),
                )

    return prices, token_paths, pool_paths


def load_pool_data():
    data = requests.get(
        "https://raw.githubusercontent.com/squidKid-deluxe/bitshares-networks/refs/heads/gh-pages/pools/pipe/pool_cache.txt"
    ).text
    data = data.split("<<< JSON IPC >>>")[1]
    data = json.loads(data)
    data = [
        (pool_id, info["share_asset"], info["asset_a"], info["asset_b"])
        for pool_id, info in data.items()
    ]
    return data


def load_precisions():
    data = requests.get(
        "https://raw.githubusercontent.com/squidKid-deluxe/bitshares-networks/refs/heads/gh-pages/pools/pipe/name_cache.txt"
    ).text
    data = data.split("<<< JSON IPC >>>")[1]
    data = json.loads(data)
    return data


def rpc_chunk_objects(rpc, ids, limit=100):
    chunks = [ids[i : i + limit] for i in range(0, len(ids), limit)]
    results = {}
    print(f"Requesting {len(chunks)} chunks...")
    for chunk_num, chunk in enumerate(chunks, start=1):
        print(f"chunk {chunk_num}")
        try:
            objects = rpc_get_objects(rpc, chunk)
            results.update(objects)
        except Exception as e:
            print(f"An error occurred processing chunk {chunk_num}: {e}")
    return results


def parse_pool_data(data, cache):
    results = {}
    for info in data.values():
        results[info["id"]] = (
            int(info["balance_a"]) / 10 ** cache[info["asset_a"]]["precision"],
            int(info["balance_b"]) / 10 ** cache[info["asset_b"]]["precision"],
            int(info["taker_fee_percent"]) / 100,
            int(info["withdrawal_fee_percent"]) / 100,
            info["asset_a"],
            info["asset_b"],
        )
    return results


def format_thousands(number):
    return f"{number:,}"


def sigfig(number, precision=6):
    if number == 0:
        return "0"
    return format_thousands(round(number, precision - int(math.floor(math.log10(abs(number))))))


def generate_all_prices(rpc, input_amount, pools, cache, core, mock=False):
    if mock:
        pool_data = parse_pool_data(mock_rpc_chunk_objects(pools), cache)
    else:
        pool_data = parse_pool_data(rpc_chunk_objects(rpc, pools), cache)

    all_assets = set()
    for pool in pool_data.values():
        all_assets.add(pool[4])
        all_assets.add(pool[5])

    rpc_chunk_objects(rpc, list(all_assets))

    balance_data = {
        pool_id: (
            balance_info[0],
            balance_info[1],
            int(balance_info[4].rsplit(".", 1)[1]),
            int(balance_info[5].rsplit(".", 1)[1]),
            balance_info[2],
            balance_info[3],
        )
        for pool_id, balance_info in pool_data.items()
    }
    graph = build_graph(balance_data)

    # First pass: Feeless to get CER prices
    cer_prices, token_paths, pool_paths = bootstrap_prices_from_core(rpc, 1, graph, base_token=0)

    return (
        bootstrap_prices_from_core(rpc, input_amount, graph, core, cer_prices=cer_prices),
        balance_data,
        graph,
    )


def load_mock_pool_data():
    return [
        ("1.19.1", "LP_SHARE_1", "1.3.0", "1.3.1"),
        ("1.19.2", "LP_SHARE_2", "1.3.1", "1.3.2"),
        ("1.19.3", "LP_SHARE_3", "1.3.2", "1.3.3"),
        ("1.19.4", "LP_SHARE_4", "1.3.121", "1.3.0"),  # XBTSX.USDT-BTS
        ("1.19.5", "LP_SHARE_5", "1.3.0", "1.3.861"),  # BTS-HONEST.MONEY
    ]


def load_mock_precisions():
    return {
        "1.3.0": {
            "symbol": "BTS",
            "precision": 5,
            "options": {"market_fee_percent": 0, "max_market_fee": 0, "flags": 0},
        },
        "1.3.1": {
            "symbol": "USD",
            "precision": 4,
            "options": {"market_fee_percent": 0, "max_market_fee": 0, "flags": 0},
        },
        "1.3.2": {
            "symbol": "EUR",
            "precision": 4,
            "options": {"market_fee_percent": 0, "max_market_fee": 0, "flags": 0},
        },
        "1.3.3": {
            "symbol": "GOLD",
            "precision": 6,
            "options": {"market_fee_percent": 0, "max_market_fee": 0, "flags": 0},
        },
        "1.3.121": {
            "symbol": "XBTSX.USDT",
            "precision": 6,
            "options": {"market_fee_percent": 0, "max_market_fee": 0, "flags": 0},
        },
        "1.3.861": {
            "symbol": "HONEST.MONEY",
            "precision": 6,
            "options": {"market_fee_percent": 0, "max_market_fee": 0, "flags": 0},
        },
    }


def mock_rpc_chunk_objects(ids):
    return {
        "1.19.1": {
            "id": "1.19.1",
            "balance_a": "100000000",
            "balance_b": "10000000",
            "asset_a": "1.3.0",
            "asset_b": "1.3.1",
            "taker_fee_percent": "10",
            "withdrawal_fee_percent": "0",
        },
        "1.19.2": {
            "id": "1.19.2",
            "balance_a": "50000000",
            "balance_b": "4500000",
            "asset_a": "1.3.1",
            "asset_b": "1.3.2",
            "taker_fee_percent": "10",
            "withdrawal_fee_percent": "0",
        },
        "1.19.3": {
            "id": "1.19.3",
            "balance_a": "20000000",
            "balance_b": "100000",
            "asset_a": "1.3.2",
            "asset_b": "1.3.3",
            "taker_fee_percent": "10",
            "withdrawal_fee_percent": "0",
        },
        "1.19.4": {  # XBTSX.USDT-BTS
            "id": "1.19.4",
            "balance_a": "1000000000",
            "balance_b": "100000000",
            "asset_a": "1.3.121",
            "asset_b": "1.3.0",
            "taker_fee_percent": "10",
            "withdrawal_fee_percent": "0",
        },
        "1.19.5": {  # BTS-HONEST.MONEY
            "id": "1.19.5",
            "balance_a": "500000000",
            "balance_b": "50000000",
            "asset_a": "1.3.0",
            "asset_b": "1.3.861",
            "taker_fee_percent": "10",
            "withdrawal_fee_percent": "0",
        },
    }


def main(
    from_token="XBTSX.USDT",
    to_token="HONEST.MONEY",
    input_amount=1,
    mock=False,
    result_holder=None,
    plot=False,
    pool_filter=None,
):
    """
    parser = argparse.ArgumentParser(
        description="Find best trading paths in BitShares DEX."
    )
    parser.add_argument(
        "--from", dest="from_token", default="XBTSX.USDT", help="The token to trade from."
    )
    parser.add_argument(
        "--to", dest="to_token", default="HONEST.MONEY", help="The token to trade to."
    )
    parser.add_argument(
        "--mock", action="store_true", help="Use mock data instead of live data."
    )

    TODO: Add argparser back in
    """

    if mock:
        data = load_mock_pool_data()
        cache = load_mock_precisions()
        rpc = None
        # Pre-populate rpc_get_objects cache for wrapper to work in mock mode
        rpc_get_objects.cache = cache
    else:
        data = load_pool_data()
        cache = load_precisions()
        rpc = wss_handshake()

    if not any(v["symbol"] == from_token for v in cache.values()):
        print(f"Invalid 'from' token: {from_token}")
        return

    if not any(v["symbol"] == to_token for v in cache.values()):
        print(f"Invalid 'to' token: {to_token}")
        return

    FROM_ID = [int(k.split(".")[2]) for k, v in cache.items() if v["symbol"] == from_token][0]
    TO_ID = [int(k.split(".")[2]) for k, v in cache.items() if v["symbol"] == to_token][0]

    whitelisted_assets = ["TWENTIX", "BTS", "BTWTY", "XBTSX.USDT", "BTWTY.EOS", "HONEST.MONEY", "IOB.XRP", "IOB.XLM"]
    whitelisted_asset_ids = {k for k, v in cache.items() if v["symbol"] in whitelisted_assets}

    filtered_data = []
    for d in data:
        if d[2] in whitelisted_asset_ids or d[3] in whitelisted_asset_ids:
            filtered_data.append(d)
    data = filtered_data
    pools = [d[0] for d in data]

    if pool_filter:
        if isinstance(pool_filter, list):
            pools = [p for p in pools if p in pool_filter]
            data = [d for d in data if d[0] in pool_filter]
        elif isinstance(pool_filter, str):
            asset_id_to_filter = None
            for k, v in cache.items():
                if v["symbol"] == pool_filter:
                    asset_id_to_filter = k
                    break
            
            if asset_id_to_filter:
                original_data = data
                filtered_data = []
                for d in data:
                    if d[2] == asset_id_to_filter or d[3] == asset_id_to_filter:
                        filtered_data.append(d)
                data = filtered_data
                pools = [d[0] for d in data]
            else:
                print(f"Asset {pool_filter} not found.")
                return

    core = FROM_ID

    (prices, token_paths, pool_paths), balance_data, graph = generate_all_prices(
        rpc, input_amount, pools, cache, core, mock=mock
    )

    print("\nPATHS\n")
    print("Symbol           Price        Path")
    if not TO_ID in token_paths:
        print(f"No path found from {from_token} to {to_token}")
        return

    token_path = token_paths[TO_ID]
    pool_path = pool_paths[TO_ID]
    path_str = " -> ".join([cache[f"1.3.{i}"]["symbol"] for i in token_path])
    print(
        cache[f"1.3.{TO_ID}"]["symbol"].ljust(16),
        str(sigfig(prices[TO_ID])).ljust(16),
        path_str,
    )

    if result_holder is not None:
        # values = []
        # pool_prices = []
        balances = []
        fees = []
        for token, pool_id in zip(token_path, pool_path):
            pool = balance_data[pool_id]
            # asset_a = pool[2]
            # asset_b = pool[3]
            # if asset_a in prices and asset_b in prices:
            #     values.append(pool[0] * prices[asset_a] + pool[1] * prices[asset_b])
            # pool_prices.append((pool[0] / pool[1]) if asset_a == token else (pool[1] / pool[0]))
            balances.append(pool)  # if asset_a == token else (pool[1], pool[0]))
            fees.append(pool[4])

        result_holder["result"] = [prices[TO_ID], token_path, pool_path, balances, fees]
        result_holder["rpc"] = rpc
        result_holder["cache"] = cache

    if not plot:
        return

    from pyvis.network import Network

    # Create a pyvis network
    net = Network(
        notebook=False, height="750px", width="100%", bgcolor="#222222", font_color="white"
    )
    net.from_nx(graph)

    # Set labels and colors
    for node in net.nodes:
        node_id = node["id"]
        node["label"] = cache.get(f"1.3.{node_id}", {}).get("symbol", str(node_id))
        if node_id in token_path:
            node["color"] = "skyblue"

    path_edges = list(zip(token_path, token_path[1:]))
    for edge in net.edges:
        is_path = (edge["from"], edge["to"]) in path_edges or (
            edge["to"],
            edge["from"],
        ) in path_edges
        if is_path:
            edge["color"] = "lime"
            edge["width"] = 2.0
        else:
            edge["color"] = "gray"
            edge["width"] = 1.0

    net.set_options(
        """
    var options = {
      "nodes": {
        "font": {
          "size": 12
        }
      },
      "edges": {
        "color": {
          "inherit": true
        },
        "smooth": {
          "type": "continuous"
        }
      },
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -50,
          "centralGravity": 0.01,
          "springLength": 230,
          "springConstant": 0.08,
          "damping": 0.4,
          "avoidOverlap": 0
        },
        "minVelocity": 0.75,
        "solver": "forceAtlas2Based"
      }
    }
    """
    )

    net.show(f"liquidity_pool_map.html", notebook=False)



if __name__ == "__main__":
    main()
