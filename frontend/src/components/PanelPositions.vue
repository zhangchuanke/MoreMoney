<template>
  <div class="panel active">
    <div class="sec">持仓明细</div>
    <div v-if="!positions.length" style="color:var(--t2);text-align:center;padding:24px">暂无持仓</div>
    <div class="g3">
      <div v-for="[sym,pos] in positions" :key="sym" :class="'pos-card '+(pos.pnl_pct>=0?'pos-card-up':'pos-card-dn')">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
          <div><div class="mono" style="font-size:13px;font-weight:700">{{ sym }}</div><div style="font-size:10px;color:var(--t2)">{{ pos.name }}</div></div>
          <div :class="pos.pnl_pct>=0?'up':'dn'" style="font-family:var(--mono);font-size:14px;font-weight:700">{{ (pos.pnl_pct>=0?'+':'')+pct(pos.pnl_pct) }}</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:11px">
          <div><span style="color:var(--t2)">现价 </span><span class="mono">{{ pos.current_price }}</span></div>
          <div><span style="color:var(--t2)">成本 </span><span class="mono">{{ pos.cost }}</span></div>
          <div><span style="color:var(--t2)">市值 </span><span class="mono">¥{{ fmt(pos.market_value,0) }}</span></div>
          <div><span style="color:var(--t2)">数量 </span><span class="mono">{{ pos.qty }}</span></div>
          <div><span style="color:var(--t2)">止损 </span><span class="mono" style="color:#ff3d6b">{{ pos.stop_loss }}</span></div>
          <div><span style="color:var(--t2)">止盈 </span><span class="mono" style="color:#00e5a0">{{ pos.take_profit }}</span></div>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps(['s','fmt','pct','clr'])
const { s, fmt, pct, clr } = props
const positions = computed(() => Object.entries(s.portfolio.positions||{}))
</script>
