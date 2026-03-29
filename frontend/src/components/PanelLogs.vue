<template>
  <div class="panel active">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
      <div class="sec" style="margin:0;flex:1">系统日志</div>
      <select v-model="filterLevel" style="background:var(--bg3);border:1px solid var(--border2);color:var(--t1);padding:4px 8px;border-radius:4px;font-size:11px">
        <option value="">全部</option>
        <option value="INFO">INFO</option>
        <option value="WARN">WARN</option>
        <option value="ERR">ERR</option>
      </select>
    </div>
    <div v-for="log in filteredLogs" :key="log.time+log.msg" class="log-item">
      <span class="log-t">{{ log.time }}</span>
      <span :class="'log-lvl log-'+log.level">{{ log.level }}</span>
      <span class="log-msg">{{ log.msg }}</span>
    </div>
    <div v-if="!filteredLogs.length" style="color:var(--t2);text-align:center;padding:24px">暂无日志</div>
  </div>
</template>
<script setup>
import { ref, computed } from 'vue'
const props = defineProps(['s'])
const { s } = props
const filterLevel = ref('')
const filteredLogs = computed(() =>
  filterLevel.value ? (s.logs||[]).filter(l => l.level===filterLevel.value) : (s.logs||[])
)
</script>
