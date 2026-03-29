<template>
  <div class="panel active">
    <div style="margin-bottom:12px">
      <button class="kill-btn kill-resume" style="width:auto;padding:6px 14px" @click="showModal=true">+ 添加</button>
    </div>
    <div v-if="!(s.daily_watchlist||[]).length" style="color:var(--t2);text-align:center;padding:24px">暂无自选股</div>
    <div class="g3">
      <div v-for="w in s.daily_watchlist" :key="w.code" :class="'wl-card '+(w.added_by==='AI'?'wl-ai':'wl-manual')">
        <button class="wl-del" @click="wlDelete(w.code)">✕</button>
        <div style="display:flex;justify-content:space-between;margin-bottom:6px">
          <div><div class="mono" style="font-size:13px;font-weight:700">{{ w.code }}</div><div style="font-size:10px;color:var(--t2)">{{ w.name }}</div></div>
          <div :class="w.change_pct>=0?'up':'dn'" class="mono" style="font-size:14px;font-weight:700">{{ (w.change_pct>=0?'+':'')+w.change_pct.toFixed(2) }}%</div>
        </div>
        <div style="font-size:10px;color:var(--t2);margin-bottom:6px">{{ w.sector }} · {{ w.added_by }} {{ w.added_at }}</div>
        <div style="font-size:11px;color:var(--t1);margin-bottom:6px">{{ w.reason }}</div>
        <div style="display:flex;align-items:center;gap:6px">
          <span style="font-size:9px;color:var(--t2)">评分</span>
          <div style="flex:1;height:3px;background:var(--bg4);border-radius:2px"><div :style="{width:(w.score*100)+'%',height:'100%',background:'var(--acc)',borderRadius:'2px'}"></div></div>
          <span class="mono" style="font-size:10px">{{ (w.score*100).toFixed(0) }}</span>
        </div>
      </div>
    </div>
    <div v-if="showModal" class="modal-overlay" @click.self="showModal=false">
      <div class="modal-box">
        <div class="modal-title">添加自选股</div>
        <div class="form-row"><div class="form-lbl">股票代码 *</div><input class="form-inp" v-model="form.code" placeholder="600519"></div>
        <div class="form-row"><div class="form-lbl">名称</div><input class="form-inp" v-model="form.name" placeholder="贵州茅台"></div>
        <div class="form-row"><div class="form-lbl">板块</div><input class="form-inp" v-model="form.sector" placeholder="食品饮料"></div>
        <div class="form-row"><div class="form-lbl">添加理由</div><input class="form-inp" v-model="form.reason" placeholder="技术面突破"></div>
        <div class="modal-btns">
          <button class="btn-cancel" @click="showModal=false">取消</button>
          <button class="btn-submit" @click="submit">确认添加</button>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { ref, reactive } from 'vue'
const props = defineProps(['s','fmt','pct','clr','wlDelete','wlAdd'])
const { s, fmt, pct, clr, wlDelete, wlAdd } = props
const showModal = ref(false)
const form = reactive({ code:'', name:'', sector:'', reason:'' })
async function submit() {
  if (!form.code.trim()) return
  const ok = await wlAdd({ ...form })
  if (ok) { showModal.value = false; Object.assign(form, { code:'', name:'', sector:'', reason:'' }) }
}
</script>
