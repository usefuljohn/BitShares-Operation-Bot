"""
This is a python port of the min_to_receive logic in Bitshares-UI.

Credits go to Bitshares-UI devs and Grok.com for making this possible.
"""

import math
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, getcontext

from rpc import rpc_get_objects

getcontext().prec = 28


def calculate_min_to_receive(amount_to_sell_str, pool, sell_tag, receive_tag):
    amount_to_sell = Decimal(amount_to_sell_str)

    asset_a = pool[f"asset_{sell_tag}"]
    asset_b = pool[f"asset_{receive_tag}"]

    pool_amount_a = Decimal(pool[f"balance_{sell_tag}"])
    precision_a = int(asset_a["precision"])
    pool_amount_ap = Decimal(10) ** precision_a

    pool_amount_b = Decimal(pool[f"balance_{receive_tag}"])
    precision_b = int(asset_b["precision"])
    pool_amount_bp = Decimal(10) ** precision_b

    maker_market_fee_percent_a = Decimal(asset_a["options"]["market_fee_percent"])
    maker_market_fee_percent_b = Decimal(asset_b["options"]["market_fee_percent"])

    asset_a_flags = int(asset_a["options"]["flags"])
    asset_b_flags = int(asset_b["options"]["flags"])

    max_market_fee_a = Decimal(asset_a["options"]["max_market_fee"])
    max_market_fee_b = Decimal(asset_b["options"]["max_market_fee"])

    def flags_a():
        if asset_a_flags % 2 == 0:
            return Decimal(0)
        if maker_market_fee_percent_a == 0:
            return Decimal(0)
        if maker_market_fee_percent_a > 0:
            calculated = (
                amount_to_sell * pool_amount_ap * (maker_market_fee_percent_a / Decimal(10000))
            )
            ceiled = calculated.quantize(Decimal("1"), rounding=ROUND_CEILING)
            return min(max_market_fee_a, ceiled)

    def flags_b():
        if asset_b_flags % 2 == 0:
            return Decimal(0)
        if maker_market_fee_percent_b == 0:
            return Decimal(0)
        if maker_market_fee_percent_b > 0:
            calculated = (
                amount_to_sell * pool_amount_bp * (maker_market_fee_percent_b / Decimal(10000))
            )
            ceiled = calculated.quantize(Decimal("1"), rounding=ROUND_CEILING)
            return min(max_market_fee_b, ceiled)

    def taker_market_fee_percent_a_func():
        if asset_a_flags % 2 == 0:
            return Decimal(0)
        extensions = asset_a["options"].get("extensions", {})
        taker_fee_percent_a = extensions.get("taker_fee_percent")
        if taker_fee_percent_a is None and maker_market_fee_percent_a > 0:
            return maker_market_fee_percent_a / Decimal(10000)
        if taker_fee_percent_a is None and maker_market_fee_percent_a == 0:
            return Decimal(0)
        else:
            return Decimal(taker_fee_percent_a) / Decimal(10000)

    def taker_market_fee_percent_b_func():
        if asset_b_flags % 2 == 0:
            return Decimal(0)
        extensions = asset_b["options"].get("extensions", {})
        taker_fee_percent_b = extensions.get("taker_fee_percent")
        if taker_fee_percent_b is None and maker_market_fee_percent_b > 0:
            return maker_market_fee_percent_b / Decimal(10000)
        if taker_fee_percent_b is None and maker_market_fee_percent_b == 0:
            return Decimal(0)
        else:
            return Decimal(taker_fee_percent_b) / Decimal(10000)

    flags_a_val = flags_a()
    flags_b_val = flags_b()

    tmp_delta_a = pool_amount_a - (
        (pool_amount_a * pool_amount_b)
        / (pool_amount_b + (amount_to_sell * pool_amount_bp - flags_b_val))
    ).quantize(Decimal("1"), rounding=ROUND_CEILING)
    tmp_delta_b = pool_amount_b - (
        (pool_amount_b * pool_amount_a)
        / (pool_amount_a + (amount_to_sell * pool_amount_ap - flags_a_val))
    ).quantize(Decimal("1"), rounding=ROUND_CEILING)

    pool_taker_fee_percent = Decimal(pool["taker_fee_percent"])

    tmp_a = (tmp_delta_a * pool_taker_fee_percent) / Decimal(10000)
    tmp_b = (tmp_delta_b * pool_taker_fee_percent) / Decimal(10000)

    taker_market_fee_percent_a_val = taker_market_fee_percent_a_func()
    taker_market_fee_percent_b_val = taker_market_fee_percent_b_func()

    asset_taker_fee_inner_ceil = (tmp_delta_b * taker_market_fee_percent_b_val).quantize(
        Decimal("1"), rounding=ROUND_CEILING
    )
    asset_taker_fee_outer_ceil = asset_taker_fee_inner_ceil.quantize(
        Decimal("1"), rounding=ROUND_CEILING
    )  # Matches the nested ceil
    min_fee = min(max_market_fee_b, asset_taker_fee_outer_ceil)
    asset_fee_ceil = min_fee.quantize(Decimal("1"), rounding=ROUND_CEILING)

    pool_fee_floor = tmp_b.quantize(Decimal("1"), rounding=ROUND_FLOOR)

    min_receive_sat = tmp_delta_b - pool_fee_floor - asset_fee_ceil
    min_to_receive = min_receive_sat / pool_amount_bp

    return min_to_receive


# Usage example:
# result = min_to_receive(100, pool, 'A', 'B')  # Selling A for B
# result = min_to_receive(100, pool, 'B', 'A')  # Selling B for A

# --- Example usage ---
# pool = {
#     'balance_A': 1000000,
#     'balance_B': 2000000,
#     'asset_A': {
#         'precision': 5,
#         'options': {
#             'market_fee_percent': 20,
#             'max_market_fee': 1000,
#             'flags': 2,
#             'extensions': {
#                 'taker_fee_percent': 10
#             }
#         }
#     },
#     'asset_B': {
#         'precision': 5,
#         'options': {
#             'market_fee_percent': 30,
#             'max_market_fee': 1100,
#             'flags': 3,
#             'extensions': {
#                 'taker_fee_percent': 15
#             }
#         }
#     },
#     'taker_fee_percent': 25
# }
# result = min_to_receive(100, pool, 'A', 'B')
# print(result)


def wrapper(rpc, amount_a, fee, balance_a, balance_b, a_id, b_id, direction):
    """
    FIXME ideally this conversion layer isn't needed,
    we're re-precisioning to de-precision, not ideal.
    """
    objects = rpc_get_objects(rpc, [a_id, b_id])
    pool = {
        f"balance_{a_id}": int(balance_a * (10 ** objects[a_id]["precision"])),
        f"balance_{b_id}": int(balance_b * (10 ** objects[b_id]["precision"])),
        f"asset_{a_id}": objects[a_id],
        f"asset_{b_id}": objects[b_id],
        "taker_fee_percent": int(fee * 100),
    }
    # import json
    # print(json.dumps(pool, indent=2))
    return float(
        calculate_min_to_receive(amount_a, pool, direction, a_id if direction == b_id else b_id)
    )
