<template>
  <div class="panel active">
    <div class="sec">北向资金</div>
    <div class="g4" style="margin-bottom:12px">
      <div class="card"><div class="card-title">今日净流入</div><div class="card-val" :class="nb.today_net>=0?'up':'dn'">{{ nb.today_net>=0?'+':'' }}{{ (nb.today_net||0).toFixed(1) }}亿</div></div>
      <div class="card"><div class="card-title">5日净流入</div><div class="card-val" :class="nb['5day_net']>=0?'up':'dn'">{{ (nb['5day_net']||0).toFixed(1) }}亿</div></div>
      <div class="card"><div class="card-title">连续天数</div><div class="card-val">{{ nb.consecutive_days||0 }}天</div></div>
      <div class="card"><div class="card-title">沪股通</div><div class="card-val">{{ (nb.sh_stock_connect||0).toFixed(1) }}亿</div></div>
    </div>
    <div class="sec">主力资金</div>
    <div class="card" style="margin-bottom:12px">
      <div v-for="(v,k) in mf" :key="k" class="cf-bar-row">
        <div class="cf-lbl">{{ mfLabel(k) }}</div>
        <div class="cf-bar"><div :style="{width:Math.min(Math.abs(v)*2,100)+'%',height:'100%',borderRadius:'3px',background:v>=0?'var(--green)':'var(--red)'}"></div></div>
        <div :class="'cf-val '+(v>=0?'up':'dn')">{{ v>=0?'+':'' }}{{ (v||0).toFixed(1) }}亿</div>
      </div>
    </div>
    <div class="sec">板块资金流</div>
    <div class="card">
      <div v-for="(v,k) in s.capital_flow.sector_flow" :key="k" class="cf-bar-row">
        <div class="cf-lbl">{{ k }}</div>
        <div class="cf-bar"><div :style="{width:Math.min(Math.abs(v)*5,100)+'%',height:'100%',borderRadius:'3px',background:v>=0?'var(--green)':'var(--red)'}"></div></div>
        <div :class="'cf-val '+(v>=0?'up':'dn')">{{ v>=0?'+':'' }}{{ (v||0).toFixed(1) }}亿</div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps(['s','fmt'])
const { s, fmt } = props
const nb = computed(() => s.capital_flow.northbound||{})
const mf = computed(() => s.capital_flow.main_force||{})
const mfLabel = k => ({'net_inflow':'主力净流','large_order_net':'大单净','super_large_net':'超大单','medium_order_net':'中单净','small_order_net':'小单净'}[k]||k)
</script>
