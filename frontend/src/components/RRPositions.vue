<template>
  <div>
    <div style="font-size:9px;color:var(--t2);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px">持仓盈亏</div>
    <div v-if="!positions.length" style="color:var(--t2);font-size:11px;text-align:center;padding:16px">暂无持仓</div>
    <div v-for="[sym,pos] in positions" :key="sym" style="display:flex;align-items:center;gap:6px;padding:6px 0;border-bottom:1px solid rgba(30,45,61,.7)">
      <div style="width:52px;font-family:var(--mono);font-size:11px;color:var(--t1)">{{ sym }}</div>
      <div style="flex:1">
        <div style="font-size:10px;color:var(--t2)">{{ pos.name }}</div>
        <div style="font-family:var(--mono);font-size:11px">¥{{ pos.current_price }}</div>
      </div>
      <div :class="pos.pnl_pct>=0?'up':'dn'" style="font-family:var(--mono);font-size:12px;font-weight:700">
        {{ (pos.pnl_pct>=0?'+':'')+pct(pos.pnl_pct) }}
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
