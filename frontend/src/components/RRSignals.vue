<template>
  <div>
    <div style="font-size:9px;color:var(--t2);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px">实时信号流</div>
    <div v-if="!(s.signals||[]).length" style="color:var(--t2);font-size:11px;text-align:center;padding:16px">暂无信号</div>
    <div v-for="sig in s.signals" :key="sig.symbol+sig.dimension" class="sig-row">
      <div class="sig-sym">{{ sig.symbol }}</div>
      <div class="sig-dim">{{ dimLabel(sig.dimension) }}</div>
      <div :class="'sig-dir '+(sig.direction==='bullish'?'up':'dn')">{{ sig.direction==='bullish'?'▲多':'▼空' }}</div>
      <div class="bar-wrap"><div :class="'bar-fill '+(sig.direction==='bullish'?'bar-bull':'bar-bear')" :style="{width:(sig.strength*100)+'%'}"></div></div>
      <div class="sig-pct">{{ Math.round(sig.strength*100) }}</div>
    </div>
  </div>
</template>
<script setup>
const props = defineProps(['s','pct'])
const { s, pct } = props
const dimLabel = k => ({'technical':'技术','sentiment':'情绪','capital_flow':'资金','fundamental':'基本'}[k]||k)
</script>
