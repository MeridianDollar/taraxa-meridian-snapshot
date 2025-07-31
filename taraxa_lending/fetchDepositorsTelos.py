import json
import os
import sys
from hexbytes import HexBytes
from web3 import Web3, HTTPProvider
import config.abis as abis

# ------------------------------------------
# 1. Configuration
# ------------------------------------------
RPC_URLS = ["https://rpc-private.mainnet.taraxa.io"]

CONTRACTS = {
    "lendingPoolAddressProvider": "0x0EdbA5d821B9BCc1654aEf00F65188de636951fa",
    "protocolDataProvider":       "0x0208E7B745591f6c2F02B4DcF53B3e1f11c671df",
}


BLOCK_INCREMENT   = 1000
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

# ------------------------------------------
# 3. Fetch and Print Deposit Events in Chunks
# ------------------------------------------
def fetch_depositors_in_range(w3, contract_address, from_block, to_block):
    """
    Fetch all Deposit events between from_block and to_block in BLOCK_INCREMENT chunks.
    Returns a set of depositor addresses.
    """
    # Only one signature → one topic
    deposit_signature = "Deposit(address,address,address,uint256,uint16)"
    deposit_topic = w3.keccak(text=deposit_signature).hex()
    all_depositors = set()

    for start in range(from_block, to_block + 1, BLOCK_INCREMENT):
        end = min(start + BLOCK_INCREMENT - 1, to_block)
        print(f"Scanning Deposit events from {start} to {end}…")

        filter_params = {
            "fromBlock": start,
            "toBlock":   end,
            "address":   contract_address,
            "topics":    [[deposit_topic]],
        }

        try:
            logs = w3.eth.get_logs(filter_params)
            print(f"  → {len(logs)} logs")

            for log in logs:
                # topic[1] is the indexed depositor address
                if len(log["topics"]) > 1:
                    addr_hex = log["topics"][1].hex()  # "0x0000…abcd"
                    depositor = Web3.to_checksum_address("0x" + addr_hex[-40:])
                    all_depositors.add(depositor)

        except Exception as e:
            print(f"Error fetching {start}–{end}: {e}", file=sys.stderr)

    return all_depositors

# ------------------------------------------
# 4. Main Workflow
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

    # 4a) Scan depositors up to BALANCE_BLOCK
    print(f"\nScanning deposit events up to block {BALANCE_BLOCK}...")
    depositors = fetch_depositors_in_range(w3, lending_pool_addr,16792600, BALANCE_BLOCK)


if __name__ == "__main__":
    main()