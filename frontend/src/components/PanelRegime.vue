<template>
  <div class="panel active">
    <div class="g2" style="margin-bottom:12px">
      <div class="card">
        <div class="card-title">市场机制</div>
        <div class="card-val" :style="{color: regimeColor}">{{ regimeLabel }}</div>
        <div class="card-sub">置信度 {{ pct(s.market_regime.confidence) }}</div>
      </div>
      <div class="card">
        <div class="card-title">描述</div>
        <div style="font-size:12px;color:var(--t1);line-height:1.6;margin-top:4px">{{ s.market_regime.description }}</div>
      </div>
    </div>
    <div class="sec">基础权重</div>
    <div class="card" style="margin-bottom:12px">
      <div v-for="(v,k) in s.market_regime.base_weights" :key="k" class="gauge-row">
        <div class="gauge-lbl">{{ dimLabel(k) }}</div>
        <div class="gauge-bar"><div class="gauge-fill" :style="{width:pct(v),background:'var(--acc2)'}"></div></div>
        <div class="gauge-pct">{{ pct(v) }}</div>
      </div>
    </div>
    <div class="sec">判断信号</div>
    <div class="card">
      <div v-for="(v,k) in s.market_regime.signals" :key="k" style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border);font-size:12px">
        <span style="color:var(--t2)">{{ k }}</span>
        <span class="mono" style="color:var(--t0)">{{ typeof v==='number'?v.toFixed(2):v }}</span>
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps(['s','pct'])
const { s, pct } = props
const dimLabel = k => ({'technical':'技术面','sentiment':'情绪面','capital_flow':'资金面','fundamental':'基本面'}[k]||k)
const regimeLabel = computed(() => ({'bull':'牛市趋势','bear':'熊市趋势','range':'震荡市','momentum':'题材动能','value':'价值修复'}[s.market_regime.regime]||s.market_regime.regime))
const regimeColor = computed(() => ({'bull':'var(--green)','bear':'var(--red)','range':'var(--yellow)','momentum':'var(--acc)','value':'var(--gold)'}[s.market_regime.regime]||'var(--t1)'))
</script>
