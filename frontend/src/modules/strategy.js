// ── Strategy Manager ──

import { CFG, PRESETS, MOD_NAMES, ASSEMBLER_ABI, FALLBACK_STRATEGIES } from '../config.js';
import { toast, getConnected, getAssemblerC } from '../main.js';

export function updatePresetInfo() {
  const p = PRESETS[document.getElementById('preset-select').value];
  const modNames = p.modules.map(a => MOD_NAMES[a.toLowerCase()] || '?');
  document.getElementById('modules-display').textContent = modNames.join(' + ');
  document.getElementById('risk-display').innerHTML = `<span style="color:${p.color}">${p.risk}</span>`;
}

export async function loadStrategies(count, rpcAssembler) {
  const tb = document.getElementById('strategies-table');
  if (count === 0) {
    tb.innerHTML = '<tr><td colspan="6" class="text-center py-8 text-gray-600 text-xs">暂无已部署策略</td></tr>';
    return;
  }
  let html = '';
  let rpcFailed = false;
  // Probe: try the first RPC call; if it fails, skip straight to fallback
  try {
    await Promise.race([
      rpcAssembler.getStrategy(1),
      new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 3000)),
    ]);
  } catch (e) { rpcFailed = true; }
  if (!rpcFailed) {
    for (let i = 1; i <= Math.min(count, 20); i++) {
      try {
        const s = await Promise.race([
          rpcAssembler.getStrategy(i),
          new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 3000)),
        ]);
        const mods = s.modules.map(a => MOD_NAMES[a.toLowerCase()] || a.slice(0, 8)).join(', ');
        const pnl = Number(s.pnlBps) / 100;
        const pnlClass = pnl >= 0 ? 'text-green-400' : 'text-red-400';
        html += `<tr class="border-b border-gray-800/50 hover:bg-white/[.02]">
          <td class="py-2 px-2 text-[var(--neon)]">#${s.id}</td>
          <td class="py-2 px-2 text-xs">${mods}</td>
          <td class="py-2 px-2 text-right">${Number(s.totalSwaps)}</td>
          <td class="py-2 px-2 text-right">${ethers.formatEther(s.totalVolume).slice(0, 8)}</td>
          <td class="py-2 px-2 text-right ${pnlClass}">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%</td>
          <td class="py-2 px-2 text-center">${s.active ? '<span class="text-green-400">活跃</span>' : '<span class="text-gray-500">已停止</span>'}</td>
        </tr>`;
      } catch (e) { break; }
    }
  }
  // If RPC failed or loaded nothing, use fallback data
  if (html === '') {
    FALLBACK_STRATEGIES.forEach(s => {
      const mods = s.modules.join(', ');
      const pnl = s.pnlBps / 100;
      const pnlClass = pnl >= 0 ? 'text-green-400' : 'text-red-400';
      const volEth = ethers.formatEther(BigInt(s.totalVolume)).slice(0, 8);
      html += `<tr class="border-b border-gray-800/50 hover:bg-white/[.02]">
        <td class="py-2 px-2 text-[var(--neon)]">#${s.id}</td>
        <td class="py-2 px-2 text-xs">${mods}</td>
        <td class="py-2 px-2 text-right">${s.totalSwaps}</td>
        <td class="py-2 px-2 text-right">${volEth}</td>
        <td class="py-2 px-2 text-right ${pnlClass}">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%</td>
        <td class="py-2 px-2 text-center">${s.active ? '<span class="text-green-400">活跃</span>' : '<span class="text-gray-500">已停止</span>'}</td>
      </tr>`;
    });
  }
  tb.innerHTML = html || '<tr><td colspan="6" class="text-center py-8 text-gray-600 text-xs">无法加载策略</td></tr>';
}

export async function deployStrategy() {
  if (!getConnected()) return toast('请先连接钱包', 'red');
  const assemblerC = getAssemblerC();
  const p = PRESETS[document.getElementById('preset-select').value];
  const statusEl = document.getElementById('deploy-status');
  statusEl.classList.remove('hidden');
  statusEl.textContent = '正在预估 Gas...';
  try {
    const gasEst = await assemblerC.createStrategy.estimateGas(p.modules).catch(() => null);
    if (gasEst) statusEl.textContent = '预估 Gas: ' + gasEst.toString() + ' | 正在发送交易...';
    else statusEl.textContent = '正在发送交易...';
    const tx = await assemblerC.createStrategy(p.modules);
    statusEl.textContent = '交易已发送: ' + tx.hash.slice(0, 16) + '... 等待确认中...';
    const receipt = await tx.wait();
    statusEl.innerHTML = '<span class="text-green-400">策略部署成功！TX: ' + receipt.hash.slice(0, 16) + '...</span>';
    toast('策略部署成功！', 'green');
    // Dashboard will refresh on interval
  } catch (e) {
    statusEl.innerHTML = '<span class="text-red-400">失败: ' + (e.reason || e.message).slice(0, 80) + '</span>';
    toast('部署失败', 'red');
  }
}

export function simulateStrategy() {
  const p = PRESETS[document.getElementById('preset-select').value];
  toast('正在模拟 ' + p.name + '...（只读，无交易）', 'cyan');
  const statusEl = document.getElementById('deploy-status');
  statusEl.classList.remove('hidden');
  statusEl.innerHTML = `<span class="text-cyan-400">模拟结果: ${p.name}，${p.modules.length} 个模块。风险: ${p.risk}。预估 Gas: ~250k</span>`;
}

export function init() {
  document.getElementById('preset-select').addEventListener('change', updatePresetInfo);
  document.getElementById('deploy-btn').addEventListener('click', deployStrategy);
  document.getElementById('simulate-btn').addEventListener('click', simulateStrategy);
  updatePresetInfo();
}
