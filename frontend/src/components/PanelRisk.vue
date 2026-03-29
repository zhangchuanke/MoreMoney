<template>
  <div class="panel active">
    <div class="sec">动态仓位参数</div>
    <div class="card" style="margin-bottom:12px">
      <div v-for="(v,k) in dynParams" :key="k" class="gauge-row">
        <div class="gauge-lbl">{{ dynLabel(k) }}</div>
        <div class="gauge-bar"><div class="gauge-fill" :style="{width:Math.min(v*100,100)+'%',background:'var(--acc2)'}"></div></div>
        <div class="gauge-pct">{{ pct(v) }}</div>
      </div>
    </div>
    <div class="sec">风控参数</div>
    <table class="tbl">
      <thead><tr><th>参数</th><th>值</th></tr></thead>
      <tbody>
        <tr v-for="(v,k) in s.risk_params" :key="k">
          <td style="color:var(--t2)">{{ k }}</td>
          <td class="mono">{{ typeof v==='number' && v<1 && v>0 ? pct(v) : v }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps(['s','pct'])
const { s, pct } = props
const dynParams = computed(() => {
  const dp = s.dynamic_position || {}
  return {
    max_single_position_pct: dp.max_single_position_pct,
    max_sector_pct: dp.max_sector_pct,
    max_total_position_pct: dp.max_total_position_pct,
    stop_loss_pct: dp.stop_loss_pct,
    take_profit_pct: dp.take_profit_pct,
    trailing_stop_pct: dp.trailing_stop_pct,
  }
})
const dynLabel = k => ({'max_single_position_pct':'单票上限','max_sector_pct':'板块上限','max_total_position_pct':'总仓上限','stop_loss_pct':'止损线','take_profit_pct':'止盈线','trailing_stop_pct':'追踪止损'}[k]||k)
</script>
