// ── x402 Payment Protocol Demo ──

import { toast, getConnected, getSigner } from '../main.js';

const X402_SERVICES = {
  signal_query: { method: 'GET', path: '/api/v1/signal?pair=ETH-USDT', amount: '0.001', desc: '市场信号查询' },
  strategy_subscribe: { method: 'POST', path: '/api/v1/strategy/subscribe', amount: '0.01', desc: '策略变更订阅' },
  strategy_params_buy: { method: 'POST', path: '/api/v1/strategy/params/export', amount: '1.00', desc: '完整参数导出' },
  nft_license: { method: 'POST', path: '/api/v1/nft/license', amount: '5.00', desc: 'NFT策略授权' },
};

export function updateX402Preview() {
  const svc = X402_SERVICES[document.getElementById('x402-service').value];
  document.getElementById('x402-preview').innerHTML =
    '<p><span class="text-cyan-400">' + svc.method + '</span> ' + svc.path + '</p>' +
    '<p><span class="text-purple-400">X-Payment:</span> x402-USDT-' + svc.amount + '</p>' +
    '<p><span class="text-purple-400">X-Chain:</span> xlayer-196</p>' +
    '<p><span class="text-purple-400">X-Settle:</span> ' + (parseFloat(svc.amount) < 0.1 ? 'async' : 'sync') + '</p>';
  document.getElementById('x402-status').textContent = '';
}

export async function simulateX402Payment() {
  const svc = X402_SERVICES[document.getElementById('x402-service').value];
  const st = document.getElementById('x402-status');

  // Go directly to simulation mode (x402 server not available in demo)
  st.innerHTML = '<span class="text-yellow-400">x402 Demo Mode — 使用模拟支付流程...</span>';
  await new Promise(r => setTimeout(r, 600));
  st.innerHTML = '<span class="text-cyan-400">模拟: HTTP 402 Payment Required — ' + svc.amount + ' USDT</span>';
  await new Promise(r => setTimeout(r, 800));
  st.innerHTML = '<span class="text-purple-400">模拟: OnchainOS 钱包签名中... (income wallet #2)</span>';
  await new Promise(r => setTimeout(r, 1000));
  const txHash = '0x' + Array.from({ length: 16 }, (_, i) => '0123456789abcdef'[(Date.now() + i * 7) % 16]).join('');
  st.innerHTML = '<span class="text-green-400">模拟完成: TX ' + txHash + '... → ' + svc.desc + '</span>';
  toast('x402 模拟支付: ' + svc.amount + ' USDT → ' + svc.desc, 'green');
}

export function init() {
  document.getElementById('x402-service').addEventListener('change', updateX402Preview);
  document.getElementById('x402-pay-btn').addEventListener('click', simulateX402Payment);
}
