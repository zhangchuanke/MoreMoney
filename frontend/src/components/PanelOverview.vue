<template>
  <div class="panel active">
    <!-- KPI row -->
    <div class="g4" style="margin-bottom:12px">
      <div class="card">
        <div class="card-title">总资产</div>
        <div class="card-val">¥{{ fmt(s.portfolio.total_assets,0) }}</div>
        <div class="card-sub" :class="clr(s.portfolio.total_pnl)">总盈亏 {{ fmtPnl(s.portfolio.total_pnl) }}</div>
      </div>
      <div class="card">
        <div class="card-title">日盈亏</div>
        <div class="card-val" :class="clr(s.portfolio.daily_pnl)">{{ fmtPnl(s.portfolio.daily_pnl) }}</div>
        <div class="card-sub">可用现金 ¥{{ fmt(s.portfolio.cash,0) }}</div>
      </div>
      <div class="card">
        <div class="card-title">胜率</div>
        <div class="card-val">{{ pct(s.portfolio.win_rate) }}</div>
        <div class="card-sub">{{ s.portfolio.win_trades }}胜 / {{ s.portfolio.loss_trades }}负</div>
      </div>
      <div class="card">
        <div class="card-title">Sharpe</div>
        <div class="card-val">{{ (s.portfolio.sharpe_ratio||0).toFixed(2) }}</div>
        <div class="card-sub">最大回撤 {{ pct(s.portfolio.max_drawdown) }}</div>
      </div>
    </div>
    <div class="g4" style="margin-bottom:12px">
      <div class="card">
        <div class="card-title">Sortino</div>
        <div class="card-val">{{ (s.portfolio.sortino_ratio||0).toFixed(2) }}</div>
      </div>
      <div class="card">
        <div class="card-title">Calmar</div>
        <div class="card-val">{{ (s.portfolio.calmar_ratio||0).toFixed(2) }}</div>
      </div>
      <div class="card">
        <div class="card-title">盈亏比</div>
        <div class="card-val">{{ (s.portfolio.profit_factor||0).toFixed(2) }}</div>
      </div>
      <div class="card">
        <div class="card-title">总交易</div>
        <div class="card-val">{{ s.portfolio.total_trades||0 }}</div>
      </div>
    </div>
    <!-- dimension weights -->
    <div class="sec">四维权重</div>
    <div class="card" style="margin-bottom:12px">
      <div v-for="(v,k) in s.dimension_weights" :key="k" class="gauge-row">
        <div class="gauge-lbl">{{ dimLabel(k) }}</div>
        <div class="gauge-bar"><div class="gauge-fill" :style="{width:pct(v),background:'var(--acc)'}"></div></div>
        <div class="gauge-pct">{{ pct(v) }}</div>
      </div>
    </div>
    <!-- risk flags -->
    <div v-if="(s.risk_flags||[]).length" class="sec">风险预警</div>
    <div v-for="f in s.risk_flags" :key="f" class="flag-item">
      <span class="flag-icon">⚠</span>{{ f }}
    </div>
  </div>
</template>
<script setup>
const props = defineProps(['s','fmt','fmtPnl','pct','clr'])
const { s, fmt, fmtPnl, pct, clr } = props
const dimLabel = k => ({'technical':'技术面','sentiment':'情绪面','capital_flow':'资金面','fundamental':'基本面'}[k]||k)
</script>
