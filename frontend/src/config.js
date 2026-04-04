// ── Config: Contract addresses, ABIs, Presets ──

export const CFG = {
  testRpc: 'https://testrpc.xlayer.tech',
  mainRpc: 'https://rpc.xlayer.tech',
  testChainId: 1952,
  mainChainId: 196,
  assembler: '0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78',
  assemblerV2: '0x8da3b913362aa243BC89322Fe8012e70175B6D48',
  v4Hook: '0x174a2450b342042AAe7398545f04B199248E69c0',
  nft: '0x8a0e87395f864405c5225eBd80391Ac82eefe437',
  liquidityShield: '0xd969448dfc24Fe3Aff25e86db338fAB41b104319',
  oracle: '0xCFc867E2379Cbe097D934CB8e19e3F028B82Bd3D',
  dynamicFee: '0x277Ee5801D5d1e5126A76c986c96923AB5eC54Ed',
  mev: '0xA4f6ABd6F77928b06F075637ccBACA8f89e17386',
  rebalance: '0xe04E22e78E1935b60e8827EB72CEc3b56299c8ee',
};

export const ASSEMBLER_ABI = [
  "function strategyCount() view returns (uint256)",
  "function decisionCount() view returns (uint256)",
  "function totalSwapsProcessed() view returns (uint256)",
  "function totalVolumeProcessed() view returns (uint256)",
  "function assemblerDeployedAt() view returns (uint256)",
  "function owner() view returns (address)",
  "function getStrategy(uint256) view returns (tuple(uint256 id, address[] modules, bytes32 configHash, uint256 createdAt, uint256 totalSwaps, uint256 totalVolume, int256 pnlBps, bool active))",
  "function getDecision(uint256) view returns (tuple(uint256 timestamp, uint256 strategyId, bytes32 decisionType, bytes32 reasoningHash, bytes params))",
  "function getActiveModules() view returns (address[])",
  "function createStrategy(address[]) returns (uint256)",
  "function logDecision(uint256, bytes32, bytes32, bytes)",
  "event StrategyCreated(uint256 indexed strategyId, address indexed creator, address[] modules)",
  "event DecisionLogged(uint256 indexed strategyId, bytes32 decisionType)",
];

export const NFT_ABI = [
  "function totalSupply() view returns (uint256)",
  "function ownerOf(uint256) view returns (address)",
  "function getStrategyMeta(uint256) view returns (tuple(address assembler, uint256 strategyId, bytes32 configHash, address[] modules, bytes[] moduleParams, uint256 totalSwaps, uint256 totalVolume, int256 pnlBps, uint256 decisionCount, uint256 mintedAt, uint256 runDurationSeconds, uint256 marketVolatility, uint256 marketPrice))",
  "event Transfer(address indexed from, address indexed to, uint256 indexed tokenId)",
];

export const PRESETS = {
  calm: { name: '稳健积累型', modules: [CFG.dynamicFee, CFG.rebalance], risk: '保守', color: '#22d3ee' },
  volatile: { name: '波动防御型', modules: [CFG.dynamicFee, CFG.mev, CFG.rebalance], risk: '防御', color: '#a855f7' },
  trend: { name: '趋势跟踪型', modules: [CFG.dynamicFee, CFG.mev], risk: '激进', color: '#00f0ff' },
  balanced: { name: '均衡型', modules: [CFG.dynamicFee, CFG.rebalance], risk: '均衡', color: '#eab308' },
};

export const MOD_NAMES = {
  [CFG.dynamicFee.toLowerCase()]: 'DynamicFee',
  [CFG.mev.toLowerCase()]: 'MEV',
  [CFG.rebalance.toLowerCase()]: 'AutoRebalance',
};

export const DECISION_TYPE_MAP = {
  '0x0100000000000000000000000000000000000000000000000000000000000000': '策略创建',
  '0x0200000000000000000000000000000000000000000000000000000000000000': '策略停止',
  '0x0300000000000000000000000000000000000000000000000000000000000000': '费率调整',
  '0x0400000000000000000000000000000000000000000000000000000000000000': '再平衡执行',
  '0x0500000000000000000000000000000000000000000000000000000000000000': '资金转移',
  '0x0600000000000000000000000000000000000000000000000000000000000000': '模块切换',
  '0x0700000000000000000000000000000000000000000000000000000000000000': '表现评估',
  '0x0800000000000000000000000000000000000000000000000000000000000000': '元认知',
  '0x0900000000000000000000000000000000000000000000000000000000000000': 'NFT 铸造',
};

export const DECISION_COLORS = {
  '策略创建': 'text-cyan-400',
  '策略停止': 'text-red-400',
  '费率调整': 'text-green-400',
  '再平衡执行': 'text-yellow-400',
  '资金转移': 'text-blue-400',
  '模块切换': 'text-orange-400',
  '表现评估': 'text-purple-400',
  '元认知': 'text-pink-400',
  'NFT 铸造': 'text-yellow-300',
};

export const DECISION_REASONS = {
  '策略创建': 'AI 分析市场状态后创建新的 Hook 策略组合，根据波动率和趋势选择最优模块配置',
  '策略停止': '策略表现未达预期或市场条件发生重大变化，AI 决定暂停策略以保护 LP 资金',
  '费率调整': '波动率变化触发动态费率调整，提高交易量或保护 LP 免受无常损失',
  '再平衡执行': '价格偏离流动性范围边界，AI 触发自动再平衡以维持最优头寸',
  '资金转移': '在多钱包体系中转移资金，用于策略部署、收益归集或储备金补充',
  '模块切换': '市场制度转变，AI 切换 Hook 模块组合以适应新的市场环境',
  '表现评估': '定期评估策略的 P&L、Swap 处理量、费率收益，记录到决策日志',
  '元认知': 'AI 自我评估决策质量，检测认知偏差，调整信心阈值和模型参数',
  'NFT 铸造': '策略达到铸造阈值（P&L>=1%, Swap>=50, 运行>=48h），铸造 Strategy NFT',
};

// Embedded agent state from last run (updated by agent_service)
export const EMBEDDED_AGENT_STATE = {
  cycle_count: 3,
  preferences: { risk_tolerance: 0.52, rebalance_eagerness: 0.5, new_strategy_bias: 0.6 },
  prediction_accuracy: 0.5,
  ml_state: {
    ema_fast: 2053.24, ema_slow: 2061.75, momentum_score: -0.004132,
    bayesian_prior: { calm: 0.435, volatile: 0.271, trending: 0.294 },
    price_history_len: 500, vol_history_len: 35, action_outcomes_len: 0, pretrained: true,
  },
  engine_status: {
    running: false, paused: true, mode: 'paper', cycle_count: 3, prediction_accuracy: 0.5,
    preferences: { risk_tolerance: 0.52, rebalance_eagerness: 0.5, new_strategy_bias: 0.6 },
    ml_momentum: { ema_fast: 2053.24, ema_slow: 2061.75, momentum_score: -0.004132, signal: 'neutral' },
    ml_forecast: { slope: -0.211, r_squared: 0.156, predicted_change_pct: -0.051, n: 30, direction: 'down' },
    bayesian_regime: { calm: 0.435, volatile: 0.271, trending: 0.294 },
  },
};
