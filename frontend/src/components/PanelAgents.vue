<template>
  <div class="panel active">
    <div class="sec">Agent 运行状态</div>
    <div v-for="(v,k) in s.agent_status" :key="k" class="agent-row">
      <div :class="'agent-dot '+v.status"></div>
      <div class="agent-name">{{ v.name || k }}</div>
      <div class="agent-meta">{{ v.last_run }}</div>
      <div class="agent-meta" style="width:48px;text-align:right">{{ v.avg_duration_ms }}ms</div>
      <div class="agent-meta" style="width:28px;text-align:right" :class="v.error_count>0?'dn':''">{{ v.run_count }}</div>
    </div>
  </div>
</template>
<script setup>
const props = defineProps(['s'])
const { s } = props
</script>
