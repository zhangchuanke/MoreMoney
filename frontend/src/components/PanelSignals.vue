<template>
  <div class="panel active">
    <div class="sec">信号列表</div>
    <div class="card">
      <div v-if="!(s.signals||[]).length" style="color:var(--t2);text-align:center;padding:24px">暂无信号</div>
      <div v-for="sig in s.signals" :key="sig.symbol+sig.dimension" class="sig-row">
        <div class="sig-sym">{{ sig.symbol }}</div>
        <div class="sig-dim">{{ dimLabel(sig.dimension) }}</div>
        <div :class="'sig-dir '+(sig.direction==='bullish'?'up':'dn')">{{ sig.direction==='bullish'?'多':'空' }}</div>
        <div class="bar-wrap">
          <div :class="'bar-fill '+(sig.direction==='bullish'?'bar-bull':'bar-bear')" :style="{width:(sig.strength*100)+'%'}"></div>
        </div>
        <div class="sig-pct">{{ Math.round(sig.strength*100) }}</div>
      </div>
    </div>
    <div class="sec">信号详情</div>
    <table class="tbl">
      <thead><tr><th>标的</th><th>维度</th><th>方向</th><th>强度</th><th>置信</th><th>理由</th></tr></thead>
      <tbody>
        <tr v-for="sig in s.signals" :key="sig.symbol+sig.dimension">
          <td class="mono">{{ sig.symbol }}</td>
          <td>{{ dimLabel(sig.dimension) }}</td>
          <td :class="sig.direction==='bullish'?'up':'dn'">{{ sig.direction==='bullish'?'看多':'看空' }}</td>
          <td class="mono">{{ pct(sig.strength) }}</td>
          <td class="mono">{{ pct(sig.confidence) }}</td>
          <td style="color:var(--t2)">{{ sig.reasoning }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
<script setup>
const props = defineProps(['s','pct'])
const { s, pct } = props
const dimLabel = k => ({'technical':'技术面','sentiment':'情绪面','capital_flow':'资金面','fundamental':'基本面'}[k]||k)
</script>
