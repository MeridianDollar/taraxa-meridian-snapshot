
import os
import sys
import json
import csv
from web3 import Web3


usdm_holders = [
                "0xf6Ad62cCa52a5d3c5d567303347E013c2dadec92",
                "0x02e6ddd40b336247174F37bFA3119eF819db1ef3",
                "0x02F92F357F96c51cc0411Cf9DA1fdb19Fc353478",
                "0xD42eaA28C5EAfEe9a0040a7aC74dd3f4b57678bD",
                "0xb8477F685473cb0C356eB9C56004DA1ceef6cB9D",
                "0x2A354F7de4F0283880A63F5a8a9d39f48d4564c8",
                "0xb4F12Da415e9A06f5869e37a9aeF198EA54Bcb81",
                "0x9aC436368Ab41b295DC3109C6f27e8C1D0CfDA94",
                "0x242f27EFB84bE154A8d05597B5659d0F470E06e1",
                "0xc374d36787C1B2f7C4f3482d7e3dcAA503B4A97e",
                "0xD49EEafa6BdbcC551f462c5A582959a9B7A2EFDb",
                "0x18f5052f99669a687030c9b0485a7e018a4678FD",
                "0x873415F6633A0C42b8717bC898354638F52b13f3",
                "0x6C4803d61799377874519A206A2427AE11C7d9F6",
                "0xa5E8301a8556baF387228c780381341A8940B734",
                "0x885410c6d5945C10409d72976D73Fcc1d3e115bF",
                "0x7918C828Aa465660C4DD61F2a5A1d4EBE0273619",
                "0x668F46Af86E9c90CC067aBc7034Cf9C1803d0f75",
                "0xa47AD24Dd03844aB85E61671340F5A5688fCBB24",
                "0xD03c8F40691A3C4A6049E3A7E644865690af0CDa",
                "0x0B479bcBD016E3E4317b896704679b7DBc2cb6cf",
                "0x173220bD4af07d8659A863F98cf7B46F1C54d745",
                "0x78f3C58cc94563e55054D310888491ee88b70E36",
                "0x78f3C58cc94563e55054D310888491ee88b70E36",
                "0xe2736485271EE622B4ACF6d38518a0F32F83C59C",
                "0x03f985316117708e277D1cE243e957B208aeB4cd"]


# ─── Configuration ────────────────────────────────────────────────────────────

# Default local path to the TroveManager ABI JSON
ABI_PATH = os.getenv("ABI_PATH", "trove_manager_abi.json")

# Ethereum JSON-RPC endpoint, e.g. Infura or Alchemy
WEB3_PROVIDER_URI = "https://rpc.mainnet.taraxa.io"


# TroveManager v1 on Ethereum
TROVE_MANAGER_ADDRESS = "0xd2ff761A55b17a4Ff811B262403C796668Ff610D"
USDM_TOKEN_ADDRESS = "0xC26B690773828999c2612549CC815d1F252EA15e"
# ─── Setup Web3 ────────────────────────────────────────────────────────────────

w3 = Web3(Web3.HTTPProvider(WEB3_PROVIDER_URI))

# ─── Load ABIs ─────────────────────────────────────────────────────────────────

# TroveManager ABI
try:
    with open(ABI_PATH, "r") as f:
        trove_abi = json.load(f)
except FileNotFoundError:
    print(f"Error: ABI file not found at '{ABI_PATH}'.")
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"Error: invalid JSON in ABI file: {e}")
    sys.exit(1)

trove_contract = w3.eth.contract(
    address=w3.to_checksum_address(TROVE_MANAGER_ADDRESS),
    abi=trove_abi
)

# Minimal ERC20 ABI for balanceOf + decimals
erc20_abi = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]

token_contract = w3.eth.contract(
    address=w3.to_checksum_address(USDM_TOKEN_ADDRESS),
    abi=erc20_abi
)

# ─── Main Logic ────────────────────────────────────────────────────────────────

def main():

    block = 19916232

    troves_file  = sys.argv[2] if len(sys.argv) > 2 else None

    # 1) Trove data
    count = trove_contract.functions.getTroveOwnersCount().call(block_identifier=block)
    print(f"Found {count} trove owners at block {block}")

    trove_rows = []
    for i in range(count):
        owner = trove_contract.functions.getTroveFromTroveOwnersArray(i).call(block_identifier=block)
        debt_raw, coll_raw, *_ = trove_contract.functions.Troves(owner).call(block_identifier=block)
        debt = w3.from_wei(debt_raw, "ether")
        coll = w3.from_wei(coll_raw, "ether")
        trove_rows.append((owner, float(debt), float(coll)))

    # 2) Token balances
    decimals      = token_contract.functions.decimals().call()
    token_rows    = []
    for holder in usdm_holders:
        bal_raw = token_contract.functions.balanceOf(holder).call(block_identifier=block)
        bal     = bal_raw / (10 ** decimals)
        token_rows.append((holder, float(bal)))

    # ─── Output ────────────────────────────────────────────────────────────────

    if troves_file:
        # Troves CSV
        with open(troves_file, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["owner", "debt_lusd", "coll_eth"])
            w.writerows(trove_rows)
        print(f"Trove data written to {troves_file}")

        # Token CSV alongside
        tok_file = troves_file.replace(".csv", "_usdm_balances.csv")
        with open(tok_file, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["holder", "usdm_balance"])
            w.writerows(token_rows)
        print(f"USDM balances written to {tok_file}")

    else:
        # Print to console
        print("\n--- Trove Balances ---")
        for owner, debt, coll in trove_rows:
            print(f"{owner} → Debt: {debt:.6f} LUSD | Collateral: {coll:.6f} ETH")

        print("\n--- USDM Token Balances ---")
        for holder, bal in token_rows:
            print(f"{holder} → {bal:.6f} USDM")

if __name__ == "__main__":
    main()