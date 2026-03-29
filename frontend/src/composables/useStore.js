import { ref, reactive, onMounted, onUnmounted } from 'vue'

const state = reactive({
  // portfolio
  portfolio: { total_assets: 0, cash: 0, daily_pnl: 0, total_pnl: 0, max_drawdown: 0, win_rate: 0, sharpe_ratio: 0, positions: {} },
  // market
  market_overview: {},
  sector_rotation: {},
  market_regime: { regime: 'unknown', confidence: 0, base_weights: {}, signals: {} },
  capital_flow: { northbound: {}, main_force: {}, sector_flow: {} },
  // trading
  signals: [],
  decisions: [],
  executed_orders: [],
  daily_watchlist: [],
  // agents & system
  agent_status: {},
  kill_switch_state: 'NORMAL',
  kill_switch_history: [],
  risk_level: 'medium',
  risk_flags: [],
  dynamic_position: {},
  risk_params: {},
  dimension_weights: {},
  // memory / evolution
  memory: { learned_rules: [], successful_patterns: [], failed_patterns: [] },
  // misc
  logs: [],
  equity_curve: [],
  trading_phase: 'morning',
  iteration_count: 0,
  max_iterations: 20,
  market_sentiment: 'neutral',
  session_id: '',
})

const sseOk = ref(false)
const clock = ref('')
const loading = ref(true)

async function fetchAll() {
  try {
    const [st, eq] = await Promise.all([
      fetch('/api/state').then(r => r.json()),
      fetch('/api/equity_curve').then(r => r.json()),
    ])
    Object.assign(state, st)
    state.equity_curve = eq
    loading.value = false
  } catch(e) { console.error('fetchAll', e) }
}

function startSSE() {
  const es = new EventSource('/stream')
  es.onopen = () => { sseOk.value = true }
  es.onerror = () => { sseOk.value = false }
  es.onmessage = (e) => {
    try {
      const d = JSON.parse(e.data)
      sseOk.value = true
      if (d.total_assets) state.portfolio.total_assets = d.total_assets
      if (d.daily_pnl !== undefined) state.portfolio.daily_pnl = d.daily_pnl
      if (d.total_pnl !== undefined) state.portfolio.total_pnl = d.total_pnl
      if (d.risk_level) state.risk_level = d.risk_level
      if (d.kill_switch_state) state.kill_switch_state = d.kill_switch_state
      if (d.market_sentiment) state.market_sentiment = d.market_sentiment
      if (d.iteration_count !== undefined) state.iteration_count = d.iteration_count
      if (d.agent_status) Object.assign(state.agent_status, Object.fromEntries(
        Object.entries(d.agent_status).map(([k,v]) => [k, {...(state.agent_status[k]||{}), status: v}])
      ))
      if (d.indices) Object.entries(d.indices).forEach(([k,v]) => {
        if (state.market_overview[k]) Object.assign(state.market_overview[k], v)
      })
      if (d.positions) Object.entries(d.positions).forEach(([k,v]) => {
        if (state.portfolio.positions[k]) Object.assign(state.portfolio.positions[k], v)
      })
      if (d.northbound_today !== undefined) state.capital_flow.northbound.today_net = d.northbound_today
      if (d.main_force_net !== undefined) state.capital_flow.main_force.net_inflow = d.main_force_net
      if (d.ts) clock.value = d.ts
    } catch(e) { console.error('SSE parse', e) }
  }
  return es
}

let _es = null
export function useStore() {
  onMounted(async () => {
    await fetchAll()
    _es = startSSE()
    setInterval(fetchAll, 15000)
  })
  onUnmounted(() => { if (_es) _es.close() })

  // helpers
  const fmt = (v, d=0) => typeof v === 'number' ? v.toLocaleString('zh-CN', {minimumFractionDigits:d, maximumFractionDigits:d}) : '--'
  const fmtPnl = (v) => (v >= 0 ? '+' : '') + fmt(v, 2)
  const pct = (v, d=2) => typeof v === 'number' ? (v*100).toFixed(d)+'%' : '--'
  const clr = (v) => v > 0 ? 'up' : v < 0 ? 'dn' : 'neu'
  const clrPct = (v) => v > 0 ? 'up' : v < 0 ? 'dn' : 'neu'

  async function killSwitch(action) {
    await fetch(`/api/kill_switch/${action}`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({reason:'web panel'})})
    await fetchAll()
  }
  async function wlDelete(code) {
    await fetch(`/api/watchlist/${code}`, {method:'DELETE'})
    state.daily_watchlist = state.daily_watchlist.filter(s => s.code !== code)
  }
  async function wlAdd(payload) {
    const r = await fetch('/api/watchlist', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)})
    if (r.ok) { const item = await r.json(); state.daily_watchlist.push(item) }
    return r.ok
  }
  async function refetch() { await fetchAll() }

  return { state, sseOk, clock, loading, fmt, fmtPnl, pct, clr, clrPct, killSwitch, wlDelete, wlAdd, refetch }
}
