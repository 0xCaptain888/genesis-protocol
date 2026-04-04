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

  st.innerHTML = '<span class="text-yellow-400">发送 HTTP 请求到 x402 服务器...</span>';

  try {
    const isGet = svc.method === 'GET';
    const url = 'http://localhost:8402' + svc.path.split('?')[0] + (isGet ? '?pair=ETH-USDT' : '');

    const r1 = await fetch(url, { method: svc.method, headers: { 'Content-Type': 'application/json' } });

    if (r1.status === 402) {
      const data402 = await r1.json();
      st.innerHTML = '<span class="text-cyan-400">收到 HTTP 402 Payment Required — 需支付 ' + svc.amount + ' USDT</span>';
      await new Promise(r => setTimeout(r, 1000));

      st.innerHTML = '<span class="text-purple-400">发送支付证明...</span>';
      const proof = Array.from({ length: 32 }, (_, i) => '0123456789abcdef'[(Date.now() + i * 7) % 16]).join('');

      const connected = getConnected();
      const signer = getSigner();
      const r2 = await fetch(url, {
        method: svc.method,
        headers: {
          'Content-Type': 'application/json',
          'X-Payment-Proof': proof,
          'X-Payer-Address': connected ? await signer.getAddress() : '0xdemo',
        },
        body: isGet ? undefined : JSON.stringify({ preset: 'volatile_defender' }),
      });

      if (r2.ok) {
        const data = await r2.json();
        st.innerHTML = '<span class="text-green-400">x402 支付成功！真实服务器返回数据 (' + Object.keys(data).length + ' 字段)</span>';
        toast('x402 真实支付完成: ' + svc.amount + ' USDT → ' + svc.desc, 'green');
        return;
      }
    }
  } catch (e) {
    // x402 server not running, fall back to simulation
  }

  // Fallback: simulation mode
  st.innerHTML = '<span class="text-yellow-400">x402 服务器离线，使用模拟模式...</span>';
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
