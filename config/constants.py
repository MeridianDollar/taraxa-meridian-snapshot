SUBGRAPH_URL = 'https://subgraph.meridianfinance.net/subgraphs/name/perpetuals-stats'
MTR_EVENT_ID = "0x8cdc9b2118d2ce55a299f8f1d700d0127cf4036d1aa666a8cd51dcab4254284f"
MTRG_EVENT_ID = "0x20d096e088a9b85f8cf09278965b77aeb05c00769e2ddeda5ea2d07ea554b283"
BASE_PATH = "json/trading/prices/meter"

BASE = 1.0001
INITIAL_MST_SUPPLY = 7000000 * 1e18
LEND_ORACLE_PRECISION = 100000000
MIN_BLOCK_DIFF = 100

# precision
ORACLE_PRECISION = 1e8
ONE_NONILLION = 1e30
WEI =  1e18
RAY = 1e27

# Time
SECONDS_PER_YEAR = 31536000
SECONDS_PER_DAY = 86400
DAYS_PER_YEAR = 365

BLOCK_INCREMENT = {
    'telos': 100000,
    'taiko': 1000,
    'fuse': 10000,
    'meter': 1000,
    'base': 2500,
    'artela': 300,
    'taraxa': 300,
    # Add other networks as needed
}