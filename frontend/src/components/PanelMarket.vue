<template>
  <div class="panel active">
    <div class="sec">四大指数</div>
    <div class="g4" style="margin-bottom:12px">
      <div v-for="(v,k) in s.market_overview" :key="k" class="idx-card">
        <div class="idx-name">{{ v.name }}</div>
        <div class="idx-price">{{ fmt(v.price,2) }}</div>
        <div :class="'idx-chg '+ (v.change_pct>=0?'up':'dn')">{{ v.change_pct>=0?'+':'' }}{{ (v.change_pct||0).toFixed(2) }}%</div>
      </div>
    </div>
    <div class="sec">板块资金流向</div>
    <div class="card">
      <div v-for="(v,k) in s.sector_rotation" :key="k" style="display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid var(--border)">
        <div style="width:80px;font-size:11px;color:var(--t1)">{{ k }}</div>
        <div style="flex:1;height:4px;background:var(--bg4);border-radius:2px;overflow:hidden">
          <div :style="{width:Math.min(Math.abs(v)*10,100)+'%',height:'100%',borderRadius:'2px',background:v>=0?'var(--green)':'var(--red)'}"></div>
        </div>
        <div :class="v>=0?'up':'dn'" style="font-family:var(--mono);font-size:11px;width:48px;text-align:right">{{ v>=0?'+':'' }}{{ v.toFixed(2) }}%</div>
      </div>
    </div>
  </div>
</template>
<script setup>
const props = defineProps(['s','fmt','pct','clr'])
const { s, fmt, pct, clr } = props
</script>
