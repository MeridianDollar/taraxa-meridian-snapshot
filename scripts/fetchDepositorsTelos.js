

const { ethers } = require("ethers");
const fs         = require("fs");
const path       = require("path");

// ------------------------------------------
// 1. Configuration
// ------------------------------------------
const RPC_URLS = ["https://rpc.telos.net"];

const CONTRACTS = {
  lendingPoolAddressProvider: "0x703cF2C85EA76C54bd863337585673B3DF8FCE72",
  protocolDataProvider:       "0x6DE58d6dBECF87D7cE972f6E4838fEeCc63B4c5e",
};

const USDM_UNDERLYING = ethers.utils.getAddress("0x8f7D64ea96D729EF24a0F30b4526D47b80d877B9");
const USDT_UNDERLYING = ethers.utils.getAddress("0x975Ed13fa16857E83e7C493C7741D556eaaD4A3f");

const PADDED_USDM_TOPIC = ethers.utils.hexZeroPad(USDM_UNDERLYING, 32);
const PADDED_USDT_TOPIC = ethers.utils.hexZeroPad(USDT_UNDERLYING, 32);
// (we define these in case you later want to filter by reserve)
const TARGET_TOPICS = [PADDED_USDM_TOPIC, PADDED_USDT_TOPIC];

const BLOCK_INCREMENT = 100_000;
const BALANCE_BLOCK   = 416_907_698;

const OUT_DIR        = path.resolve(__dirname, "../json");
const OUT_DEPOSITORS = path.join(OUT_DIR, "depositors_usdm_usdt_taraxa.json");

// ------------------------------------------
// 2. Load your single-ABI file
// ------------------------------------------
const lendingPoolAbi = require("../config/abis.json");  // must be a top-level array

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
        // if you wanted to filter by reserve (USDM/USDT), you could instead:
        // topics: [ [depositTopic], null, TARGET_TOPICS ]
      });
      console.log(`   → ${logs.length} log(s) found`);

      for (const log of logs) {
        if (log.topics.length > 1) {
          const raw      = log.topics[1];  // indexed depositor
          const depositor = ethers.utils.getAddress("0x" + raw.slice(-40));
          allDepositors.add(depositor);
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
  const lpProvider = new ethers.Contract(
    CONTRACTS.lendingPoolAddressProvider,
    lendingPoolAbi,
    provider
  );

  // Resolve the active LendingPool address
  const lendingPoolAddr = await lpProvider.getLendingPool();
  console.log(`🏦 LendingPool address resolved to: ${lendingPoolAddr}\n`);

  // Fetch depositors
  console.log(`🚀 Scanning deposit events up to block ${BALANCE_BLOCK}…`);
  const depositors = await fetchDepositorsInRange(
    provider,
    lendingPoolAddr,
    413_996_255,
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
