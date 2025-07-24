import os
import sys
import json
from web3 import Web3
import config.abis as abis


# List of non-zero balance USDM address from Tara.to
usdm_holders = list(set([
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
    "0xe2736485271EE622B4ACF6d38518a0F32F83C59C",
    "0x03f985316117708e277D1cE243e957B208aeB4cd"
]))


# ─── Configuration ────────────────────────────────────────────────────────────


WEB3_PROVIDER_URI = "https://rpc.mainnet.taraxa.io"

# Contract Addresses
TROVE_MANAGER_ADDRESS = "0xd2ff761A55b17a4Ff811B262403C796668Ff610D"
USDM_TOKEN_ADDRESS = "0xC26B690773828999c2612549CC815d1F252EA15e"

# ─── Setup Web3 ────────────────────────────────────────────────────────────────

w3 = Web3(Web3.HTTPProvider(WEB3_PROVIDER_URI))

# ─── Load ABIs ─────────────────────────────────────────────────────────────────

# TroveManager ABI
trove_contract = w3.eth.contract(
    address=w3.to_checksum_address(TROVE_MANAGER_ADDRESS),
    abi=abis.troveManager()
)

# Minimal ERC20 ABI for balanceOf + decimals
erc20_abi = [
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"}
]

token_contract = w3.eth.contract(
    address=w3.to_checksum_address(USDM_TOKEN_ADDRESS),
    abi=erc20_abi
)

# ─── Main Logic ────────────────────────────────────────────────────────────────

def main():
    block = 19916232

    # 1) Get Trove data
    print(f"Fetching trove data at block {block}...")
    count = trove_contract.functions.getTroveOwnersCount().call(block_identifier=block)
    print(f"Found {count} trove owners.")

    troves_data = []
    for i in range(count):
        owner = trove_contract.functions.getTroveFromTroveOwnersArray(i).call(block_identifier=block)
        debt_raw, coll_raw, *_ = trove_contract.functions.Troves(owner).call(block_identifier=block)
        
        debt = w3.from_wei(debt_raw, "ether")
        coll = w3.from_wei(coll_raw, "ether")
        
        troves_data.append({
            "owner": owner,
            "debt_usdm": str(debt),
            "collateral_tara": str(coll)
        })
        if (i + 1) % 100 == 0:
            print(f"  ...processed {i+1}/{count} troves")

    # 2) Get Token balances
    print(f"\nFetching USDM token balances for {len(usdm_holders)} unique holders...")
    decimals = token_contract.functions.decimals().call()
    token_balances = {}
    for holder in usdm_holders:
        bal_raw = token_contract.functions.balanceOf(w3.to_checksum_address(holder)).call(block_identifier=block)
        bal = bal_raw / (10 ** decimals)
        if bal > 0: # Only include holders with a non-zero balance
            token_balances[holder] = str(bal)

    # ─── Output to JSON File ──────────────────────────────────────────────────

    output_dir = "json"
    os.makedirs(output_dir, exist_ok=True)
    output_filename = f"{output_dir}/trove_snapshot_block_{block}.json"

    output_json = {
        "block_number": block,
        "troves": troves_data,
        "token_balances": token_balances
    }

    with open(output_filename, "w") as f:
        json.dump(output_json, f, indent=4)

    print(f"\n✓ Success! All data written to {output_filename}")

if __name__ == "__main__":
    main()