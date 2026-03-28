// MoreMoney Dashboard JS

// NAV — 挂到 window 供 HTML onclick 调用
window.showTab = function(id) {
  document.querySelectorAll('.panel').forEach(function(p) { p.classList.remove('active'); });
  document.querySelectorAll('.nav-item').forEach(function(n) { n.classList.remove('active'); });
  var panel = document.getElementById('panel-' + id);
  if (panel) panel.classList.add('active');
  if (window.event && window.event.currentTarget) window.event.currentTarget.classList.add('active');
};

// CHARTS
let equityChart, radarChart, pieChart;

function initEquityChart(data) {
  const ctx = document.getElementById('equity-chart').getContext('2d');
  const grad = ctx.createLinearGradient(0,0,0,180);
  grad.addColorStop(0,'rgba(0,212,255,0.25)');
  grad.addColorStop(1,'rgba(0,212,255,0.0)');
  equityChart = new Chart(ctx, {
    type:'line',
    data:{ labels:data.map(d=>d.date), datasets:[{ data:data.map(d=>d.value),
      borderColor:'#00d4ff', borderWidth:2, backgroundColor:grad,
      fill:true, tension:0.4, pointRadius:0 }] },
    options:{ responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{ display:false } },
      scales:{
        x:{ grid:{ color:'#1c2330' }, ticks:{ color:'#5a6a7e', font:{ size:10 } } },
        y:{ grid:{ color:'#1c2330' }, ticks:{ color:'#5a6a7e', font:{ size:10 },
          callback: v => '¥'+(v/1e6).toFixed(3)+'M' } } } }
  });
}

function initRadarChart(signals) {
  const ctx = document.getElementById('signal-radar').getContext('2d');
  const dims = ['technical','capital_flow','sentiment','fundamental'];
  const dimNames = {technical:'技术面',capital_flow:'资金面',sentiment:'消息面',fundamental:'基本面'};
  const bull={}, bear={};
  dims.forEach(d=>{ bull[d]=0; bear[d]=0; });
  signals.forEach(s=>{
    if(s.direction==='bullish') bull[s.dimension]=Math.max(bull[s.dimension]||0,s.strength);
    else if(s.direction==='bearish') bear[s.dimension]=Math.max(bear[s.dimension]||0,s.strength);
  });
  radarChart = new Chart(ctx, {
    type:'radar',
    data:{ labels:dims.map(d=>dimNames[d]), datasets:[
      { label:'多头强度', data:dims.map(d=>bull[d]*100), borderColor:'#00e676',
        backgroundColor:'rgba(0,230,118,0.15)', pointBackgroundColor:'#00e676', pointRadius:4 },
      { label:'空头强度', data:dims.map(d=>bear[d]*100), borderColor:'#ff4d6d',
        backgroundColor:'rgba(255,77,109,0.12)', pointBackgroundColor:'#ff4d6d', pointRadius:4 }
    ]},
    options:{ responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{ labels:{ color:'#a8b4c4', font:{ size:11 } } } },
      scales:{ r:{ min:0, max:100, grid:{ color:'#1c2330' }, angleLines:{ color:'#232c3a' },
        ticks:{ color:'#5a6a7e', backdropColor:'transparent', font:{ size:10 } },
        pointLabels:{ color:'#a8b4c4', font:{ size:11 } } } } }
  });
}

function initPieChart(positions, cash) {
  const ctx = document.getElementById('pos-pie').getContext('2d');
  const palette=['#00d4ff','#7c5cfc','#00e676','#ffc107','#ff9100','#ff4d6d','#e040fb'];
  const labels=[],values=[],colors=[];
  let i=0;
  for(const [sym,pos] of Object.entries(positions)) {
    labels.push(pos.name||sym); values.push(pos.market_value); colors.push(palette[i++%palette.length]);
  }
  labels.push('现金'); values.push(cash); colors.push('#232c3a');
  pieChart = new Chart(ctx,{
    type:'doughnut',
    data:{ labels, datasets:[{ data:values, backgroundColor:colors,
      borderColor:'#0f1318', borderWidth:2, hoverOffset:6 }] },
    options:{ responsive:true, maintainAspectRatio:false, cutout:'65%',
      plugins:{ legend:{ position:'right',
        labels:{ color:'#a8b4c4', font:{ size:11 }, boxWidth:12, padding:10 } } } }
  });
}

// HELPERS
window.fmt=function(n){return '¥'+Number(n).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});};
window.pct=function(n){return(n>=0?'+':'')+(Number(n)*100).toFixed(2)+'%';};
window.clr=function(n){return n>=0?'up':'dn';};
var fmt=window.fmt,pct=window.pct,clr=window.clr;

// RENDER KPIs
function renderKPIs(p) {
  document.getElementById('kpi-total').textContent = fmt(p.total_assets);
  const kd=document.getElementById('kpi-daily');
  kd.className='card-val '+clr(p.daily_pnl);
  kd.textContent=(p.daily_pnl>=0?'+':'')+fmt(p.daily_pnl);
  document.getElementById('kpi-daily-pct').textContent=pct(p.daily_pnl/(p.total_assets-p.daily_pnl||1));
  const tp=document.getElementById('kpi-total-pnl');
  tp.className='card-val '+clr(p.total_pnl);
  tp.textContent=(p.total_pnl>=0?'+':'')+fmt(p.total_pnl);
  document.getElementById('kpi-total-pnl-pct').textContent=pct(p.total_pnl/1000000);
  document.getElementById('kpi-cash').textContent=fmt(p.cash);
  document.getElementById('kpi-cash-pct').textContent=((p.total_assets-p.cash)/p.total_assets*100).toFixed(1)+'% 仓位';
  document.getElementById('perf-wr').textContent=(p.win_rate*100).toFixed(1)+'%';
  document.getElementById('perf-sr').textContent=p.sharpe_ratio.toFixed(2);
  const dd=document.getElementById('perf-dd');
  dd.className='card-val dn'; dd.textContent='-'+(p.max_drawdown*100).toFixed(2)+'%';
}

function renderIndices(ov) {
  const ids=Object.values(ov);
  ['idx-0','idx-1','idx-2','idx-3'].forEach((pfx,i)=>{
    if(!ids[i]) return;
    document.getElementById(pfx+'-price').textContent=ids[i].price.toLocaleString('zh-CN');
    const el=document.getElementById(pfx+'-chg');
    el.textContent=(ids[i].change_pct>=0?'+':'')+ids[i].change_pct.toFixed(2)+'%';
    el.className='idx-chg '+clr(ids[i].change_pct);
  });
}

function renderRisk(s) {
  const rl=s.risk_level||'medium';
  document.getElementById('risk-dot').className='risk-dot risk-'+rl;
  document.getElementById('risk-label').textContent=rl.toUpperCase();
  const sm={fear:'恐慌',neutral:'中性',greed:'贪婪'};
  document.getElementById('sentiment-label').textContent=sm[s.market_sentiment]||s.market_sentiment;
  document.getElementById('iter-counter').textContent='Iter '+s.iteration_count+'/'+s.max_iterations;
  document.getElementById('perf-iter').textContent=s.iteration_count;
  document.getElementById('sb-session').textContent='session '+(s.session_id||'').slice(-13);
}

function renderWeights(w) {
  const m={tech:w.technical,sent:w.sentiment,cap:w.capital_flow,fund:w.fundamental};
  for(const [k,v] of Object.entries(m)) {
    document.getElementById('wt-'+k).style.width=(v*100)+'%';
    document.getElementById('wt-'+k+'-v').textContent=(v*100).toFixed(0)+'%';
  }
}

function renderSignals(signals) {
  const dimMap={technical:'技术面',capital_flow:'资金面',sentiment:'消息面',fundamental:'基本面'};
  document.getElementById('signal-list').innerHTML=signals.map(s=>{
    const dc=s.direction==='bullish'?'dir-bullish':s.direction==='bearish'?'dir-bearish':'dir-neutral';
    const bc=s.direction==='bullish'?'bar-bull':s.direction==='bearish'?'bar-bear':'bar-neu';
    const dt=s.direction==='bullish'?'多 ↑':s.direction==='bearish'?'空 ↓':'中性';
    return `<div class="sig-row" title="${s.reasoning}">
      <span class="sig-sym">${s.symbol}</span>
      <span class="sig-dim">${dimMap[s.dimension]||s.dimension}</span>
      <span class="sig-dir ${dc}">${dt}</span>
      <div class="bar-wrap"><div class="bar-fill ${bc}" style="width:${(s.strength*100).toFixed(0)}%"></div></div>
      <span class="sig-val">${(s.strength*100).toFixed(0)}</span>
    </div>`;
  }).join('');
  document.getElementById('rt-signals').innerHTML=signals.slice(0,6).map(s=>{
    const c=s.direction==='bullish'?'var(--green)':s.direction==='bearish'?'var(--red)':'var(--text2)';
    return `<div style="display:flex;gap:6px;align-items:center;padding:5px 0;border-bottom:1px solid var(--border)">
      <span style="font-family:monospace;font-size:11px;color:var(--text2);width:54px">${s.symbol}</span>
      <span style="font-size:10px;color:${c};width:44px;font-weight:700">${s.direction==='bullish'?'多↑':s.direction==='bearish'?'空↓':'中性'}</span>
      <div style="flex:1;height:4px;background:var(--bg3);border-radius:2px;overflow:hidden"><div style="height:100%;background:${c};width:${(s.strength*100).toFixed(0)}%"></div></div>
    </div>`;
  }).join('');
}

function renderDecisions(decisions) {
  const urgMap={immediate:'立即',normal:'普通',passive:'被动'};
  const actMap={buy:'买入',sell:'卖出',hold:'持有',reduce:'减仓',add:'加仓'};
  document.querySelector('#decision-tbl tbody').innerHTML=decisions.map(d=>{
    const rs=d.risk_score;
    const rc=rs>0.6?'var(--red)':rs>0.3?'var(--yellow)':'var(--green)';
    return `<tr>
      <td class="mono">${d.symbol}</td>
      <td><span class="act act-${d.action}">${actMap[d.action]||d.action}</span></td>
      <td class="mono">${(d.current_position*100).toFixed(1)}%</td>
      <td class="mono">${(d.target_position*100).toFixed(1)}%</td>
      <td class="mono dn">${d.stop_loss.toFixed(2)}</td>
      <td class="mono up">${d.take_profit.toFixed(2)}</td>
      <td style="color:${d.urgency==='immediate'?'var(--red)':d.urgency==='normal'?'var(--yellow)':'var(--text2)'}">${urgMap[d.urgency]||d.urgency}</td>
      <td><div style="width:48px;height:5px;background:var(--bg3);border-radius:3px;overflow:hidden"><div style="height:100%;background:${rc};width:${(rs*100).toFixed(0)}%"></div></div></td>
      <td style="font-size:11px;color:var(--text2);max-width:180px">${d.reasoning}</td>
    </tr>`;
  }).join('');
}

function renderPositions(positions, cash, total) {
  document.querySelector('#pos-tbl tbody').innerHTML=Object.entries(positions).map(([sym,pos])=>`<tr>
    <td><span class="mono" style="color:var(--accent)">${sym}</span> <span style="font-size:11px;color:var(--text2)">${pos.name||''}</span></td>
    <td style="font-size:11px;color:var(--text2)">${pos.sector||'-'}</td>
    <td class="mono">${pos.qty}</td>
    <td class="mono">${Number(pos.cost).toFixed(2)}</td>
    <td class="mono">${Number(pos.current_price).toFixed(2)}</td>
    <td class="mono ${clr(pos.pnl_pct)}">${pct(pos.pnl_pct)}</td>
    <td class="mono">${fmt(pos.market_value)}</td>
  </tr>`).join('');

  document.getElementById('pos-gauges').innerHTML=Object.entries(positions).map(([sym,pos])=>{
    const w=(pos.market_value/total*100).toFixed(1);
    const c=pos.pnl_pct>=0?'var(--green)':'var(--red)';
    return `<div class="gauge-row">
      <span class="gauge-label mono">${sym}</span>
      <div class="gauge-bar"><div class="gauge-fill" style="width:${w}%;background:${c}"></div></div>
      <span class="gauge-pct">${w}%</span>
    </div>`;
  }).join('');

  document.getElementById('rt-positions').innerHTML=Object.entries(positions).map(([sym,pos])=>{
    const c=pos.pnl_pct>=0?'var(--green)':'var(--red)';
    return `<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border)">
      <span style="font-family:monospace;font-size:11px;color:var(--text1)">${sym} ${pos.name||''}</span>
      <span style="font-family:monospace;font-size:11px;color:${c};font-weight:700">${pct(pos.pnl_pct)}</span>
    </div>`;
  }).join('');
}

function renderOrders(orders) {
  const actMap={buy:'买入',sell:'卖出'};
  const stMap={filled:'已成交',partial:'部分成交',rejected:'已拒绝'};
  document.querySelector('#orders-tbl tbody').innerHTML=orders.map(o=>`<tr>
    <td class="mono" style="color:var(--text2)">${o.time||'--'}</td>
    <td class="mono">${o.symbol}</td>
    <td><span class="act act-${o.action}">${actMap[o.action]||o.action}</span></td>
    <td class="mono">${o.quantity}</td>
    <td class="mono">${Number(o.filled_price).toFixed(2)}</td>
    <td class="mono">${fmt(o.amount)}</td>
    <td><span class="act act-${o.status}">${stMap[o.status]||o.status}</span></td>
  </tr>`).join('');
}


function renderSectors(sectors) {
  var cells=Object.entries(sectors).sort(function(a,b){return b[1]-a[1];});
  var hm=document.getElementById('sector-heatmap');
  if(hm) hm.innerHTML=cells.map(function(entry){
    var name=entry[0],chg=entry[1];
    var abs=Math.min(Math.abs(chg)/4,1);
    var bg=chg>=0?'rgba(0,230,118,'+(0.15+abs*0.5).toFixed(2)+')':'rgba(255,77,109,'+(0.15+abs*0.5).toFixed(2)+')';
    var col=chg>=0?'#00e676':'#ff4d6d';
    return '<div class="sector-cell" style="background:'+bg+';color:'+col+'">'+name+'<br>'+(chg>=0?'+':'')+chg.toFixed(2)+'%</div>';
  }).join('');
  var tb=document.querySelector('#sector-tbl tbody');
  if(tb) tb.innerHTML=cells.map(function(entry){
    var name=entry[0],chg=entry[1];
    return '<tr><td>'+name+'</td>'
      +'<td class="mono '+(chg>=0?'up':'dn')+'">'+(chg>=0?'+':'')+chg.toFixed(2)+'%</td>'
      +'<td><div style="width:'+Math.min(Math.abs(chg)/4*100,100).toFixed(0)+'%;height:4px;background:'+(chg>=0?'var(--green)':'var(--red)')+';border-radius:2px"></div></td></tr>';
  }).join('');
}
