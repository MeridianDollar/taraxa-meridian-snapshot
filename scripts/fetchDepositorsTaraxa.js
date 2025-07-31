// scripts/fetchDepositors.js

const { ethers } = require("ethers");
const fs      = require("fs");
const path    = require("path");

// ------------------------------------------
// 1. Configuration
// ------------------------------------------
const RPC_URLS = ["https://rpc-private.mainnet.taraxa.io"];

const CONTRACTS = {
  lendingPoolAddressProvider: "0x0EdbA5d821B9BCc1654aEf00F65188de636951fa",
};

const BLOCK_INCREMENT = 1000;
const FROM_BLOCK      = 16792600;
const BALANCE_BLOCK   = 19916232;

const OUT_DIR        = path.resolve(__dirname, "../json");
const OUT_DEPOSITORS = path.join(OUT_DIR, `depositors_usdm_usdt_taraxa.json`);

// ------------------------------------------
// 2. Load your single ABI file
// ------------------------------------------
const lendingPoolAbi = require("../config/abis.json");

// ------------------------------------------
// 3. Helpers
// ------------------------------------------
async function getProvider(rpcs) {
  for (const rpc of rpcs) {
    try {
      const provider = new ethers.providers.JsonRpcProvider(rpc);
      await provider.getBlockNumber();
      console.log(`✅ Connected to RPC: ${rpc}`);
      return provider;
    } catch (e) {
      console.error(`❌ RPC failed (${rpc}): ${e.message}`);
    }
  }
  throw new Error("All RPC endpoints failed.");
}

async function fetchDepositorsInRange(provider, contractAddress, fromBlock, toBlock) {
  const depositSig   = "Deposit(address,address,address,uint256,uint16)";
  const depositTopic = ethers.utils.id(depositSig);
  const allDepositors = new Set();

  for (let start = fromBlock; start <= toBlock; start += BLOCK_INCREMENT) {
    const end = Math.min(start + BLOCK_INCREMENT - 1, toBlock);
    console.log(`🔍 Scanning Deposit events from ${start} to ${end}…`);

    try {
      const logs = await provider.getLogs({
        fromBlock: start,
        toBlock:   end,
        address:   contractAddress,
        topics:    [[depositTopic]],
      });
      console.log(`   → ${logs.length} log(s) found`);

      for (const { topics } of logs) {
        if (topics.length > 1) {
          const raw     = topics[1]; // indexed depositor
          const address = ethers.utils.getAddress("0x" + raw.slice(-40));
          allDepositors.add(address);
        }
      }
    } catch (e) {
      console.error(`   ! Error fetching ${start}–${end}: ${e.message}`);
    }
  }

  return Array.from(allDepositors);
}

// ------------------------------------------
// 4. Main Workflow
// ------------------------------------------
async function main() {
  const provider = await getProvider(RPC_URLS);

  // Instantiate the AddressProvider contract
  const lpProviderContract = new ethers.Contract(
    CONTRACTS.lendingPoolAddressProvider,
    lendingPoolAbi,
    provider
  );

  // Resolve the active LendingPool address
  const lendingPoolAddr = await lpProviderContract.getLendingPool();
  console.log(`🏦 LendingPool address resolved to: ${lendingPoolAddr}\n`);

  // Fetch depositors
  console.log(`🚀 Scanning deposit events up to block ${BALANCE_BLOCK}…`);
  const depositors = await fetchDepositorsInRange(
    provider,
    lendingPoolAddr,
    FROM_BLOCK,
    BALANCE_BLOCK
  );
  console.log(`\n🎉 Found ${depositors.length} unique depositor(s).`);

  // Write results
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.writeFileSync(OUT_DEPOSITORS, JSON.stringify(depositors, null, 2));
  console.log(`💾 Depositors saved to ${OUT_DEPOSITORS}`);
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
