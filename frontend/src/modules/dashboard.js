// ── Dashboard: on-chain data, charts, recent transactions ──

import { CFG, ASSEMBLER_ABI, NFT_ABI, MOD_NAMES } from '../config.js';
import { toast } from '../main.js';
import { loadStrategies } from './strategy.js';
import { loadDecisions } from './journal.js';
import { loadNFTs } from './nft.js';

const rpcProvider = new ethers.JsonRpcProvider(CFG.mainRpc);
const rpcAssembler = new ethers.Contract(CFG.assembler, ASSEMBLER_ABI, rpcProvider);
const rpcAssemblerV2 = new ethers.Contract(CFG.assemblerV2, ASSEMBLER_ABI, rpcProvider);
const rpcNft = new ethers.Contract(CFG.nft, NFT_ABI, rpcProvider);

export { rpcProvider, rpcAssembler, rpcAssemblerV2, rpcNft };

let actChart = null, feeChart = null, rngChart = null, radarChart = null;

export function initCharts() {
  // Activity chart
  actChart = echarts.init(document.getElementById('chart-activity'));
  actChart.setOption({
    backgroundColor: 'transparent',
    grid: { top: 10, bottom: 25, left: 50, right: 10 },
    xAxis: {
      type: 'category',
      data: ['策略数', '决策数', 'Swap 数', 'NFT 数', '交易量(ETH)'],
      axisLabel: { color: '#6b7280', fontSize: 10 },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,.08)' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#6b7280', fontSize: 10 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,.04)' } },
    },
    series: [{
      type: 'bar', data: [0, 0, 0, 0, 0],
      itemStyle: {
        color: function (p) {
          var colors = ['#00f0ff', '#a855f7', '#22c55e', '#eab308', '#00f0ff'];
          return { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: colors[p.dataIndex] }, { offset: 1, color: colors[p.dataIndex] + '33' }] };
        },
      },
      barWidth: 30,
      label: { show: true, position: 'top', color: '#e5e7eb', fontSize: 11, formatter: function (p) { return p.value > 0 ? p.value : '--'; } },
    }],
    tooltip: { trigger: 'axis', backgroundColor: '#1f2937', borderColor: '#374151', textStyle: { color: '#e5e7eb', fontSize: 11 } },
  });

  // Fee curve
  feeChart = echarts.init(document.getElementById('chart-fee'));
  const fX = Array.from({ length: 20 }, (_, i) => i);
  const fY = fX.map(x => 0.05 + 0.95 / (1 + Math.exp(-0.5 * (x - 10))));
  feeChart.setOption({
    backgroundColor: 'transparent', grid: { top: 5, bottom: 20, left: 30, right: 5 },
    xAxis: { type: 'category', data: fX, show: false },
    yAxis: { type: 'value', axisLabel: { color: '#6b7280', fontSize: 9, formatter: v => v.toFixed(1) + '%' }, splitLine: { show: false } },
    series: [{
      type: 'line', data: fY, smooth: true, showSymbol: false, lineStyle: { color: '#00f0ff', width: 2 },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(0,240,255,.25)' }, { offset: 1, color: 'rgba(0,240,255,0)' }] } },
    }],
    title: { text: '费率模型 (Sigmoid)', left: 'center', bottom: 0, textStyle: { color: '#6b7280', fontSize: 9, fontWeight: 'normal' } },
  });

  // Range chart
  rngChart = echarts.init(document.getElementById('chart-range'));
  const rX = Array.from({ length: 30 }, (_, i) => i);
  const price = rX.map(x => 100 + 15 * Math.sin(x / 4) + 3 * Math.sin(x * 1.7 + 2));
  rngChart.setOption({
    backgroundColor: 'transparent', grid: { top: 5, bottom: 15, left: 30, right: 5 },
    xAxis: { type: 'category', data: rX, show: false },
    yAxis: { type: 'value', min: 80, max: 130, axisLabel: { color: '#6b7280', fontSize: 9 }, splitLine: { show: false } },
    series: [
      { type: 'line', data: price, smooth: true, showSymbol: false, lineStyle: { color: '#22d3ee', width: 2 } },
      { type: 'line', data: rX.map(() => 110), showSymbol: false, lineStyle: { color: 'rgba(168,85,247,.5)', type: 'dashed', width: 1 } },
      { type: 'line', data: rX.map(() => 95), showSymbol: false, lineStyle: { color: 'rgba(168,85,247,.5)', type: 'dashed', width: 1 } },
    ],
  });

  // Radar
  radarChart = echarts.init(document.getElementById('chart-radar'));
  radarChart.setOption({
    backgroundColor: 'transparent',
    radar: {
      indicator: [{ name: '策略数', max: 10 }, { name: 'Swap 数', max: 50 }, { name: '决策数', max: 50 }, { name: '交易量(ETH)', max: 10 }, { name: 'NFT 数', max: 10 }],
      shape: 'polygon',
      axisName: { color: '#9ca3af', fontSize: 11 },
      splitArea: { areaStyle: { color: ['rgba(0,240,255,.02)', 'rgba(0,240,255,.04)'] } },
      splitLine: { lineStyle: { color: 'rgba(0,240,255,.12)' } },
      axisLine: { lineStyle: { color: 'rgba(0,240,255,.15)' } },
    },
    series: [{
      type: 'radar', data: [
        { value: [0, 0, 0, 0, 0], name: '协议指标', areaStyle: { color: 'rgba(0,240,255,.12)' }, lineStyle: { color: '#00f0ff', width: 2 }, itemStyle: { color: '#00f0ff' } },
      ],
    }],
    tooltip: { trigger: 'item' },
    title: { text: '链上指标雷达图（实时）', left: 'center', top: 0, textStyle: { color: '#6b7280', fontSize: 11, fontWeight: 'normal' } },
  });

  window.addEventListener('resize', () => {
    [actChart, feeChart, rngChart, radarChart].filter(Boolean).forEach(c => c.resize());
  });
}

function refreshActivityChart(strategies, decisions, swaps, nfts, volumeEth) {
  if (!actChart) return;
  actChart.setOption({
    series: [{
      data: [
        strategies !== null ? Number(strategies) : 0,
        decisions !== null ? Number(decisions) : 0,
        swaps !== null ? Number(swaps) : 0,
        nfts !== null ? Number(nfts) : 0,
        volumeEth !== null ? parseFloat(volumeEth) : 0,
      ],
    }],
  });
}

function refreshRadarChart(strategies, decisions, swaps, nfts, volumeEth) {
  if (!radarChart) return;
  const s = strategies !== null ? Number(strategies) : 0;
  const d = decisions !== null ? Number(decisions) : 0;
  const sw = swaps !== null ? Number(swaps) : 0;
  const n = nfts !== null ? Number(nfts) : 0;
  const vol = volumeEth !== null ? parseFloat(volumeEth) : 0;
  radarChart.setOption({
    radar: {
      indicator: [
        { name: '策略数', max: Math.max(s * 2, 10) },
        { name: 'Swap 数', max: Math.max(sw * 2, 50) },
        { name: '决策数', max: Math.max(d * 2, 50) },
        { name: '交易量(ETH)', max: Math.max(vol * 2, 10) },
        { name: 'NFT 数', max: Math.max(n * 2, 10) },
      ],
    },
    series: [{
      data: [{
        value: [s, sw, d, vol, n], name: '协议指标',
        areaStyle: { color: 'rgba(0,240,255,.12)' }, lineStyle: { color: '#00f0ff', width: 2 }, itemStyle: { color: '#00f0ff' },
      }],
    }],
  });
}

async function loadRecentTransactions() {
  const el = document.getElementById('recent-tx-list');
  try {
    const currentBlock = await rpcProvider.getBlockNumber();
    const fromBlock = Math.max(0, currentBlock - 5000);
    const strategyFilter = rpcAssembler.filters.StrategyCreated ? rpcAssembler.filters.StrategyCreated() : null;
    const decisionFilter = rpcAssembler.filters.DecisionLogged ? rpcAssembler.filters.DecisionLogged() : null;

    let events = [];
    if (strategyFilter) {
      try {
        const sEvents = await rpcAssembler.queryFilter(strategyFilter, fromBlock, currentBlock);
        events = events.concat(sEvents.map(e => ({ type: '策略创建', hash: e.transactionHash, block: e.blockNumber, color: 'bg-cyan-400' })));
      } catch (e) { /* ignore */ }
    }
    if (decisionFilter) {
      try {
        const dEvents = await rpcAssembler.queryFilter(decisionFilter, fromBlock, currentBlock);
        events = events.concat(dEvents.map(e => ({ type: '决策记录', hash: e.transactionHash, block: e.blockNumber, color: 'bg-purple-400' })));
      } catch (e) { /* ignore */ }
    }
    try {
      const nftTransferFilter = rpcNft.filters.Transfer ? rpcNft.filters.Transfer(ethers.ZeroAddress) : null;
      if (nftTransferFilter) {
        const nEvents = await rpcNft.queryFilter(nftTransferFilter, fromBlock, currentBlock);
        events = events.concat(nEvents.map(e => ({ type: 'NFT 铸造', hash: e.transactionHash, block: e.blockNumber, color: 'bg-yellow-400' })));
      }
    } catch (e) { /* ignore */ }

    events.sort((a, b) => b.block - a.block);
    events = events.slice(0, 6);

    if (events.length > 0) {
      let html = '';
      events.forEach(ev => {
        html += `<div class="card p-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full ${ev.color} flex-shrink-0"></span>
            <span class="text-xs text-gray-400">${ev.type}</span>
            <span class="text-xs text-gray-600">Block #${ev.block}</span>
          </div>
          <a href="https://www.oklink.com/xlayer/tx/${ev.hash}" target="_blank" class="text-xs text-[var(--neon)] hover:underline truncate-addr" style="max-width:320px">${ev.hash}</a>
        </div>`;
      });
      el.innerHTML = html;
    } else {
      el.innerHTML = '<div class="text-center py-4 text-gray-600 text-xs">未找到最近交易。<a href="https://www.oklink.com/xlayer/address/' + CFG.assembler + '" target="_blank" class="text-[var(--neon)] hover:underline">在浏览器查看</a></div>';
    }
  } catch (e) {
    el.innerHTML = '<div class="text-center py-4 text-gray-600 text-xs">无法查询事件。<a href="https://www.oklink.com/xlayer/address/' + CFG.assembler + '" target="_blank" class="text-[var(--neon)] hover:underline">在浏览器查看交易</a></div>';
  }
}

export async function refreshDashboard() {
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  try {
    const [sc, dc, sw, vol, dep, ns, sc2, sw2, vol2] = await Promise.allSettled([
      rpcAssembler.strategyCount(), rpcAssembler.decisionCount(),
      rpcAssembler.totalSwapsProcessed(), rpcAssembler.totalVolumeProcessed(),
      rpcAssembler.assemblerDeployedAt(), rpcNft.totalSupply(),
      rpcAssemblerV2.strategyCount(),
      rpcAssemblerV2.totalSwapsProcessed(), rpcAssemblerV2.totalVolumeProcessed(),
    ]);
    const v = r => r.status === 'fulfilled' ? r.value : null;

    const totalStrats = (v(sc) !== null ? Number(v(sc)) : 0) + (v(sc2) !== null ? Number(v(sc2)) : 0);
    const totalSwaps = (v(sw) !== null ? Number(v(sw)) : 0) + (v(sw2) !== null ? Number(v(sw2)) : 0);
    const totalVol = (v(vol) !== null ? v(vol) : 0n) + (v(vol2) !== null ? v(vol2) : 0n);

    set('stat-strategies', totalStrats || '--');
    set('stat-decisions', v(dc) !== null ? Number(v(dc)) : '--');
    set('stat-swaps', totalSwaps || '--');
    set('stat-nfts', v(ns) !== null ? Number(v(ns)) : '--');
    if (totalVol > 0n) set('stat-volume', ethers.formatEther(totalVol) + ' ETH');
    if (v(dep) !== null) {
      const d = new Date(Number(v(dep)) * 1000);
      set('stat-deployed', d.toLocaleDateString() + ' ' + d.toLocaleTimeString());
    }

    set('verified-strategies', totalStrats || '--');
    set('verified-decisions', v(dc) !== null ? Number(v(dc)) : '--');
    set('verified-nfts', v(ns) !== null ? Number(v(ns)) : '--');
    set('verified-swaps', totalSwaps || '--');

    const volEth = v(vol) !== null ? parseFloat(ethers.formatEther(v(vol))) : null;
    refreshActivityChart(v(sc), v(dc), v(sw), v(ns), volEth);
    refreshRadarChart(v(sc), v(dc), v(sw), v(ns), volEth);

    loadRecentTransactions();

    const count = v(sc) !== null ? Number(v(sc)) : 0;
    await loadStrategies(count, rpcAssembler);

    const dcount = v(dc) !== null ? Number(v(dc)) : 0;
    await loadDecisions(dcount, rpcAssembler);

    const ncount = v(ns) !== null ? Number(v(ns)) : 0;
    await loadNFTs(ncount, rpcNft);

    document.getElementById('refresh-status').textContent = '链上数据 | 上次: ' + new Date().toLocaleTimeString() + ' | 自动: 15秒';
  } catch (e) {
    document.getElementById('refresh-status').textContent = 'RPC 连接失败 - 30秒后重试';
    toast('链上数据暂时无法获取，正在重试...', 'red');
  }
}

export function getCharts() {
  return { actChart, feeChart, rngChart, radarChart };
}

export function init() {
  initCharts();
  refreshDashboard();
  setInterval(refreshDashboard, 15000);
}
