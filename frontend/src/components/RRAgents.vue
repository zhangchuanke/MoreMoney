<template>
  <div>
    <div style="font-size:9px;color:var(--t2);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px">Agent 状态</div>
    <div v-for="(v,k) in s.agent_status" :key="k" style="display:flex;align-items:center;gap:7px;padding:5px 0;border-bottom:1px solid rgba(30,45,61,.7)">
      <div :class="'agent-dot '+v.status"></div>
      <div style="flex:1;font-size:11px">{{ v.name||k }}</div>
      <div style="font-size:10px;font-family:var(--mono)" :class="v.status==='running'?'up':v.status==='error'?'dn':'neu'">{{ v.status }}</div>
    </div>
  </div>
</template>
<script setup>
const props = defineProps(['s'])
const { s } = props
</script>
