<template>
  <div id="app">
    <!-- TOP BAR -->
    <div class="topbar">
      <span class="logo">MORE MONEY</span>
      <div class="tbdiv"></div>
      <span :class="'top-badge badge-' + (state.kill_switch_state==='NORMAL'?'paper':'live')">
        {{ state.kill_switch_state }}
      </span>
      <div class="tbdiv"></div>
      <div class="tm"><div class="tm-lbl">PHASE</div><div class="tm-val">{{ state.trading_phase }}</div></div>
      <div class="tbdiv"></div>
      <div class="tm"><div class="tm-lbl">ITER</div><div class="tm-val">{{ state.iteration_count }}/{{ state.max_iterations }}</div></div>
      <div class="top-sep"></div>
      <div class="sse-row">
        <div :class="'sse-dot'+(sseOk?'':' err')"></div>
        <span>{{ sseOk ? 'LIVE' : 'DISCONNECTED' }}</span>
      </div>
      <span class="top-clock">{{ clock || '--:--:--' }}</span>
    </div>

    <!-- BODY -->
    <div class="body-grid">
      <!-- SIDENAV -->
      <nav class="sidenav">
        <div class="ng-lbl">监控</div>
        <button v-for="item in navItems" :key="item.id"
          :class="'nav-btn'+(activeNav===item.id?' active':'')"
          @click="activeNav=item.id; activeTab=item.id">
          <span class="nav-icon">{{ item.icon }}</span>{{ item.label }}
        </button>
        <div class="nav-footer">
          <div class="risk-pill">
            <div :class="'rpulse rl-'+state.risk_level"></div>
            <div style="flex:1">
              <div style="font-size:9px;color:var(--t2);text-transform:uppercase">风险</div>
              <div style="font-size:12px;font-weight:600">{{ state.risk_level.toUpperCase() }}</div>
            </div>
          </div>
        </div>
      </nav>

      <!-- CENTER -->
      <div class="center">
        <div class="tabbar">
          <button v-for="item in tabItems" :key="item.id"
            :class="'tab-btn'+(activeTab===item.id?' active':'')"
            @click="activeTab=item.id; activeNav=item.id">
            {{ item.label }}
          </button>
        </div>
        <div class="panels">
          <PanelOverview    v-if="activeTab==='overview'"    :s="state" :fmt="fmt" :fmtPnl="fmtPnl" :pct="pct" :clr="clr" />
          <PanelMarket      v-if="activeTab==='market'"      :s="state" :fmt="fmt" :pct="pct" :clr="clr" />
          <PanelRegime      v-if="activeTab==='regime'"      :s="state" :pct="pct" />
          <PanelSignals     v-if="activeTab==='signals'"     :s="state" :pct="pct" />
          <PanelDecisions   v-if="activeTab==='decisions'"   :s="state" :pct="pct" />
          <PanelCapital     v-if="activeTab==='capital'"     :s="state" :fmt="fmt" />
          <PanelPositions   v-if="activeTab==='positions'"   :s="state" :fmt="fmt" :pct="pct" :clr="clr" />
          <PanelOrders      v-if="activeTab==='orders'"      :s="state" :fmt="fmt" />
          <PanelWatchlist   v-if="activeTab==='watchlist'"   :s="state" :fmt="fmt" :pct="pct" :clr="clr" :wlDelete="wlDelete" :wlAdd="wlAdd" />
          <PanelAgents      v-if="activeTab==='agents'"      :s="state" />
          <PanelRisk        v-if="activeTab==='risk'"        :s="state" :pct="pct" />
          <PanelControl     v-if="activeTab==='control'"     :s="state" :killSwitch="killSwitch" />
          <PanelLogs        v-if="activeTab==='logs'"        :s="state" />
        </div>
        <div class="statusbar">
          <span>SESSION: {{ state.session_id }}</span>
          <span style="color:var(--border2)">|</span>
          <span>资产: <span :class="clr(state.portfolio.daily_pnl)">¥{{ fmt(state.portfolio.total_assets,0) }}</span></span>
          <span style="color:var(--border2)">|</span>
          <span>日盈亏: <span :class="clr(state.portfolio.daily_pnl)">{{ fmtPnl(state.portfolio.daily_pnl) }}</span></span>
          <span style="color:var(--border2)">|</span>
          <span>持仓: {{ Object.keys(state.portfolio.positions||{}).length }} 只</span>
          <span style="color:var(--border2)">|</span>
          <span>信号: {{ (state.signals||[]).length }}</span>
        </div>
      </div>

      <!-- RIGHT RAIL -->
      <div class="right-rail">
        <div class="rr-tabs">
          <button v-for="rt in rrTabs" :key="rt.id"
            :class="'rr-tab'+(activeRR===rt.id?' active':'')"
            @click="activeRR=rt.id">{{ rt.label }}</button>
        </div>
        <div class="rr-body">
          <RRSignals   v-if="activeRR==='signals'"   :s="state" :pct="pct" />
          <RRPositions v-if="activeRR==='positions'" :s="state" :fmt="fmt" :pct="pct" :clr="clr" />
          <RRAgents    v-if="activeRR==='agents'"    :s="state" />
          <RRAlerts    v-if="activeRR==='alerts'"    :s="state" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useStore } from './composables/useStore.js'
import PanelOverview  from './components/PanelOverview.vue'
import PanelMarket    from './components/PanelMarket.vue'
import PanelRegime    from './components/PanelRegime.vue'
import PanelSignals   from './components/PanelSignals.vue'
import PanelDecisions from './components/PanelDecisions.vue'
import PanelCapital   from './components/PanelCapital.vue'
import PanelPositions from './components/PanelPositions.vue'
import PanelOrders    from './components/PanelOrders.vue'
import PanelWatchlist from './components/PanelWatchlist.vue'
import PanelAgents    from './components/PanelAgents.vue'
import PanelRisk      from './components/PanelRisk.vue'
import PanelControl   from './components/PanelControl.vue'
import PanelLogs      from './components/PanelLogs.vue'
import RRSignals   from './components/RRSignals.vue'
import RRPositions from './components/RRPositions.vue'
import RRAgents    from './components/RRAgents.vue'
import RRAlerts    from './components/RRAlerts.vue'

const { state, sseOk, clock, fmt, fmtPnl, pct, clr, killSwitch, wlDelete, wlAdd } = useStore()

const activeNav = ref('overview')
const activeTab = ref('overview')
const activeRR  = ref('signals')

const navItems = [
  {id:'overview',  icon:'📊', label:'总览'},
  {id:'market',    icon:'📈', label:'行情'},
  {id:'regime',    icon:'🧭', label:'市场机制'},
  {id:'signals',   icon:'⚡', label:'信号矩阵'},
  {id:'decisions', icon:'🎯', label:'决策引擎'},
  {id:'capital',   icon:'💰', label:'资金流向'},
  {id:'positions', icon:'📦', label:'持仓管理'},
  {id:'orders',    icon:'📋', label:'成交记录'},
  {id:'watchlist', icon:'👁', label:'每日优选'},
  {id:'agents',    icon:'🤖', label:'Agent状态'},
  {id:'risk',      icon:'🛡', label:'风控参数'},
  {id:'control',   icon:'🚨', label:'控制面板'},
  {id:'logs',      icon:'📝', label:'系统日志'},
]
const tabItems = navItems
const rrTabs = [
  {id:'signals',   label:'信号流'},
  {id:'positions', label:'持仓盈亏'},
  {id:'agents',    label:'Agent'},
  {id:'alerts',    label:'预警'},
]
</script>
