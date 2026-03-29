<template>
  <div class="panel active">
    <div class="sec">Kill Switch</div>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
      <span style="font-size:11px;color:var(--t2)">当前状态</span>
      <span :class="'ks-state-'+s.kill_switch_state">{{ s.kill_switch_state }}</span>
    </div>
    <div class="g2" style="margin-bottom:16px">
      <button class="kill-btn kill-pause"     @click="killSwitch('pause')">⏸ 暂停交易</button>
      <button class="kill-btn kill-resume"    @click="killSwitch('resume')">▶ 恢复交易</button>
      <button class="kill-btn kill-halt"      @click="killSwitch('halt')">🛑 停止系统</button>
      <button class="kill-btn kill-emergency" @click="killSwitch('emergency')">🚨 紧急平仓</button>
    </div>
    <div class="sec">操作历史</div>
    <table class="tbl">
      <thead><tr><th>时间</th><th>状态</th><th>操作者</th><th>原因</th></tr></thead>
      <tbody>
        <tr v-for="h in [...(s.kill_switch_history||[])].reverse()" :key="h.timestamp">
          <td class="mono" style="color:var(--t2)">{{ h.timestamp?.slice(11,19) }}</td>
          <td><span :class="'ks-state-'+h.state" style="padding:2px 8px;font-size:11px">{{ h.state }}</span></td>
          <td style="color:var(--t1)">{{ h.operator }}</td>
          <td style="color:var(--t2)">{{ h.reason }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
<script setup>
const props = defineProps(['s','killSwitch'])
const { s, killSwitch } = props
</script>
