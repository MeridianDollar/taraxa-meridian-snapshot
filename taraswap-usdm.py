#!/usr/bin/env python3

import sys
import json
import os
import requests
from decimal import Decimal
from collections import defaultdict

# ─── CONFIG ───────────────────────────────────────────────────────────────────

# GraphQL endpoint for the taraxa Uniswap V3 subgraph
GRAPHQL_URL = "https://indexer.lswap.app/subgraphs/name/taraxa/uniswap-v3"

# List of pools to scan
POOL_ADDRESSES = [
    "0x66c4c7a91f9c42259c52a415ebba9866bbb4179a"
    # You can add more pool addresses here
]

# Token within the LP we care about
TARGET_TOKEN = "0xC26B690773828999c2612549CC815d1F252EA15e".lower()

# Pagination page size
PAGE_SIZE = 1000

# ─── GRAPHQL QUERY ────────────────────────────────────────────────────────────

# This query is expanded to get all data needed for the calculation.
QUERY = """
query getPositions($pool: ID!, $block: Int!, $skip: Int!) {
  positions(
    first: %(page_size)d,
    skip: $skip,
    where: { pool: $pool, liquidity_gt: 0 },
    block: { number: $block }
  ) {
    id
    owner {
      id
    }
    liquidity
    tickLower { tickIdx }
    tickUpper { tickIdx }
    pool {
      tick
      token0 { id decimals }
      token1 { id decimals }
    }
  }
}
""" % {"page_size": PAGE_SIZE}

# ─── CORE LOGIC ───────────────────────────────────────────────────────────────

def tick_to_price(tick: int) -> Decimal:
    """Converts a tick index to a price, representing sqrt(P) as a Decimal."""
    return Decimal("1.0001") ** (Decimal(tick) / Decimal(2))

def get_token_amounts(
    liquidity: int,
    current_tick: int,
    tick_lower: int,
    tick_upper: int,
    decimals0: int,
    decimals1: int,
) -> tuple[Decimal, Decimal]:
    """
    Calculates the underlying token amounts for a given liquidity and price range.
    This is a Python implementation of the core Uniswap V3 logic.
    """
    liquidity = Decimal(liquidity)
    current_price_sqrt = tick_to_price(current_tick)
    lower_price_sqrt = tick_to_price(tick_lower)
    upper_price_sqrt = tick_to_price(tick_upper)
    amount0 = Decimal(0)
    amount1 = Decimal(0)

    if current_tick < tick_lower:
        # Price is below the range, position is entirely in token0
        amount0 = liquidity * (upper_price_sqrt - lower_price_sqrt) / (lower_price_sqrt * upper_price_sqrt)
    elif current_tick >= tick_upper:
        # Price is above the range, position is entirely in token1
        amount1 = liquidity * (upper_price_sqrt - lower_price_sqrt)
    else:
        # Price is within the range
        amount0 = liquidity * (upper_price_sqrt - current_price_sqrt) / (current_price_sqrt * upper_price_sqrt)
        amount1 = liquidity * (current_price_sqrt - lower_price_sqrt)

    # Adjust for token decimals
    amount0_adjusted = amount0 / (Decimal(10) ** decimals0)
    amount1_adjusted = amount1 / (Decimal(10) ** decimals1)

    return amount0_adjusted, amount1_adjusted

# ─── SCRIPT MAIN ──────────────────────────────────────────────────────────────

def main(block_number: int):
    """
    Fetches all positions at a historic block, calculates the real underlying
    token balances, aggregates them by owner, and writes to a JSON file.
    """
    owner_totals = defaultdict(Decimal)

    # Loop through each pool address provided in the list
    for pool_address in POOL_ADDRESSES:
        skip = 0
        print(f"\nStarting snapshot for pool {pool_address} at block {block_number}...", file=sys.stderr)

        while True:
            print(f"Fetching positions for {pool_address} (offset: {skip})...", file=sys.stderr)
            vars = {"pool": pool_address.lower(), "block": block_number, "skip": skip}
            try:
                resp = requests.post(GRAPHQL_URL, json={"query": QUERY, "variables": vars}, timeout=60)
                resp.raise_for_status()
                positions = resp.json().get("data", {}).get("positions", [])
            except requests.exceptions.RequestException as e:
                print(f"ERROR: Could not fetch data from subgraph: {e}", file=sys.stderr)
                sys.exit(1)

            if not positions:
                break

            for pos in positions:
                pool = pos['pool']
                token0_id = pool['token0']['id'].lower()
                token1_id = pool['token1']['id'].lower()

                if not pool['tick']:
                    continue

                amount0, amount1 = get_token_amounts(
                    liquidity=int(pos['liquidity']),
                    current_tick=int(pool['tick']),
                    tick_lower=int(pos['tickLower']['tickIdx']),
                    tick_upper=int(pos['tickUpper']['tickIdx']),
                    decimals0=int(pool['token0']['decimals']),
                    decimals1=int(pool['token1']['decimals']),
                )

                owner_addr = pos["owner"]["id"]
                if token0_id == TARGET_TOKEN:
                    owner_totals[owner_addr] += amount0
                elif token1_id == TARGET_TOKEN:
                    owner_totals[owner_addr] += amount1

            skip += PAGE_SIZE

    # --- Create JSON Output ---
    print("\nProcessing complete. Formatting JSON output...", file=sys.stderr)

    # Define output directory and filename
    output_dir = "json"
    output_file = f"{output_dir}/lp_balances_{TARGET_TOKEN[-6:]}_block_{block_number}.json"
    os.makedirs(output_dir, exist_ok=True)

    # Convert defaultdict of Decimals to a regular dict of strings for JSON serialization
    output_data = {
        owner: str(total)
        for owner, total in owner_totals.items()
        if total > 0
    }

    # Write the data to a JSON file
    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=4)

    print(f"Results for {len(output_data)} owners written to {output_file}", file=sys.stderr)

if __name__ == "__main__":
    block = 19916232
    main(block_number=block)