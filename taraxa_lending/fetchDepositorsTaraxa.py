import json
import os
import sys
from hexbytes import HexBytes
from web3 import Web3, HTTPProvider
import config.abis as abis

# ------------------------------------------
# 1. Configuration
# ------------------------------------------
RPC_URLS = ["https://rpc.telos.net"]

CONTRACTS = {
    "lendingPoolAddressProvider": "0x703cF2C85EA76C54bd863337585673B3DF8FCE72",
    "protocolDataProvider":       "0x6DE58d6dBECF87D7cE972f6E4838fEeCc63B4c5e",
}

USDM_UNDERLYING = Web3.to_checksum_address("0x8f7D64ea96D729EF24a0F30b4526D47b80d877B9")
USDT_UNDERLYING = Web3.to_checksum_address("0x975Ed13fa16857E83e7C493C7741D556eaaD4A3f")

# Padded addresses for efficient topic filtering
PADDED_USDM_TOPIC = "0x" + USDM_UNDERLYING[2:].lower().zfill(64)
PADDED_USDT_TOPIC = "0x" + USDT_UNDERLYING[2:].lower().zfill(64)
TARGET_TOPICS = [PADDED_USDM_TOPIC, PADDED_USDT_TOPIC]

BLOCK_INCREMENT   = 100000
BALANCE_BLOCK     = 416907698  # <-- scan stops here

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
    depositors = fetch_depositors_in_range(w3, lending_pool_addr,413996255, BALANCE_BLOCK)

if __name__ == "__main__":
    main()