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

BLOCK_INCREMENT   = 10000
BALANCE_BLOCK     = 19916232  # <-- scan stops here

OUT_DEPOSITORS    = "json/depositors_all_reserves_taraxa.json"
OUT_BALANCES      = f"json/lending_depositor_balances_block_{BALANCE_BLOCK}.json"

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

# ------------------------------------------
# 3. Fetch Depositors
# ------------------------------------------
def fetch_depositors_in_range(w3, contract_address, from_block, to_block):
    deposit_signature = "Deposit(address,address,address,uint256,uint16)"
    deposit_topic     = w3.keccak(text=deposit_signature).hex()
    all_depositors    = set()

    for start in range(from_block, to_block + 1, BLOCK_INCREMENT):
        end = min(start + BLOCK_INCREMENT - 1, to_block)
        print(f"Scanning logs from {start} to {end}…")

        logs = w3.eth.get_logs({
            "fromBlock": start,
            "toBlock":   end,
            "address":   contract_address,
        })

        for log in logs:
            if not log.get("topics"):
                continue
            if log["topics"][0].hex() != deposit_topic:
                continue
            if len(log["topics"]) < 3:
                continue

            raw = log["topics"][2].hex()
            depositor = Web3.to_checksum_address("0x" + raw[-40:])
            all_depositors.add(depositor)

    return all_depositors

# ------------------------------------------
# 4. Main Workflow
# ------------------------------------------
def main():
    w3 = get_provider(RPC_URLS)

    # Resolve LendingPool address
    lp_provider = w3.eth.contract(
        address=CONTRACTS["lendingPoolAddressProvider"],
        abi=abis.lendingPoolAddressProvider()
    )
    lending_pool_addr = lp_provider.functions.getLendingPool().call()
    print(f"LendingPool address resolved to: {lending_pool_addr}")

    # 4a) Scan depositors
    print(f"\nScanning deposit events up to block {BALANCE_BLOCK}...")
    depositors = fetch_depositors_in_range(
        w3, lending_pool_addr, 16710850, BALANCE_BLOCK
    )
    depositor_list = sorted(depositors)

    if not depositor_list:
        print("No depositors found. Exiting.")
        return

    # Save depositors list
    safe_write_json({
        "block_scanned_up_to": BALANCE_BLOCK,
        "total_depositors": len(depositor_list),
        "depositors": depositor_list
    }, OUT_DEPOSITORS)
    print(f">> Saved {len(depositor_list)} depositors to {OUT_DEPOSITORS}")

    # 4b) Fetch deposit & debt balances for ALL reserves
    print(f"\nFetching deposit & debt balances at block {BALANCE_BLOCK}...")
    data_provider = w3.eth.contract(
        address=CONTRACTS["protocolDataProvider"],
        abi=abis.protocolDataProvider()
    )
    erc20_abi = abis.token()

    # Get all reserves (symbol, underlying)
    reserves = data_provider.functions.getAllReservesTokens().call()
    reserve_list = [(symbol, Web3.to_checksum_address(addr)) for symbol, addr in reserves]

    # Prepare token contracts and decimals
    token_contracts = {}
    decimals = {}
    for symbol, underlying in reserve_list:
        a_token, stable_token, variable_token = data_provider.functions.getReserveTokensAddresses(underlying).call()
        token_contracts[(symbol, 'a')]        = w3.eth.contract(address=a_token,        abi=erc20_abi)
        token_contracts[(symbol, 'stable')]   = w3.eth.contract(address=stable_token,   abi=erc20_abi)
        token_contracts[(symbol, 'variable')] = w3.eth.contract(address=variable_token, abi=erc20_abi)
        decimals[(symbol, 'a')]        = token_contracts[(symbol, 'a')].functions.decimals().call()
        decimals[(symbol, 'stable')]   = token_contracts[(symbol, 'stable')].functions.decimals().call()
        decimals[(symbol, 'variable')] = token_contracts[(symbol, 'variable')].functions.decimals().call()

    # Collect balances per user and reserve
    results = {}
    for i, user in enumerate(depositor_list):
        if (i + 1) % 50 == 0:
            print(f"  ...processed {i+1}/{len(depositor_list)} users")

        user_deposits = {}
        user_debt = {}

        for symbol, _ in reserve_list:
            raw_deposit  = token_contracts[(symbol, 'a')].functions.balanceOf(user).call(block_identifier=BALANCE_BLOCK)
            raw_stable   = token_contracts[(symbol, 'stable')].functions.balanceOf(user).call(block_identifier=BALANCE_BLOCK)
            raw_variable = token_contracts[(symbol, 'variable')].functions.balanceOf(user).call(block_identifier=BALANCE_BLOCK)

            # Only include if non-zero
            if raw_deposit > 0:
                user_deposits[symbol] = raw_deposit / 10**decimals[(symbol, 'a')]
            if raw_stable > 0 or raw_variable > 0:
                debt_entry = {}
                if raw_stable > 0:
                    debt_entry['stable'] = raw_stable / 10**decimals[(symbol, 'stable')]
                if raw_variable > 0:
                    debt_entry['variable'] = raw_variable / 10**decimals[(symbol, 'variable')]
                user_debt[symbol] = debt_entry

        if user_deposits or user_debt:
            results[user] = {}
            if user_deposits:
                results[user]['deposits'] = user_deposits
            if user_debt:
                results[user]['debt'] = user_debt

    # Write out balances
    safe_write_json({
        "block": BALANCE_BLOCK,
        "accounts": results
    }, OUT_BALANCES)
    print(f">> Wrote balances for {len(results)} users to {OUT_BALANCES}")

if __name__ == "__main__":
    main()
