// dashboard-part2.js  — sector render, flags, logs, evolution, SSE, init

function renderSectors(sectors) {
  const cells = Object.entries(sectors).sort((a,b) => b[1]-a[1]);
  document.getElementById('sector-heatmap').innerHTML = cells.map(([name,chg]) => {
    const abs = Math.min(Math.abs(chg)/4, 1);
    const bg  = chg >= 0 ? `rgba(0,230,118,${(0.15+abs*0.5).toFixed(2)})` : `rgba(255,77,109,${(0.15+abs*0.5).toFixed(2)})`;
    const col = chg >= 0 ? '#00e676' : '#ff4d6d';
    return `<div class="sector-cell" style="background:${bg};color:${col}">${name}<br>${chg>=0?'+':''}${chg.toFixed(2)}%</div>`;
  }).join('');

  document.querySelector('#sector-tbl tbody').innerHTML = cells.map(([name,chg]) =>
    `<tr><td>${name}</td>
     <td class="mono ${chg>=0?'up':'dn'}">${chg>=0?'+':''}${chg.toFixed(2)}%</td>
     <td><div style="width:${Math.min(Math.abs(chg)/4*100,100).toFixed(0)}%;height:4px;background:${chg>=0?'var(--green)':'var(--red)'};border-radius:2px"></div></td></tr>`
  ).join('');
}

function renderFlags(flags) {
  const html = (flags||[]).map(f =>
    `<div class="flag-item"><span class="flag-icon">&#9888;</span>${f}</div>`
  ).join('');
  const el = document.getElementById('rt-flags');
  const el2 = document.getElementById('risk-flags-overview');
  if(el)  el.innerHTML  = html || '<div style="color:var(--text2);font-size:11px;padding:4px 0">&#x2713; 暂无风险预警</div>';
  if(el2) el2.innerHTML = html;
}

function renderLogs(logs) {
  document.getElementById('log-list').innerHTML = [...(logs||[])].reverse().map(l =>
    `<div class="log-item">
      <span class="log-t">${l.time}</span>
      <span class="log-lvl log-${l.level}">${l.level}</span>
      <span class="log-msg">${l.msg}</span>
    </div>`
  ).join('');
}

function renderEvolution(memory, iterCount) {
  const regimeMap = {trending:'趋势行情', ranging:'震荡行情', volatile:'高波动', crisis:'危机模式', unknown:'未知'};
  const regime = document.getElementById('evo-regime');
  const iter   = document.getElementById('evo-iter');
  if(regime) regime.textContent = regimeMap[memory.market_regime] || memory.market_regime;
  if(iter)   iter.textContent   = iterCount + ' 轮';

  const ruleEl = document.getElementById('rules-list');
  if(ruleEl) ruleEl.innerHTML = (memory.learned_rules||[]).map((r,i) =>
    `<div class="rule-item"><span class="rule-idx">${String(i+1).padStart(2,'0')}</span>${r}</div>`
  ).join('');

  const sucEl = document.getElementById('success-patterns');
  if(sucEl) sucEl.innerHTML = (memory.successful_patterns||[]).map(p =>
    `<div class="rule-item" style="border-left-color:var(--green)"><span class="rule-idx" style="color:var(--green)">&#x2713;</span>${p}</div>`
  ).join('');

  const failEl = document.getElementById('fail-patterns');
  if(failEl) failEl.innerHTML = (memory.failed_patterns||[]).map(p =>
    `<div class="rule-item" style="border-left-color:var(--red)"><span class="rule-idx" style="color:var(--red)">&#x2717;</span>${p}</div>`
  ).join('');
}

// CLOCK
function updateClock() {
  const now = new Date();
  const el = document.getElementById('top-clock');
  const sb = document.getElementById('sb-ts');
  if(el) el.textContent = now.toLocaleTimeString('zh-CN', {hour12:false});
  if(sb) sb.textContent = now.toLocaleString('zh-CN');
}
setInterval(updateClock, 1000);
updateClock();

// MAIN INIT
async function init() {
  try {
    const [state, curve] = await Promise.all([
      fetch('/api/state').then(r => r.json()),
      fetch('/api/equity_curve').then(r => r.json()),
    ]);

    initEquityChart(curve);
    initRadarChart(state.signals || []);
    initPieChart(state.portfolio.positions || {}, state.portfolio.cash);

    renderKPIs(state.portfolio);
    renderIndices(state.market_overview || {});
    renderRisk(state);
    renderWeights(state.dimension_weights || {technical:0.3, sentiment:0.25, capital_flow:0.25, fundamental:0.2});
    renderSignals(state.signals || []);
    renderDecisions(state.decisions || []);
    renderPositions(state.portfolio.positions || {}, state.portfolio.cash, state.portfolio.total_assets);
    renderOrders(state.executed_orders || []);
    renderSectors(state.sector_rotation || {});
    renderFlags(state.risk_flags || []);
    renderLogs(state.logs || []);
    renderEvolution(state.memory || {}, state.iteration_count || 0);
  } catch(e) {
    console.error('Init failed:', e);
  }

  // SSE live feed
  const sse = new EventSource('/stream');
  sse.onmessage = e => {
    try {
      const d = JSON.parse(e.data);
      if(d.total_assets != null) {
        document.getElementById('kpi-total').textContent = fmt(d.total_assets);
        const kd = document.getElementById('kpi-daily');
        if(kd) { kd.className='card-val '+(d.daily_pnl>=0?'up':'dn'); kd.textContent=(d.daily_pnl>=0?'+':'')+fmt(d.daily_pnl); }
      }
      if(d.risk_level) {
        document.getElementById('risk-dot').className = 'risk-dot risk-'+d.risk_level;
        document.getElementById('risk-label').textContent = d.risk_level.toUpperCase();
      }
      if(d.iteration_count != null) {
        document.getElementById('iter-counter').textContent = 'Iter '+d.iteration_count+'/20';
        document.getElementById('perf-iter').textContent = d.iteration_count;
      }
      if(d.indices) {
        const ids = Object.values(d.indices);
        ['idx-0','idx-1','idx-2','idx-3'].forEach((pfx,i) => {
          if(!ids[i]) return;
          const pr = document.getElementById(pfx+'-price');
          const ch = document.getElementById(pfx+'-chg');
          if(pr) pr.textContent = ids[i].price.toLocaleString('zh-CN');
          if(ch) { ch.textContent=(ids[i].change_pct>=0?'+':'')+ids[i].change_pct.toFixed(2)+'%'; ch.className='idx-chg '+(ids[i].change_pct>=0?'up':'dn'); }
        });
      }
      if(d.positions) {
        const rows = document.querySelectorAll('#pos-tbl tbody tr');
        const entries = Object.entries(d.positions);
        rows.forEach((row,i) => {
          if(!entries[i]) return;
          const pos = entries[i][1];
          const cells = row.querySelectorAll('td');
          if(cells[4]) cells[4].textContent = Number(pos.current_price).toFixed(2);
          if(cells[5]) { cells[5].textContent=pct(pos.pnl_pct); cells[5].className='mono '+(pos.pnl_pct>=0?'up':'dn'); }
          if(cells[6]) cells[6].textContent = fmt(pos.market_value);
        });
        // Update rt-positions panel
        const rtPos = document.getElementById('rt-positions');
        if(rtPos) rtPos.innerHTML = entries.map(([sym,pos]) => {
          const c = pos.pnl_pct>=0?'var(--green)':'var(--red)';
          return `<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border)">
            <span style="font-family:monospace;font-size:11px;color:var(--text1)">${sym}</span>
            <span style="font-family:monospace;font-size:11px;color:${c};font-weight:700">${pct(pos.pnl_pct)}</span>
          </div>`;
        }).join('');
      }
    } catch(err) { console.warn('SSE parse error', err); }
  };
  sse.onerror = () => {
    const el = document.getElementById('sb-conn');
    if(el) { el.textContent='SSE 重连中...'; el.style.color='var(--yellow)'; }
  };
  sse.onopen = () => {
    const el = document.getElementById('sb-conn');
    if(el) { el.textContent='SSE 已连接'; el.style.color=''; }
  };

  // Refresh heavy data every 15s
  setInterval(async () => {
    try {
      const [port, sigs, decs, orders] = await Promise.all([
        fetch('/api/portfolio').then(r=>r.json()),
        fetch('/api/signals').then(r=>r.json()),
        fetch('/api/decisions').then(r=>r.json()),
        fetch('/api/orders').then(r=>r.json()),
      ]);
      renderKPIs(port);
      renderPositions(port.positions||{}, port.cash, port.total_assets);
      renderSignals(sigs);
      renderDecisions(decs);
      renderOrders(orders);
      if(pieChart) {
        const palette=['#00d4ff','#7c5cfc','#00e676','#ffc107','#ff9100','#ff4d6d','#e040fb'];
        const lbs=[], vals=[], cols=[];
        let ci=0;
        for(const [sym,pos] of Object.entries(port.positions||{})) {
          lbs.push(pos.name||sym); vals.push(pos.market_value); cols.push(palette[ci++%palette.length]);
        }
        lbs.push('现金'); vals.push(port.cash); cols.push('#232c3a');
        pieChart.data.labels=lbs;
        pieChart.data.datasets[0].data=vals;
        pieChart.data.datasets[0].backgroundColor=cols;
        pieChart.update('none');
      }
    } catch(e){ console.warn('Refresh error', e); }
  }, 15000);
}

document.addEventListener('DOMContentLoaded', init);
