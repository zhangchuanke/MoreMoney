<template>
  <div class="panel active">
    <div class="sec">成交记录</div>
    <table class="tbl">
      <thead><tr><th>时间</th><th>操作</th><th>标的</th><th>数量</th><th>成交价</th><th>金额</th><th>滑点</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="o in s.executed_orders" :key="o.time+o.symbol">
          <td class="mono" style="color:var(--t2)">{{ o.time }}</td>
          <td><span :class="'tag tag-'+o.action">{{ o.action==='buy'?'买入':'卖出' }}</span></td>
          <td><span class="mono">{{ o.symbol }}</span> <span style="color:var(--t2)">{{ o.name }}</span></td>
          <td class="mono">{{ o.quantity }}</td>
          <td class="mono">{{ o.filled_price }}</td>
          <td class="mono">¥{{ fmt(o.amount,0) }}</td>
          <td class="mono" style="color:var(--t2)">{{ ((o.slippage||0)*100).toFixed(2) }}%</td>
          <td><span :class="'tag tag-'+o.status">{{ o.status==='filled'?'完成':'部分' }}</span></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
<script setup>
const props = defineProps(['s','fmt'])
const { s, fmt } = props
</script>
