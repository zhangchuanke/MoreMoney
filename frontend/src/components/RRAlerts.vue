<template>
  <div>
    <div style="font-size:9px;color:var(--t2);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px">风险预警</div>
    <div v-if="!(s.risk_flags||[]).length" style="color:var(--t2);font-size:11px;text-align:center;padding:16px">无预警</div>
    <div v-for="f in s.risk_flags" :key="f" class="flag-item">
      <span class="flag-icon">⚠</span><span>{{ f }}</span>
    </div>
    <div style="margin-top:12px">
      <div v-if="s.circuit_breaker_triggered" class="flag-item"><span class="flag-icon">🔴</span> 熔断已触发</div>
      <div v-if="s.daily_loss_limit_reached" class="flag-item"><span class="flag-icon">🔴</span> 日亏限额已触达</div>
    </div>
  </div>
</template>
<script setup>
const props = defineProps(['s'])
const { s } = props
</script>
