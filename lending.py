# depositors_balances_block.py

import json
import os
import sys
from hexbytes import HexBytes
from web3 import Web3, HTTPProvider
import config.abis as abis

# ------------------------------------------
# 1. Configuration
# ------------------------------------------
RPC_URLS = ["https://rpc.mainnet.taraxa.io"]

CONTRACTS = {
    "lendingPoolAddressProvider": "0x0EdbA5d821B9BCc1654aEf00F65188de636951fa",
    "protocolDataProvider":       "0x0208E7B745591f6c2F02B4DcF53B3e1f11c671df",
}

USDM_UNDERLYING = Web3.to_checksum_address("0xC26B690773828999c2612549CC815d1F252EA15e")
USDT_UNDERLYING = Web3.to_checksum_address("0x69D411CbF6dBaD54Bfe36f81d0a39922625bC78c")

# Padded addresses for efficient topic filtering
PADDED_USDM_TOPIC = "0x" + USDM_UNDERLYING[2:].lower().zfill(64)
PADDED_USDT_TOPIC = "0x" + USDT_UNDERLYING[2:].lower().zfill(64)
TARGET_TOPICS = [PADDED_USDM_TOPIC, PADDED_USDT_TOPIC]


BLOCK_INCREMENT   = 30_000
BALANCE_BLOCK     = 19916232  # <-- scan stops here

OUT_DEPOSITORS    = "json/depositors_usdm_usdt_taraxa.json"
OUT_BALANCES      = f"json/depositor_balances_block_{BALANCE_BLOCK}.json"


# ------------------------------------------
# 2. Helpers
# ------------------------------------------
def get_provider(rpcs):
    for rpc in rpcs:
        try:
            w3 = Web3(HTTPProvider(rpc))
            _ = w3.eth.block_number
            print(f"Successfully connected to RPC: {rpc}")
            return w3
        except Exception as e:
            print(f"RPC failed ({rpc}): {e}", file=sys.stderr)
    raise RuntimeError("All RPC endpoints failed.")


def safe_write_json(data, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=4)

# NEW: Helper to format a log object for printing.
def log_formatter(log_obj):
    """Converts a log object to a nicely formatted JSON string."""
    def json_encoder(o):
        if isinstance(o, HexBytes):
            return o.hex()
        if isinstance(o, bytes):
            return o.hex()
        # Let the default encoder raise the TypeError
        return json.JSONEncoder.default(json.JSONEncoder(), o)

    return json.dumps(log_obj, indent=4, default=json_encoder)


# ------------------------------------------
# 3. Scan for Deposit events
# ------------------------------------------
has_printed_log = False # Global flag to ensure we only print one log

def fetch_depositors(w3, pool_addr, start, end):
    global has_printed_log
    sig    = "Deposit(address,address,address,uint256,uint16)"
    topic0 = w3.keccak(text=sig).hex()

    try:
        logs = w3.eth.get_logs({
            "fromBlock": start,
            "toBlock":   end,
            "address":   pool_addr,
            "topics":    [topic0, TARGET_TOPICS],
        })
    except Exception as e:
        print(f"ERROR: Failed to fetch logs for blocks {start}-{end}. Reason: {e}", file=sys.stderr)
        return set()

    addrs = set()
    for log in logs:
        # --- DEBUG: PRINT THE FIRST EVENT ---
        if not has_printed_log:
            print("\n--- Found first event log. Displaying its full structure: ---")
            print(log_formatter(log))
            print("----------------------------------------------------------\n")
            has_printed_log = True # Set flag to prevent further printing
        # --- END DEBUG ---

        try:
            depositor = Web3.to_checksum_address("0x" + log["data"].hex()[24:64])
            addrs.add(depositor)
        except Exception as e:
            tx_hash = log['transactionHash'].hex()
            print(f"ERROR: Could not parse depositor from log in tx {tx_hash}. Reason: {e}", file=sys.stderr)
            continue
    return addrs


# ------------------------------------------
# 4. Main
# ------------------------------------------
def main():
    w3 = get_provider(RPC_URLS)

    # Resolve LendingPool
    lp_provider = w3.eth.contract(
        address=CONTRACTS["lendingPoolAddressProvider"],
        abi=abis.lendingPoolAddressProvider()
    )
    lending_pool_addr = lp_provider.functions.getLendingPool().call()
    print(f"LendingPool address resolved to: {lending_pool_addr}")

    # 4a) Collect depositors up to BALANCE_BLOCK
    latest_block = w3.eth.block_number
    scan_end     = min(latest_block, BALANCE_BLOCK)
    cursor       = 13672421

    depositors   = set()

    print(f"\nScanning deposit events from block {cursor} to {scan_end} (cap at BALANCE_BLOCK)…")
    while cursor <= scan_end and not (len(depositors) > 0 and has_printed_log): # Stop scanning if we are only debugging one event
        end = min(cursor + BLOCK_INCREMENT - 1, scan_end)
        print(f"  ...scanning blocks {cursor}–{end}")
        batch = fetch_depositors(w3, lending_pool_addr, cursor, end)
        depositors.update(batch)
        cursor = end + 1

    # Dump list of unique depositors
    depositor_list = sorted(list(depositors))
    safe_write_json({
        "block_scanned_up_to": scan_end,
        "total_depositors": len(depositor_list),
        "depositors": depositor_list
    }, OUT_DEPOSITORS)
    print(f">> Found {len(depositor_list)} depositors; wrote to {OUT_DEPOSITORS}")

    if not depositor_list:
        print("\nNo depositors found. Exiting.")
        return

    # 4b) Fetch balances at BALANCE_BLOCK
    print(f"\nFetching aToken balances at block {BALANCE_BLOCK}…")
    data_provider = w3.eth.contract(
        address=CONTRACTS["protocolDataProvider"],
        abi=abis.protocolDataProvider()
    )
    erc20_abi = abis.erc20()

    a_usdm, _, _ = data_provider.functions.getReserveTokensAddresses(USDM_UNDERLYING).call()
    a_usdt, _, _ = data_provider.functions.getReserveTokensAddresses(USDT_UNDERLYING).call()

    a_usdm_ct = w3.eth.contract(address=a_usdm, abi=erc20_abi)
    a_usdt_ct = w3.eth.contract(address=a_usdt, abi=erc20_abi)
    dec_usdm  = a_usdm_ct.functions.decimals().call()
    dec_usdt  = a_usdt_ct.functions.decimals().call()

    balances = {}
    for i, user in enumerate(depositor_list):
        if (i + 1) % 50 == 0:
            print(f"  ...fetched balances for {i+1}/{len(depositor_list)} users")
        try:
            raw_usdm = a_usdm_ct.functions.balanceOf(user).call(block_identifier=BALANCE_BLOCK)
            raw_usdt = a_usdt_ct.functions.balanceOf(user).call(block_identifier=BALANCE_BLOCK)
            
            if raw_usdm == 0 and raw_usdt == 0:
                continue

            balances[user] = {
                "USDM": raw_usdm / (10 ** dec_usdm),
                "USDT": raw_usdt / (10 ** dec_usdt),
            }
        except Exception as e:
            print(f"ERROR: Could not fetch balance for user {user}. Reason: {e}", file=sys.stderr)
            continue
    
    print(f"  ...completed balance fetch for all users.")

    safe_write_json({
        "block": BALANCE_BLOCK,
        "balances": balances
    }, OUT_BALANCES)
    print(f">> Wrote non-zero balances for {len(balances)} depositors to {OUT_BALANCES}")


if __name__ == "__main__":
    main()