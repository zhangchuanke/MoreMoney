<template>
  <div class="panel active">
    <div class="sec">决策列表</div>
    <table class="tbl">
      <thead><tr><th>操作</th><th>标的</th><th>目标仓</th><th>止损</th><th>止盈</th><th>紧迫度</th><th>风险</th><th>理由</th></tr></thead>
      <tbody>
        <tr v-for="d in s.decisions" :key="d.symbol+d.action">
          <td><span :class="'tag tag-'+d.action">{{ actLabel(d.action) }}</span></td>
          <td class="mono">{{ d.symbol }}</td>
          <td class="mono">{{ pct(d.target_position) }}</td>
          <td class="mono" style="color:#ff3d6b">{{ d.stop_loss }}</td>
          <td class="mono" style="color:#00e5a0">{{ d.take_profit }}</td>
          <td><span :style="{color: urgColor(d.urgency)}">{{ urgLabel(d.urgency) }}</span></td>
          <td><span :style="{color: d.risk_score>0.6?'#ff3d6b':d.risk_score>0.4?'var(--yellow)':'#00e5a0'}">{{ (d.risk_score*100).toFixed(0) }}</span></td>
          <td style="color:var(--t2);max-width:160px">{{ d.reasoning }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
<script setup>
const props = defineProps(['s','pct'])
const { s, pct } = props
const actLabel = a => ({'buy':'买入','sell':'卖出','hold':'持有','reduce':'减仓','add':'加仓'}[a]||a)
const urgLabel = u => ({'immediate':'立即','normal':'普通','passive':'被动'}[u]||u)
const urgColor = u => ({'immediate':'#ff3d6b','normal':'var(--yellow)','passive':'var(--t2)'}[u]||'var(--t2)')
</script>
