// ── Main: App initialization, wallet connect, routing ──

import { CFG, ASSEMBLER_ABI, NFT_ABI, EMBEDDED_AGENT_STATE } from './config.js';
import * as i18n from './i18n.js';
import * as market from './modules/market.js';
import * as engine from './modules/engine.js';
import * as dashboard from './modules/dashboard.js';
import * as strategy from './modules/strategy.js';
import * as journal from './modules/journal.js';
import * as nft from './modules/nft.js';
import * as x402 from './modules/x402.js';
import * as aiDecision from './modules/aiDecision.js';

// ── State ──
let provider = null, signer = null, assemblerC = null, nftC = null, connected = false;

// ── Exported state accessors ──
export function getConnected() { return connected; }
export function getSigner() { return signer; }
export function getAssemblerC() { return assemblerC; }
export function getNftC() { return nftC; }

// ── Toast (queue-based, no stacking) ──
let _toastQueue = [], _toastActive = false;

export function toast(msg, color) {
  _toastQueue.push({ msg, color });
  if (!_toastActive) _showNextToast();
}

function _showNextToast() {
  if (_toastQueue.length === 0) { _toastActive = false; return; }
  _toastActive = true;
  const { msg, color } = _toastQueue.shift();
  document.querySelectorAll('.toast').forEach(t => t.remove());
  const t = document.createElement('div');
  t.className = 'toast';
  t.style.background = color === 'green' ? '#065f46' : color === 'red' ? '#7f1d1d' : '#164e63';
  t.style.color = color === 'green' ? '#6ee7b7' : color === 'red' ? '#fca5a5' : '#67e8f9';
  t.textContent = msg;
  t.onclick = () => { t.remove(); _showNextToast(); };
  document.body.appendChild(t);
  setTimeout(() => { if (t.parentNode) t.remove(); _showNextToast(); }, 3500);
}

// ── Wallet ──
async function connectWallet() {
  const w = window.ethereum || window.okxwallet;
  if (!w) return toast('请安装 MetaMask 或 OKX Wallet', 'red');
  try {
    provider = new ethers.BrowserProvider(w);
    await provider.send('eth_requestAccounts', []);
    const net = await provider.getNetwork();
    if (Number(net.chainId) !== CFG.mainChainId) {
      try {
        await provider.send('wallet_switchEthereumChain', [{ chainId: '0x' + CFG.mainChainId.toString(16) }]);
      } catch (e) {
        if (e.code === 4902 || e?.data?.originalError?.code === 4902) {
          await provider.send('wallet_addEthereumChain', [{
            chainId: '0x' + CFG.mainChainId.toString(16), chainName: 'X Layer',
            nativeCurrency: { name: 'OKB', symbol: 'OKB', decimals: 18 },
            rpcUrls: [CFG.mainRpc], blockExplorerUrls: ['https://www.oklink.com/xlayer'],
          }]);
        } else throw e;
      }
    }
    signer = await provider.getSigner();
    const addr = await signer.getAddress();
    assemblerC = new ethers.Contract(CFG.assembler, ASSEMBLER_ABI, signer);
    nftC = new ethers.Contract(CFG.nft, NFT_ABI, signer);
    connected = true;
    document.getElementById('connect-btn').textContent = addr.slice(0, 6) + '...' + addr.slice(-4);
    document.getElementById('network-badge').innerHTML = '<span class="w-2 h-2 rounded-full bg-green-400"></span> X Layer 主网';
    document.getElementById('deploy-btn').disabled = false;
    document.getElementById('deploy-btn').textContent = '部署策略';
    toast('钱包已连接: ' + addr.slice(0, 8) + '...', 'green');
    window.dispatchEvent(new Event('wallet-connected'));
    w.on('chainChanged', () => location.reload());
    w.on('accountsChanged', () => location.reload());
  } catch (e) {
    toast('连接失败: ' + e.message, 'red');
  }
}

// ── Guided Tour ──
function startGuidedTour() {
  const steps = [
    { target: '#market', msg: '第1步: 查看 AI 实时市场感知 — 波动率、制度分类、资金费率' },
    { target: '#ai-engine', msg: '第2步: 启动 AI 认知引擎 — 5层认知循环实时推理' },
    { target: '#ai-decision', msg: '第3步: AI 决策面板 — 置信度、市场区间、LLM 推理链' },
    { target: '#dashboard', msg: '第4步: 链上实时仪表盘 — 所有数据来自 X Layer 合约' },
    { target: '#activity-timeline', msg: '第5步: 链上活动时间线 — 所有交易按时间排序' },
    { target: '#backtest', msg: '第6步: 回测分析 — 各策略预设的历史表现对比' },
    { target: '#strategies', msg: '第7步: 部署策略 — 连接钱包后可真实部署' },
    { target: '#nfts', msg: '第8步: 策略 NFT — 达标策略自动铸造为链上 NFT' },
    { target: '#x402', msg: '第9步: x402 支付协议 — AI Agent 间的链上微支付' },
  ];
  let i = 0;
  function showStep() {
    if (i >= steps.length) { toast('体验完成！尝试连接钱包部署策略', 'green'); return; }
    const s = steps[i];
    const el = document.querySelector(s.target);
    if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
    toast(s.msg, 'cyan');
    i++;
    setTimeout(showStep, 4500);
  }
  showStep();
}

// ── Init ──
function initApp() {
  // Set embedded agent state before engine init
  engine.setEmbeddedState(EMBEDDED_AGENT_STATE);

  // Bind wallet connect buttons
  document.getElementById('connect-btn').addEventListener('click', connectWallet);
  document.getElementById('hero-connect-btn').addEventListener('click', connectWallet);
  document.getElementById('tour-btn').addEventListener('click', startGuidedTour);

  // Initialize all modules
  i18n.init();
  market.init();
  engine.init();
  strategy.init();
  journal.init();
  nft.init();
  x402.init();
  dashboard.init();

  // Initialize AI Decision Panel (needs rpc references from dashboard)
  const { rpcProvider: rp, rpcAssembler: ra, rpcNft: rn } = dashboard;
  aiDecision.init(rp, ra, rn);
  aiDecision.updateBacktestFromState(EMBEDDED_AGENT_STATE);

  // Handle chart resize for price chart
  window.addEventListener('resize', () => {
    const pc = market.getPriceChart();
    if (pc) pc.resize();
  });
}

// Export aiDecision for engine access
export { aiDecision };

// Start when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}
