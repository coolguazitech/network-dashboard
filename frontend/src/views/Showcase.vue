<template>
  <div class="sc">

    <!-- ═══ HERO ═══ -->
    <section class="hero">
      <div class="hero-glow"></div>
      <div class="hero-body" :class="{visible:mounted}">
        <div class="badge">Network Operations &amp; Real-time Analytics</div>
        <h1 class="hero-title">NETORA</h1>
        <p class="hero-sub">歲修驗收，一目瞭然</p>
        <p class="hero-desc">從 SNMP 採集到指標驗收、從拓樸視覺化到案件追蹤<br>一個平台，掌握整個網路歲修生命週期</p>
        <div class="hero-cta">
          <router-link to="/login" class="btn-fill">開始使用</router-link>
          <a href="#" class="btn-ghost" @click.prevent="go(wH)">了解更多</a>
        </div>
      </div>
      <div class="scroll-hint" :class="{visible:mounted}">
        <div class="mouse"><div class="wheel"></div></div><span>SCROLL</span>
      </div>
    </section>

    <!-- ═══ SCROLL-DRIVEN: Dashboard 0→96% ═══ -->
    <section class="scroll-track" ref="dashRef">
      <div class="scroll-stage">
        <div class="st-title" :style="sty(dP,0,.18,{o:0,y:40},{o:1,y:0})">
          <div class="label">Dashboard</div>
          <h2>8 大驗收指標<br>即時掌控</h2>
        </div>
        <div class="dp-wrap" :style="sty(dP,.1,.5,{o:0,sc:.55,blur:10},{o:1,sc:1,blur:0})">
          <div class="dp">
            <div class="dp-head">
              <span class="dp-lbl">指標總覽</span>
              <span class="dp-pct" :style="sty(dP,.3,.5,{o:0},{o:1})">{{ Math.round(lerp(dP,.3,.65,0,96)) }}%</span>
            </div>
            <div class="dp-bar-bg"><div class="dp-bar" :style="{width:lerp(dP,.28,.7,0,96)+'%'}"></div></div>
            <div class="dp-cards">
              <div v-for="(c,i) in dashCards" :key="i" class="dp-card" :class="c.cls"
                :style="sty(dP,.33+i*.04,.42+i*.04,{o:0,y:24},{o:1,y:0})">
                <span class="dp-cn">{{ c.name }}</span><span class="dp-cv" :class="c.cls">{{ c.rate }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="st-tags" :style="sty(dP,.75,.88,{o:0},{o:1})">
          <span>光模塊</span><span>版本</span><span>Uplink</span><span>Port-Channel</span><span>電源</span><span>風扇</span><span>錯誤計數</span><span>Ping</span>
        </div>
      </div>
    </section>

    <!-- ═══ AUTO SANITY CHECK — full-screen pipeline ═══ -->
    <section class="fullpage dark" data-s="sanity">
      <div class="fp-inner" :class="{visible:seen.sanity}">
        <h2 class="fp-title sanity-hero-title">一鍵 Sanity Check</h2>

        <!-- Click button → report appears -->
        <div class="sc-layout">
          <div class="sc-btn-side">
            <div class="sc-fake-btn" @click="showReport=true" :class="{clicked:showReport}">📄 匯出報告</div>
          </div>
          <div class="sc-main-wrap">
            <transition name="report-reveal">
              <img v-if="showReport" :src="reportImg" alt="Sanity Check Report" class="sc-main-img" />
            </transition>
            <div v-if="!showReport" class="sc-placeholder">
              <span>👆</span>
              <p>點擊按鈕生成報告</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══ TOPOLOGY — interactive demo (full-screen) ═══ -->
    <section class="fullpage topo-fp" data-s="topo">
      <div class="fp-inner" :class="{visible:seen.topo}">
        <div class="topo-split">
          <!-- Left: interactive SVG -->
          <div class="topo-canvas-lg">
            <svg viewBox="0 0 640 330" class="topo-svg-demo">
              <template v-for="(l,i) in topoLinksLive" :key="'l'+i">
                <line :x1="l.sx" :y1="l.sy" :x2="l.ex" :y2="l.ey"
                  :stroke="tLinkColor(l,i)" :stroke-width="tLinkWidth(l,i)" :opacity="tLinkOpa(i)" class="topo-link"/>
                <!-- Interface label panel on pinned links -->
                <g v-if="tMode==='pinOnly' && _isPinLink(l) && tGetIfLabel(l)">
                  <rect :x="(l.sx+l.ex)/2 - 62" :y="(l.sy+l.ey)/2 - 10" width="124" height="20" rx="4"
                    fill="rgba(15,23,42,.85)" stroke="rgba(51,65,85,.5)"/>
                  <text :x="(l.sx+l.ex)/2" :y="(l.sy+l.ey)/2 + 4"
                    text-anchor="middle" fill="#cbd5e1" font-size="9" font-family="monospace">{{ tGetIfLabel(l) }}</text>
                </g>
              </template>
              <g v-for="(n,i) in topoNodesAnim" :key="'n'+i"
                v-show="tMode!=='pinOnly' || tPinned.has(i)"
                @mouseenter="tHover(i)" @mouseleave="tHover(-1)" @click="tClick(i)" style="cursor:pointer">
                <circle v-if="tSelected===i || tPinned.has(i)" :cx="n.ax" :cy="n.ay" :r="n.r+6" fill="none" stroke="#fff" stroke-width="2" opacity=".6" class="sel-ring"/>
                <circle :cx="n.ax" :cy="n.ay" :r="tNodeR(n,i)" :fill="tNodeColor(n,i)" :opacity="tNodeOpa(i)" class="topo-circle"/>
                <text v-if="n.label && tShowLabel(i)" :x="n.ax" :y="n.ay+n.r+14" text-anchor="middle" :fill="tLabelColor(i)" :font-size="tLabelSize(i)" font-family="monospace" :font-weight="(tSelected===i||tPinned.has(i))?'bold':'normal'">{{ n.label }}</text>
              </g>
              <template v-if="tMode!=='pinOnly'">
                <text x="10" y="55" fill="#334155" font-size="10" font-weight="700" :opacity="tMode==='layers'?1:.35">L0</text>
                <text x="10" y="158" fill="#334155" font-size="10" font-weight="700" :opacity="tMode==='layers'?1:.35">L1</text>
                <text x="10" y="275" fill="#334155" font-size="10" font-weight="700" :opacity="tMode==='layers'?1:.35">L2</text>
              </template>
              <g v-if="tHovered>=0" class="topo-tip">
                <rect :x="topoNodesAnim[tHovered].ax+16" :y="topoNodesAnim[tHovered].ay-28" width="140" height="48" rx="8" fill="rgba(15,23,42,.95)" stroke="rgba(51,65,85,.6)"/>
                <text :x="topoNodesAnim[tHovered].ax+24" :y="topoNodesAnim[tHovered].ay-12" fill="#f1f5f9" font-size="11" font-weight="700">{{ topoNodesAnim[tHovered].label }}</text>
                <text :x="topoNodesAnim[tHovered].ax+24" :y="topoNodesAnim[tHovered].ay+4" fill="#64748b" font-size="9">{{ topoNodesAnim[tHovered].ip }} · {{ topoNodesAnim[tHovered].vendor }}</text>
              </g>
            </svg>
            <div class="topo-mode-tag">{{ tModeLabel }}</div>
          </div>

          <!-- Right: feature cards -->
          <div class="topo-right">
            <div class="label">Topology</div>
            <h2 class="topo-heading">網路拓樸<br>一眼讀懂</h2>
            <div class="tf-list">
              <div v-for="(ft,i) in topoFeatures" :key="i" class="tf-card" :class="{active:tFeatureIdx===i}" @click="tSetFeature(i)">
                <div class="tf-icon">{{ ft.icon }}</div>
                <div class="tf-text"><h4>{{ ft.title }}</h4><p>{{ ft.desc }}</p></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══ EXPECTATION — full-screen visual comparison ═══ -->
    <section class="fullpage" data-s="dev">
      <div class="fp-inner" :class="{visible:seen.dev}">
        <div class="label center">Validation</div>
        <h2 class="fp-title">定義期望值<br>系統自動比對</h2>
        <p class="fp-sub">告訴系統「應該長什麼樣」，系統自動採集實際狀態，通過或失敗一目瞭然</p>
        <div class="exp-tabs">
          <button v-for="(t,i) in devTabs" :key="i" :class="{active:devIdx===i}" @click="devIdx=i">{{ t.title }}</button>
        </div>
        <transition name="xfade" mode="out-in">
          <div class="exp-showcase" :key="devIdx">
            <div class="exp-card-lg" v-for="(item,j) in devTabs[devIdx].items" :key="j" :class="item.ok?'pass':'fail'">
              <div class="ec-device"><span class="mono">{{ item.device }}</span></div>
              <div class="ec-body">
                <div class="ec-col">
                  <div class="ec-col-hd">期望</div>
                  <div class="ec-val" v-for="v in item.expect" :key="v">{{ v }}</div>
                </div>
                <div class="ec-arrow"><svg viewBox="0 0 24 24" width="28" height="28"><path d="M5 12h14M13 6l6 6-6 6" fill="none" :stroke="item.ok?'#22c55e':'#ef4444'" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
                <div class="ec-col">
                  <div class="ec-col-hd actual">實際採集</div>
                  <div class="ec-val" v-for="v in item.actual" :key="v">{{ v }}</div>
                </div>
                <div class="ec-result" :class="item.ok?'pass':'fail'">{{ item.ok?'✓ 通過':'✗ 不符' }}</div>
              </div>
              <div v-if="item.reason" class="ec-reason">{{ item.reason }}</div>
            </div>
          </div>
        </transition>
      </div>
    </section>

    <!-- ═══ CASES — interactive lifecycle demo ═══ -->
    <section class="fullpage dark cases-fp" data-s="cases">
      <div class="fp-inner" :class="{visible:seen.cases}">
        <h2 class="fp-title">案件追蹤</h2>

        <!-- Interactive case demo -->
        <div class="case-demo">
          <!-- Left: live case card -->
          <div class="cd-card">
            <div class="cd-card-head">
              <span class="mono">EDGE-SW-05</span>
              <span class="cd-ping" :class="caseDemo.ping?'ok':'down'">{{ caseDemo.ping ? '● 可達' : '● 不可達' }}</span>
            </div>
            <div class="cd-status-row">
              <span class="cd-status-badge" :class="caseDemo.statusCls">{{ caseDemo.status }}</span>
              <span class="cd-assignee" v-if="caseDemo.assignee">👤 {{ caseDemo.assignee }}</span>
            </div>
            <!-- Attribute changes -->
            <div class="cd-changes" v-if="caseDemo.changes && caseDemo.changes.length">
              <div class="cd-change" v-for="(ch,i) in caseDemo.changes" :key="i" :class="ch.cls">
                <span class="cd-change-attr">{{ ch.attr }}</span>
                <span class="cd-change-from">{{ ch.from }}</span>
                <span class="cd-change-arrow">→</span>
                <span class="cd-change-to">{{ ch.to }}</span>
              </div>
            </div>
            <div class="cd-summary" v-if="caseDemo.summary">{{ caseDemo.summary }}</div>
            <!-- Notes -->
            <div class="cd-notes" v-if="caseDemo.notes.length">
              <div class="cd-note" v-for="(note,i) in caseDemo.notes" :key="i">
                <span class="cd-note-author">{{ note.author }}</span>
                <span class="cd-note-text">{{ note.text }}</span>
              </div>
            </div>
            <!-- Action buttons (change based on step) -->
            <div class="cd-actions">
              <button v-for="btn in caseDemo.buttons" :key="btn.label" class="cd-btn" :class="btn.cls" @click="caseNextStep">{{ btn.label }}</button>
            </div>
          </div>

          <!-- Right: timeline -->
          <div class="cd-timeline">
            <div class="cd-tl-title">生命週期</div>
            <div class="cd-tl-items">
              <div class="cd-tl-item" v-for="(ev,i) in caseDemo.timeline" :key="i" :class="ev.cls">
                <div class="cd-tl-dot"></div>
                <div class="cd-tl-content">
                  <div class="cd-tl-label">{{ ev.label }}</div>
                  <div class="cd-tl-desc">{{ ev.desc }}</div>
                </div>
              </div>
            </div>
            <!-- Step controls -->
            <div class="cd-controls">
              <button class="cd-ctrl-btn" @click="caseReset">重新開始</button>
              <button class="cd-ctrl-btn primary" @click="caseNextStep">{{ caseStep < caseScenario.length - 1 ? '下一步 →' : '重新開始' }}</button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══ CLIENT WIZARD — full-screen interactive ═══ -->
    <section class="fullpage" data-s="client">
      <div class="fp-inner" :class="{visible:seen.client}">
        <div class="label center">Client Management</div>
        <h2 class="fp-title">GNMS 匯入精靈<br>批次匯入 Client</h2>
        <p class="fp-sub">從 GNMS MacARP API 查詢設備下的 Client，分批篩選、標記負責人、一鍵匯入</p>
        <div class="wiz-showcase">
          <div class="wiz-steps four">
            <div v-for="(ws,i) in wizSteps" :key="i" class="wiz-step" :class="{active:wizI===i,done:wizI>i}" @click="wizGoTo(i)">
              <div class="wiz-dot">{{ wizI>i?'✓':i+1 }}</div><span>{{ ws }}</span>
            </div>
          </div>
          <transition name="wfade" mode="out-in">
            <div class="wiz-panel" :key="wizI">
              <template v-if="wizI===0">
                <div class="wp-info">
                  <div class="wp-row"><span>歲修 ID</span><span class="mono">FAB18-2026Q2</span></div>
                  <div class="wp-row"><span>設備數</span><span>18 台</span></div>
                  <div class="wp-row"><span>每批上限</span><span>100 台</span></div>
                  <div class="wp-row"><span>預計批次</span><span>1 批</span></div>
                </div>
              </template>
              <template v-else-if="wizI===1">
                <div class="wp-loading">
                  <div class="wiz-spinner-lg"><div class="wiz-spin-ring"></div><div class="wiz-spin-ring inner"></div></div>
                  <p class="text-cyan">正在查詢 GNMS MacARP API...</p>
                  <div class="wiz-pbar-bg"><div class="wiz-pbar" :style="{width:wizProg+'%'}"></div></div>
                </div>
              </template>
              <template v-else-if="wizI===2">
                <div class="wp-review">
                  <div class="wp-review-hd"><span class="dim">共 <b class="text-white">247</b> 筆 Client</span><span class="wiz-sel-badge">已選 18 台</span></div>
                  <div class="wp-table">
                    <div class="wpt-hd"><span>☑</span><span>設備</span><span>Tenant</span><span>Client</span><span>標記</span></div>
                    <div v-for="d in wizDevices" :key="d.n" class="wpt-row" :class="{checked:d.sel}">
                      <span class="wiz-chk">{{ d.sel?'☑':'☐' }}</span>
                      <span class="mono text-xs">{{ d.n }}</span>
                      <span class="wiz-tag">{{ d.tg }}</span>
                      <span>{{ d.cnt }}</span>
                      <span :class="d.marked?'text-ok':'text-amber'">{{ d.marked?'✓':'—' }}</span>
                    </div>
                  </div>
                </div>
              </template>
              <template v-else>
                <div class="wp-done">
                  <svg viewBox="0 0 52 52" class="wiz-check-svg"><circle cx="26" cy="26" r="24" fill="none" stroke="#22c55e" stroke-width="3"/><path d="M14 27l8 8 16-16" fill="none" stroke="#22c55e" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" class="wiz-check-path"/></svg>
                  <div class="wp-done-num">247</div>
                  <div class="wp-done-lbl">筆 Client 已成功匯入</div>
                  <div class="wp-done-row"><span class="text-ok">247</span> 新增 <span class="text-amber">12</span> 跳過 <span class="text-err">0</span> 錯誤</div>
                </div>
              </template>
            </div>
          </transition>
          <div class="wiz-actions">
            <button v-if="wizI>0 && wizI<3" class="wiz-btn ghost" @click="wizGoTo(wizI-1)">上一步</button>
            <button v-if="wizI===0" class="wiz-btn fill" @click="wizNext">開始查詢</button>
            <button v-else-if="wizI===2" class="wiz-btn fill" @click="wizNext">匯入選取設備</button>
            <button v-else-if="wizI===3" class="wiz-btn fill" @click="wizGoTo(0)">重新體驗</button>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══ RBAC ═══ -->
    <section class="fullpage" data-s="rbac">
      <div class="fp-inner" :class="{visible:seen.rbac}">
        <h2 class="fp-title">角色權限控管</h2>
        <div class="img-hero">
          <img :src="usersImg" alt="使用者管理" class="img-hero-main" />
        </div>
      </div>
    </section>

    <!-- ═══ Contacts ═══ -->
    <section class="fullpage dark" data-s="contacts">
      <div class="fp-inner" :class="{visible:seen.contacts}">
        <h2 class="fp-title">通訊錄</h2>
        <div class="img-hero">
          <img :src="contactsImg" alt="通訊錄" class="img-hero-main" />
        </div>
      </div>
    </section>

    <!-- ═══ System Logs ═══ -->
    <section class="fullpage" data-s="logs">
      <div class="fp-inner" :class="{visible:seen.logs}">
        <h2 class="fp-title">系統日誌</h2>
        <div class="img-hero">
          <img :src="logsImg" alt="系統日誌" class="img-hero-main" />
        </div>
      </div>
    </section>

    <!-- ═══ STATS — massive numbers ═══ -->
    <section class="fullpage dark" data-s="stats">
      <div class="fp-inner" :class="{visible:seen.stats}">
        <h2 class="stats-hl">為大規模歲修而生</h2>
        <div class="stats-mega">
          <div class="sm-item" v-for="s in allStats" :key="s.l">
            <div class="sm-val">{{ s.v }}</div>
            <div class="sm-lbl">{{ s.l }}</div>
            <div class="sm-desc">{{ s.d }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══ CTA ═══ -->
    <section class="fullpage cta-bg" data-s="cta">
      <div class="fp-inner" :class="{visible:seen.cta}">
        <h2 class="cta-title">準備好了嗎？</h2>
        <p class="cta-sub">NETORA 讓歲修驗收不再是苦差事</p>
        <router-link to="/login" class="btn-fill lg">立即登入</router-link>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, defineOptions } from 'vue'
import reportImg from '@/assets/showcase/report.png'
import usersImg from '@/assets/showcase/users.png'
import contactsImg from '@/assets/showcase/contacts.png'
import logsImg from '@/assets/showcase/logs.png'
defineOptions({ name: 'Showcase' })

const mounted = ref(false)
const wH = ref(0)
const dashRef = ref(null)
const dP = ref(0)

function lerp(p,t0,t1,v0,v1){ return p<=t0?v0:p>=t1?v1:v0+(v1-v0)*((p-t0)/(t1-t0)) }
function sty(p,t0,t1,f,t){
  const r={}; if('o' in f) r.opacity=lerp(p,t0,t1,f.o,t.o)
  const parts=[]; if('y' in f) parts.push(`translateY(${lerp(p,t0,t1,f.y,t.y)}px)`)
  if('sc' in f) parts.push(`scale(${lerp(p,t0,t1,f.sc,t.sc)})`); if(parts.length) r.transform=parts.join(' ')
  if('blur' in f) r.filter=`blur(${lerp(p,t0,t1,f.blur,t.blur)}px)`; return r
}
function updateP(){ if(!dashRef.value) return; const r=dashRef.value.getBoundingClientRect(); const h=dashRef.value.offsetHeight-window.innerHeight; if(h>0) dP.value=Math.max(0,Math.min(1,-r.top/h)) }

const seen = reactive({sanity:false,topo:false,dev:false,cases:false,client:false,rbac:false,contacts:false,logs:false,stats:false,cta:false})
let obs=null, ticking=false
function onScroll(){ if(!ticking){ticking=true;requestAnimationFrame(()=>{updateP();ticking=false})} }
function go(y){ window.scrollTo({top:y,behavior:'smooth'}) }

// ── Sanity Check ──
const showReport = ref(false)
const sanityGlow = ref(0)
let sanityTimer = null
const sanityFlow = [
  { icon:'📡', label:'採集', desc:'唯讀 SNMP 安全採集' },
  { icon:'🔍', label:'比對', desc:'期望值 vs 實際狀態' },
  { icon:'🚨', label:'通報', desc:'異常自動開案指派' },
  { icon:'✅', label:'結案', desc:'恢復即自動結案' },
]
const sanityLogs = [
  { time:'16:05:32', type:'採集', cls:'ok', msg:'EDGE-SW-01 ~ EDGE-SW-12 SNMP 採集完成（8/8 指標）' },
  { time:'16:05:33', type:'比對', cls:'ok', msg:'Uplink 全部通過 — 17/17 連線匹配期望值' },
  { time:'16:05:33', type:'異常', cls:'err', msg:'EDGE-SW-05 Ping 不可達 — 自動開案 #142，指派：王大明' },
  { time:'16:05:34', type:'變化', cls:'warn', msg:'AGG-SW-02 GE1/0/3 VLAN 100 → 200（屬性變更已記錄）' },
  { time:'16:05:35', type:'恢復', cls:'ok', msg:'EDGE-SW-09 Ping 恢復可達 — 案件 #138 自動結案' },
]

// ── Topology: real FAB architecture ──
// Layout: Core(2) + FW(2) at top, AGG(8) in middle, Edge(12) at bottom
// Indices: 0=CORE-01, 1=CORE-02, 2=FW-01, 3=FW-02,
//          4-11=AGG-01~08, 12-23=EDGE-01~12

const _c1=240, _c2=400  // core X positions
const _fw1=90, _fw2=550 // firewall X positions
// AGG pairs: (4,5) (6,7) (8,9) (10,11) — X spread across width
const _aggPairX = [110, 230, 380, 500]
const _aggY = 155, _aggGap = 36 // gap within pair

const topoNodesDef = [
  // Core (peer link)
  { x:_c1,y:50,r:16,color:'#22c55e',label:'CORE-01',ip:'10.1.1.1',vendor:'NX-OS',layer:0,
    neighbors:[1,2,4,5,6,7,8,9,10,11] },
  { x:_c2,y:50,r:16,color:'#22c55e',label:'CORE-02',ip:'10.1.1.2',vendor:'NX-OS',layer:0,
    neighbors:[0,3,4,5,6,7,8,9,10,11] },
  // Firewalls
  { x:_fw1,y:50,r:11,color:'#3b82f6',label:'FW-01',ip:'10.1.4.1',vendor:'Palo Alto',layer:0,
    neighbors:[0,3] },
  { x:_fw2,y:50,r:11,color:'#3b82f6',label:'FW-02',ip:'10.1.4.2',vendor:'Palo Alto',layer:0,
    neighbors:[1,2] },
  // AGG pairs (4 pairs × 2 = 8)
  ...Array.from({length:4},(_, pi)=>[
    { x:_aggPairX[pi]-_aggGap/2, y:_aggY, r:11, color:pi===1?'#eab308':'#22c55e',
      label:`AGG-${String(pi*2+1).padStart(2,'0')}`, ip:`10.1.2.${pi*2+1}`, vendor:'IOS', layer:1,
      neighbors:[0,1, 4+pi*2+1, 12+pi*3, 12+pi*3+1, 12+pi*3+2] },
    { x:_aggPairX[pi]+_aggGap/2, y:_aggY, r:11, color:pi===1?'#eab308':'#22c55e',
      label:`AGG-${String(pi*2+2).padStart(2,'0')}`, ip:`10.1.2.${pi*2+2}`, vendor:'IOS', layer:1,
      neighbors:[0,1, 4+pi*2, 12+pi*3, 12+pi*3+1, 12+pi*3+2] },
  ]).flat(),
  // Edge (12 = 3 per AGG pair, dual uplink to both AGGs in pair)
  ...Array.from({length:12},(_, i)=>{
    const pair = Math.floor(i/3)
    const posInPair = i % 3
    const pairCx = _aggPairX[pair]
    return {
      x: pairCx - 40 + posInPair * 40, y: 270, r: 8,
      color: i===4?'#dc2626': i===10?'#eab308': '#22c55e',
      label: (i===4||i===10) ? `EDGE-${String(i+1).padStart(2,'0')}` : '',
      ip:`10.1.3.${i+1}`, vendor:'HPE', layer:2,
      neighbors:[4+pair*2, 4+pair*2+1],
    }
  }),
]
const topoNodesAnim = ref(topoNodesDef.map(n=>({...n,ax:n.x,ay:n.y})))

// Links
const topoLinksDef = [
  // Core peer link
  {si:0,ei:1,status:'expected_pass'},
  // FW: CORE-01↔FW-01, CORE-02↔FW-02, FW peer link
  {si:0,ei:2,status:'expected_pass'},
  {si:1,ei:3,status:'expected_pass'},
  {si:2,ei:3,status:'expected_pass'},
  // AGG→Core: each AGG pair has 4 links to core (2 per AGG × 2 cores)
  ...Array.from({length:4},(_, pi)=>[
    {si:4+pi*2, ei:0, status:'expected_pass'}, // AGG-odd → CORE-01
    {si:4+pi*2, ei:1, status:'expected_pass'}, // AGG-odd → CORE-02
    {si:4+pi*2+1, ei:0, status:'expected_pass'}, // AGG-even → CORE-01
    {si:4+pi*2+1, ei:1, status:'expected_pass'}, // AGG-even → CORE-02
  ]).flat(),
  // AGG MLAG peer link within pair
  ...Array.from({length:4},(_, pi)=>({si:4+pi*2, ei:4+pi*2+1, status:'discovered'})),
  // Edge→AGG: each edge has 2 links (1 to each AGG in its pair)
  ...Array.from({length:12},(_, i)=>{
    const pair = Math.floor(i/3)
    return [
      {si:12+i, ei:4+pair*2, status:i===4?'expected_fail':'discovered'},
      {si:12+i, ei:4+pair*2+1, status:'discovered'},
    ]
  }).flat(),
]
const topoLinksLive = computed(()=>{ const ns=topoNodesAnim.value; return topoLinksDef.map(l=>({...l,sx:ns[l.si].ax,sy:ns[l.si].ay,ex:ns[l.ei].ax,ey:ns[l.ei].ay})) })

const tMode = ref('layers'); const tSelected = ref(-1); const tPinned = ref(new Set()); const tHovered = ref(-1); const tFeatureIdx = ref(0)
let tAutoTimer = null
const topoFeatures = [
  { icon:'🏗️',title:'智慧分層',desc:'自動辨識 Core / AGG / Edge / FW' },
  { icon:'🎨',title:'狀態著色',desc:'綠=正常 黃=異常 紅=不可達' },
  { icon:'👆',title:'節點選取',desc:'點擊高亮鄰居，淡化其餘' },
  { icon:'📌',title:'Pin Only',desc:'多選節點後只顯示已選，含詳細介面' },
  { icon:'✋',title:'拖曳互動',desc:'拖動節點，連線跟隨移動' },
  { icon:'🔗',title:'連線比對',desc:'綠=通過 紅=失敗 灰=發現' },
]
const tModeLabel = computed(()=>({layers:'階層模式',colors:'狀態模式',select:'選取模式',pinOnly:`Pin Only（${tPinned.value.size} 個節點）`,drag:'拖曳模式',links:'連線比對'})[tMode.value])

// Interface labels for links (for pin-only detail view)
const linkInterfaces = {
  '0-1':'Eth1/49 ↔ Eth1/49',
  '0-2':'Eth1/48 ↔ Eth1/1', '1-3':'Eth1/48 ↔ Eth1/1', '2-3':'Eth1/2 ↔ Eth1/2',
  '0-4':'Eth1/1 ↔ Te1/1/1', '0-5':'Eth1/2 ↔ Te1/1/1',
  '1-4':'Eth1/3 ↔ Te1/1/2', '1-5':'Eth1/4 ↔ Te1/1/2',
  '4-5':'Te1/1/3 ↔ Te1/1/3',
  '0-6':'Eth1/5 ↔ Te1/1/1', '0-7':'Eth1/6 ↔ Te1/1/1',
  '1-6':'Eth1/5 ↔ Te1/1/2', '1-7':'Eth1/6 ↔ Te1/1/2',
  '6-7':'Te1/1/3 ↔ Te1/1/3',
  // AGG-03(6)→EDGE-04(15), AGG-04(7)→EDGE-04(15)
  '6-15':'Gi1/0/1 ↔ XGE1/0/1', '7-15':'Gi1/0/1 ↔ XGE1/0/2',
}

function tSetFeature(idx){ stopTopoAuto(); tFeatureIdx.value=idx; applyFeatureMode(idx) }
function applyFeatureMode(idx){
  tSelected.value=-1; tPinned.value=new Set()
  topoNodesAnim.value=topoNodesDef.map(n=>({...n,ax:n.x,ay:n.y}))
  const modes=['layers','colors','select','pinOnly','drag','links']
  tMode.value=modes[idx]
  if(idx===2) tSelected.value=5
  else if(idx===3){
    // Pin Only: like real screenshot — CORE-01, CORE-02, AGG-03, AGG-04, EDGE-04
    // Spread out to fill the canvas with interface labels visible
    const pinIdx=[0,1,6,7,15] // CORE-01, CORE-02, AGG-03, AGG-04, EDGE-04
    tPinned.value=new Set(pinIdx)
    const positions=[
      {x:180,y:60},   // CORE-01 top-left
      {x:460,y:60},   // CORE-02 top-right
      {x:100,y:195},  // AGG-03 mid-left
      {x:540,y:195},  // AGG-04 mid-right
      {x:320,y:290},  // EDGE-04 bottom-center
    ]
    const ns=topoNodesDef.map((n,i)=>{
      const pi=pinIdx.indexOf(i)
      if(pi>=0) return {...n,ax:positions[pi].x,ay:positions[pi].y,r:n.r*1.4}
      return {...n,ax:n.x,ay:n.y}
    })
    topoNodesAnim.value=ns
  }
  else if(idx===4) animateDrag()
}
function _ease(t){ return t<.5?2*t*t:1-Math.pow(-2*t+2,2)/2 }
function _animNode(ni, dest, dur, cb) {
  const orig = { x: topoNodesAnim.value[ni].ax, y: topoNodesAnim.value[ni].ay }
  let f = 0
  function step() {
    f++; const t = _ease(Math.min(1, f / dur))
    const ns = [...topoNodesAnim.value]
    ns[ni] = { ...ns[ni], ax: orig.x + (dest.x - orig.x) * t, ay: orig.y + (dest.y - orig.y) * t }
    topoNodesAnim.value = ns
    if (f < dur) requestAnimationFrame(step); else if (cb) setTimeout(cb, 300)
  }
  requestAnimationFrame(step)
}
function animateDrag() {
  // Drag CORE-01 up-left slightly to spread the cluster — don't overlap with FW
  // CORE-01: (240,50) → (160,20), CORE-02: (400,50) → (480,20)
  _animNode(0, { x: 160, y: 18 }, 55, () => {
    _animNode(1, { x: 480, y: 18 }, 55)
  })
}
function tNodeColor(n){ return tMode.value==='layers'?['#06b6d4','#0ea5e9','#3b82f6'][n.layer]||'#8b5cf6':n.color }
function _isPinVisible(i){ const p=tPinned.value; if(p.size===0) return false; if(p.has(i)) return true; for(const pi of p){ if(topoNodesDef[pi].neighbors.includes(i)) return true } return false }
function _isPinLink(l){ const p=tPinned.value; return p.has(l.si)&&p.has(l.ei) }
function tGetIfLabel(l){ const key=Math.min(l.si,l.ei)+'-'+Math.max(l.si,l.ei); return linkInterfaces[key]||'' }

function tNodeOpa(i){ if(tMode.value==='select'&&tSelected.value>=0){const s=topoNodesDef[tSelected.value];return(i===tSelected.value||s.neighbors.includes(i))?1:.12} if(tMode.value==='pinOnly'&&tPinned.value.size>0) return _isPinVisible(i)?1:0; return 1 }
function tNodeR(n,i){ return tHovered.value===i?n.r*1.3:(tPinned.value.has(i)||tSelected.value===i)?n.r*1.2:n.r }
function tShowLabel(i){ if(tMode.value==='pinOnly') return tPinned.value.has(i); return true }
function tLabelColor(i){ return (tSelected.value===i||tPinned.value.has(i))?'#fff':'#94a3b8' }
function tLabelSize(i){ return tMode.value==='pinOnly'&&tPinned.value.has(i)?13:9 }
function tLinkColor(l){ if(tMode.value==='links') return l.status==='expected_pass'?'#22c55e':l.status==='expected_fail'?'#ef4444':'#475569'; if(tMode.value==='select'&&tSelected.value>=0) return(l.si===tSelected.value||l.ei===tSelected.value)?'#67e8f9':'rgba(71,85,105,.2)'; if(tMode.value==='pinOnly') return _isPinLink(l)?'#67e8f9':'rgba(71,85,105,.1)'; return 'rgba(71,85,105,.5)' }
function tLinkWidth(l){ if(tMode.value==='links') return l.status==='expected_fail'?2.5:1.8; if(tMode.value==='select'&&tSelected.value>=0) return(l.si===tSelected.value||l.ei===tSelected.value)?2.5:.8; if(tMode.value==='pinOnly') return _isPinLink(l)?2.5:.5; return 1.5 }
function tLinkOpa(i){ if(tMode.value==='pinOnly'&&tPinned.value.size>0){const l=topoLinksDef[i]; return _isPinLink(l)?.8:0} return undefined }
function tHover(i){ tHovered.value=i }
function tClick(i){ if(tMode.value==='select') tSelected.value=tSelected.value===i?-1:i; if(tMode.value==='pinOnly'){const p=new Set(tPinned.value); if(p.has(i)) p.delete(i); else p.add(i); tPinned.value=p} }
function startTopoAuto(){ stopTopoAuto(); tAutoTimer=setInterval(()=>{ const next=(tFeatureIdx.value+1)%topoFeatures.length; tFeatureIdx.value=next; applyFeatureMode(next) },4000) }
function stopTopoAuto(){ if(tAutoTimer){clearInterval(tAutoTimer);tAutoTimer=null} }

// ── Expectations ──
const devIdx = ref(0)
const devTabs=[
  {title:'Uplink',items:[
    {device:'AGG-SW-01',expect:['Te1/1/1 → CORE-SW-01','介面 Eth1/1'],actual:['Te1/1/1 → CORE-SW-01','介面 Eth1/1'],ok:true},
    {device:'EDGE-SW-05',expect:['XGE1/0/1 → AGG-SW-02','介面 Gi1/0/1'],actual:['XGE1/0/1 → AGG-SW-03','介面 Gi1/0/2'],ok:false,reason:'鄰居不符：期望 AGG-SW-02，實際 AGG-SW-03'},
  ]},
  {title:'版本',items:[
    {device:'CORE-SW-01',expect:['n9000-dk9.10.3.2'],actual:['bootflash:n9000-dk9.10.3.2.bin'],ok:true},
    {device:'EDGE-SW-05',expect:['R1238P06','R1238P06H01'],actual:['flash:5710-R1238P06.bin'],ok:false,reason:'缺少補丁 R1238P06H01'},
  ]},
  {title:'Port-Channel',items:[
    {device:'CORE-SW-01',expect:['Po1','Members: Eth1/49, Eth1/50'],actual:['Po1','Members: Eth1/49, Eth1/50'],ok:true},
    {device:'AGG-SW-01',expect:['Po1','Members: Gi1/0/23, Gi1/0/24'],actual:['Po1','Members: Gi1/0/23'],ok:false,reason:'Member 缺少 Gi1/0/24'},
  ]},
]

// ── Cases interactive demo: ACL change → ping down → fix → manual resolve ──
const caseStep = ref(0)
const caseScenario = [
  { // 0: ACL name changed after maintenance
    ping:true, status:'處理中', statusCls:'inprogress', assignee:'王大明', summary:'',
    notes:[], changes:[{attr:'ACL',from:'3220',to:'3150',cls:'err'}],
    buttons:[{label:'系統偵測到屬性變化...', cls:'disabled'}],
    timeline:[{label:'屬性變化：ACL',desc:'GE1/0/5 ACL 從 3220 → 3150',cls:'err'}],
  },
  { // 1: Ping goes down because of wrong ACL
    ping:false, status:'處理中', statusCls:'inprogress', assignee:'王大明', summary:'',
    notes:[], changes:[{attr:'ACL',from:'3220',to:'3150',cls:'err'},{attr:'Ping',from:'可達',to:'不可達',cls:'err'}],
    buttons:[{label:'新增筆記',cls:'ghost'}],
    timeline:[
      {label:'屬性變化：ACL',desc:'GE1/0/5 ACL 從 3220 → 3150',cls:'done'},
      {label:'Ping 不可達',desc:'ACL 變更導致設備無法回應',cls:'err'},
    ],
  },
  { // 2: Engineer investigates
    ping:false, status:'處理中', statusCls:'inprogress', assignee:'王大明',
    summary:'',
    notes:[{author:'王大明',text:'確認歲修時 ACL 被改為 3150，原本應為 3220，聯繫負責人修復'}],
    changes:[{attr:'ACL',from:'3220',to:'3150',cls:'err'},{attr:'Ping',from:'可達',to:'不可達',cls:'err'}],
    buttons:[{label:'📷 上傳截圖',cls:'ghost'},{label:'討論',cls:'ghost'}],
    timeline:[
      {label:'屬性變化：ACL',desc:'GE1/0/5 ACL 從 3220 → 3150',cls:'done'},
      {label:'Ping 不可達',desc:'ACL 變更導致設備無法回應',cls:'done'},
      {label:'調查中',desc:'確認歲修時 ACL 被誤改',cls:'active'},
    ],
  },
  { // 3: ACL restored, ping recovered
    ping:true, status:'處理中', statusCls:'inprogress', assignee:'王大明',
    summary:'',
    notes:[
      {author:'王大明',text:'確認歲修時 ACL 被改為 3150，原本應為 3220，聯繫負責人修復'},
      {author:'王大明',text:'負責人已將 ACL 恢復為 3220'},
      {author:'系統',text:'Ping 已恢復可達'},
    ],
    changes:[{attr:'ACL',from:'3150',to:'3220',cls:'ok'},{attr:'Ping',from:'不可達',to:'可達',cls:'ok'}],
    buttons:[{label:'標記已解決',cls:'primary'}],
    timeline:[
      {label:'屬性變化：ACL',desc:'GE1/0/5 ACL 從 3220 → 3150',cls:'done'},
      {label:'Ping 不可達',desc:'ACL 變更導致設備無法回應',cls:'done'},
      {label:'調查中',desc:'確認歲修時 ACL 被誤改',cls:'done'},
      {label:'ACL 恢復',desc:'負責人恢復 ACL 3220',cls:'ok'},
      {label:'Ping 恢復',desc:'設備已恢復回應',cls:'ok'},
    ],
  },
  { // 4: Manually resolved
    ping:true, status:'已結案', statusCls:'resolved', assignee:'王大明',
    summary:'歲修時 GE1/0/5 ACL 被誤改為 3150，已由負責人恢復為 3220',
    notes:[
      {author:'王大明',text:'確認歲修時 ACL 被改為 3150，原本應為 3220，聯繫負責人修復'},
      {author:'王大明',text:'負責人已將 ACL 恢復為 3220'},
      {author:'系統',text:'Ping 已恢復可達'},
      {author:'王大明',text:'驗證完成，手動結案'},
    ],
    changes:[],
    buttons:[{label:'重新體驗 ↺',cls:'ghost'}],
    timeline:[
      {label:'屬性變化：ACL',desc:'GE1/0/5 ACL 從 3220 → 3150',cls:'done'},
      {label:'Ping 不可達',desc:'ACL 變更導致設備無法回應',cls:'done'},
      {label:'調查中',desc:'確認原因並聯繫廠務',cls:'done'},
      {label:'ACL 恢復',desc:'負責人恢復 ACL 3220',cls:'done'},
      {label:'Ping 恢復',desc:'設備已恢復回應',cls:'done'},
      {label:'手動結案',desc:'王大明驗證完成，標記已解決',cls:'ok'},
    ],
  },
]

const caseDemo = computed(()=>caseScenario[caseStep.value])
function caseNextStep(){ caseStep.value = caseStep.value >= caseScenario.length-1 ? 0 : caseStep.value+1 }
function caseReset(){ caseStep.value = 0 }

// ── Wizard ──
const wizI = ref(0); const wizProg = ref(0)
const wizSteps = ['確認開始','查詢 API','檢視 & 標記','匯入完成']
const wizDevices = [
  {n:'CORE-SW-01',tg:'F18',cnt:8,sel:true,marked:true},{n:'AGG-SW-01',tg:'F18',cnt:22,sel:true,marked:true},
  {n:'AGG-SW-02',tg:'F18',cnt:19,sel:true,marked:true},{n:'EDGE-SW-01',tg:'F18',cnt:15,sel:true,marked:true},
  {n:'EDGE-SW-05',tg:'F18',cnt:0,sel:false,marked:false},
]
let wizT = null
function stopWiz(){ if(wizT){clearInterval(wizT);wizT=null} }
function wizGoTo(s){ stopWiz(); wizI.value=s; wizProg.value=0; if(s===1) runQuery() }
function wizNext(){ stopWiz(); if(wizI.value===0){wizI.value=1;runQuery()} else if(wizI.value===2){wizI.value=3} }
function runQuery(){ wizProg.value=0; wizT=setInterval(()=>{ wizProg.value+=3; if(wizProg.value>=100){stopWiz();wizI.value=2} },50) }
function startWiz(){ wizGoTo(0) }

// ── Stats ──
const dashCards=[
  {name:'光模塊',rate:'100%',cls:'pass'},{name:'版本',rate:'100%',cls:'pass'},
  {name:'Uplink',rate:'100%',cls:'pass'},{name:'Port-Ch',rate:'100%',cls:'pass'},
  {name:'電源',rate:'100%',cls:'pass'},{name:'風扇',rate:'92%',cls:'warn'},
  {name:'錯誤計數',rate:'78%',cls:'fail'},{name:'Ping',rate:'98%',cls:'pass'},
]
const allStats = [
  {v:'8',l:'驗收指標',d:'自動評估每台設備的通過率'},
  {v:'50+',l:'台設備同時採集',d:'安全唯讀，不影響交換器運作'},
  {v:'<2s',l:'資料延遲',d:'可達設備優先，秒級回饋'},
  {v:'7×24',l:'自動巡檢',d:'異常即開案，恢復即結案'},
  {v:'0',l:'Critical CVE',d:'Docker Scout 掃描零漏洞'},
  {v:'1 鍵',l:'生成驗收報告',d:'HTML 報告直接交付客戶'},
]

onMounted(()=>{
  mounted.value=true; wH.value=window.innerHeight
  window.addEventListener('scroll',onScroll,{passive:true})
  obs=new IntersectionObserver(entries=>{
    entries.forEach(e=>{ if(e.isIntersecting){ const id=e.target.dataset.s; if(id) seen[id]=true; if(id==='client') startWiz(); if(id==='topo') startTopoAuto()
      if(id==='sanity'){ sanityTimer=setInterval(()=>{sanityGlow.value=(sanityGlow.value+1)%4},1200) }
    }})
  },{threshold:.12})
  document.querySelectorAll('[data-s]').forEach(el=>obs.observe(el))
})
onBeforeUnmount(()=>{ window.removeEventListener('scroll',onScroll); obs?.disconnect(); stopWiz(); stopTopoAuto(); if(sanityTimer) clearInterval(sanityTimer) })
</script>

<style scoped>
.sc{color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',sans-serif}

/* ═══ SHARED ═══ */
.fullpage{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:100px 48px;position:relative;overflow:hidden}
.fullpage.dark{background:rgba(0,0,0,.2)}
/* Decorative glow orbs */
.fullpage::before{content:'';position:absolute;width:500px;height:500px;border-radius:50%;filter:blur(120px);opacity:.06;pointer-events:none}
.fullpage:nth-child(odd)::before{background:radial-gradient(circle,#06b6d4,transparent 70%);top:-100px;right:-100px}
.fullpage:nth-child(even)::before{background:radial-gradient(circle,#6366f1,transparent 70%);bottom:-100px;left:-100px}
.topo-fp::before{background:radial-gradient(circle,#22c55e,transparent 70%) !important;top:auto !important;bottom:-150px;right:auto;left:50%;transform:translateX(-50%)}
.fp-inner{max-width:1100px;width:100%;opacity:0;transform:translateY(50px);transition:all 1s cubic-bezier(.16,1,.3,1)}
.fp-inner.visible{opacity:1;transform:none}
.fp-title{font-size:clamp(2rem,5vw,3rem);font-weight:800;text-align:center;color:#f1f5f9;line-height:1.25;margin-bottom:16px}
.fp-title::after{content:'';display:block;width:60px;height:3px;background:linear-gradient(90deg,#06b6d4,#6366f1);border-radius:2px;margin:16px auto 0}
.fp-sub{font-size:16px;color:#94a3b8;text-align:center;max-width:540px;margin:0 auto 40px;line-height:1.7}
.label{font-size:13px;font-weight:600;color:#06b6d4;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px}
.label.center{text-align:center}
.center{text-align:center}
.mono{font-family:ui-monospace,SFMono-Regular,monospace}
.dim{color:#94a3b8}
.text-ok{color:#4ade80}.text-err{color:#f87171}.text-cyan{color:#67e8f9}.text-amber{color:#fbbf24}.text-white{color:#f1f5f9}

.btn-fill{padding:14px 36px;border-radius:12px;font-weight:600;font-size:16px;text-decoration:none;background:linear-gradient(135deg,#06b6d4,#6366f1);color:#fff;box-shadow:0 4px 20px rgba(6,182,212,.3);transition:all .3s}
.btn-fill:hover{transform:translateY(-2px);box-shadow:0 8px 30px rgba(6,182,212,.4)}
.btn-fill.lg{padding:18px 48px;font-size:18px}
.btn-ghost{padding:14px 36px;border-radius:12px;font-weight:500;font-size:16px;text-decoration:none;border:1px solid rgba(148,163,184,.3);color:#94a3b8;transition:all .3s}
.btn-ghost:hover{border-color:#67e8f9;color:#67e8f9}
.xfade-enter-active{transition:opacity .3s,transform .3s}.xfade-leave-active{transition:opacity .15s}.xfade-enter-from{opacity:0;transform:translateX(20px)}.xfade-leave-to{opacity:0}
.wfade-enter-active{transition:opacity .3s,transform .3s}.wfade-leave-active{transition:opacity .15s}.wfade-enter-from{opacity:0;transform:translateX(16px)}.wfade-leave-to{opacity:0}
.st-tags span{padding:6px 16px;border-radius:8px;font-size:12px;font-weight:500;background:rgba(6,182,212,.1);color:#67e8f9;border:1px solid rgba(6,182,212,.15)}

/* ═══ HERO ═══ */
.hero{position:relative;height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;overflow:hidden}
.hero-glow{position:absolute;inset:0;background:radial-gradient(ellipse 80% 55% at 50% 40%,rgba(6,182,212,.12) 0%,transparent 70%),radial-gradient(ellipse 50% 40% at 30% 60%,rgba(99,102,241,.08) 0%,transparent 60%)}
.hero-body{position:relative;z-index:1;opacity:0;transform:translateY(40px) scale(.96);transition:all 1.2s cubic-bezier(.16,1,.3,1)}
.hero-body.visible{opacity:1;transform:none}
.badge{display:inline-block;padding:6px 18px;border-radius:999px;border:1px solid rgba(6,182,212,.3);color:#67e8f9;font-size:13px;font-weight:500;letter-spacing:1px;margin-bottom:28px;background:rgba(6,182,212,.06)}
.hero-title{font-size:clamp(4rem,12vw,8rem);font-weight:800;line-height:1;margin-bottom:20px;background:linear-gradient(135deg,#f1f5f9,#67e8f9 50%,#818cf8);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;letter-spacing:-2px}
.hero-sub{font-size:clamp(1.3rem,3vw,2rem);font-weight:600;color:#cbd5e1;margin-bottom:16px}
.hero-desc{font-size:16px;color:#64748b;line-height:1.8;max-width:520px;margin:0 auto 36px}
.hero-cta{display:flex;gap:16px;justify-content:center}
.scroll-hint{position:absolute;bottom:40px;display:flex;flex-direction:column;align-items:center;gap:8px;opacity:0;transition:opacity 1.5s 1s}
.scroll-hint.visible{opacity:.5}.scroll-hint span{font-size:10px;letter-spacing:3px;color:#475569}
.mouse{width:24px;height:38px;border-radius:12px;border:2px solid #475569;position:relative}
.wheel{width:4px;height:8px;border-radius:2px;background:#475569;position:absolute;left:50%;top:8px;transform:translateX(-50%);animation:wh 2s ease-in-out infinite}
@keyframes wh{0%,100%{opacity:1;top:8px}50%{opacity:.3;top:18px}}

/* ═══ SCROLL-DRIVEN ═══ */
.scroll-track{height:500vh;position:relative}
.scroll-stage{position:sticky;top:0;height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;overflow:hidden}
.st-title{text-align:center;margin-bottom:28px}.st-title h2{font-size:clamp(1.8rem,4vw,2.8rem);font-weight:700;color:#f1f5f9;line-height:1.25}
.st-tags{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;position:absolute;bottom:10vh}
.dp-wrap{will-change:transform,opacity,filter;transform-origin:center}
.dp{width:min(700px,88vw);background:rgba(15,23,42,.85);border:1px solid rgba(51,65,85,.5);border-radius:18px;padding:28px;backdrop-filter:blur(12px);box-shadow:0 30px 80px rgba(0,0,0,.5)}
.dp-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px}
.dp-lbl{font-size:20px;font-weight:700;color:#f1f5f9}
.dp-pct{font-size:48px;font-weight:800;background:linear-gradient(135deg,#22c55e,#67e8f9);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.dp-bar-bg{height:10px;background:rgba(51,65,85,.5);border-radius:5px;margin-bottom:20px;overflow:hidden}
.dp-bar{height:100%;border-radius:5px;background:linear-gradient(90deg,#22c55e,#06b6d4)}
.dp-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.dp-card{background:rgba(30,41,59,.8);border-radius:10px;padding:14px 10px;display:flex;flex-direction:column;align-items:center;gap:8px;border:1px solid transparent}
.dp-card.pass{border-color:rgba(34,197,94,.2)}.dp-card.warn{border-color:rgba(234,179,8,.2)}.dp-card.fail{border-color:rgba(239,68,68,.2)}
.dp-cn{font-size:11px;color:#94a3b8;font-weight:600}.dp-cv{font-size:18px;font-weight:700}
.dp-cv.pass{color:#22c55e}.dp-cv.warn{color:#eab308}.dp-cv.fail{color:#ef4444}

/* ═══ SANITY CHECK ═══ */
.sanity-flow{display:flex;justify-content:center;gap:0;margin-bottom:40px}
.sf-step{text-align:center;padding:24px 28px;position:relative;flex:1;max-width:220px;border-radius:14px;transition:background .4s}
.sf-step.glow{background:rgba(6,182,212,.08)}
.sf-icon{font-size:36px;margin-bottom:10px}
.sf-label{font-size:16px;font-weight:700;color:#f1f5f9;margin-bottom:4px}
.sf-desc{font-size:12px;color:#64748b}
.sf-connector{position:absolute;right:-8px;top:36px;color:#334155;font-size:20px;z-index:1}
.sf-pulse{width:8px;height:8px;border-radius:50%;background:#334155;transition:all .3s}
.sf-pulse.run{background:#06b6d4;box-shadow:0 0 12px rgba(6,182,212,.6);animation:pulse 1s ease-in-out}
@keyframes pulse{0%{transform:scale(1)}50%{transform:scale(1.8)}100%{transform:scale(1)}}

.sanity-log{background:rgba(15,23,42,.7);border:1px solid rgba(51,65,85,.4);border-radius:14px;padding:16px 20px;max-width:800px;margin:0 auto}
.sl-line{display:flex;align-items:center;gap:12px;padding:6px 0;font-size:13px;border-bottom:1px solid rgba(51,65,85,.2)}
.sl-line:last-child{border-bottom:none}
.sl-time{color:#475569;font-family:monospace;font-size:11px;flex-shrink:0}
.sl-badge{padding:2px 8px;border-radius:5px;font-size:10px;font-weight:700;flex-shrink:0}
.sl-badge.ok{background:rgba(34,197,94,.15);color:#4ade80}
.sl-badge.err{background:rgba(239,68,68,.15);color:#f87171}
.sl-badge.warn{background:rgba(234,179,8,.15);color:#fbbf24}
.sl-msg{color:#cbd5e1}

/* ═══ SANITY CHECK IMAGES ═══ */
.sanity-hero-title{font-size:clamp(2.5rem,6vw,4.5rem) !important;letter-spacing:-1px;margin-bottom:48px !important}
.sanity-hero-title::after{width:80px}
.sc-layout{display:flex;align-items:flex-start;gap:40px;max-width:1060px;margin:0 auto}
.sc-btn-side{flex:0 0 auto;padding-top:80px}
.sc-fake-btn{padding:14px 28px;background:linear-gradient(135deg,#059669,#0d9488);border-radius:12px;color:#fff;font-weight:700;font-size:16px;box-shadow:0 8px 30px rgba(5,150,105,.4);white-space:nowrap;cursor:pointer;transition:all .3s;user-select:none}
.sc-fake-btn:hover{transform:scale(1.05);box-shadow:0 12px 40px rgba(5,150,105,.5)}
.sc-fake-btn.clicked{background:linear-gradient(135deg,#047857,#0f766e);box-shadow:0 4px 16px rgba(5,150,105,.2);transform:scale(.97)}
.sc-placeholder{display:flex;flex-direction:column;align-items:center;justify-content:center;height:300px;color:#334155;font-size:15px;gap:8px}
.sc-placeholder span{font-size:32px;animation:bounce 2s ease-in-out infinite}
@keyframes bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
.report-reveal-enter-active{transition:all 1.2s cubic-bezier(.16,1,.3,1)}
.report-reveal-leave-active{transition:all .4s ease}
.report-reveal-enter-from{opacity:0;transform:translateY(40px) scale(.96);filter:blur(8px)}
.report-reveal-leave-to{opacity:0;filter:blur(4px)}
.sc-main-wrap{flex:1;min-width:0}
.sc-main-img{width:100%;border-radius:16px;box-shadow:0 24px 80px rgba(0,0,0,.5);-webkit-mask-image:linear-gradient(to bottom,#000 75%,transparent 100%);mask-image:linear-gradient(to bottom,#000 75%,transparent 100%)}

/* ═══ TOPOLOGY ═══ */
.topo-fp{padding:80px 40px}
.topo-split{display:grid;grid-template-columns:1.5fr 1fr;gap:40px;align-items:center}
.topo-canvas-lg{position:relative;background:rgba(15,23,42,.7);border:1px solid rgba(51,65,85,.5);border-radius:18px;padding:16px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.4),inset 0 1px 0 rgba(255,255,255,.03)}
.topo-svg-demo{width:100%;height:auto;display:block}
.topo-link{transition:stroke .4s,stroke-width .3s,opacity .4s}
.topo-circle{transition:r .25s,fill .4s,opacity .4s}
.sel-ring{animation:selP 1.5s ease-in-out infinite}
@keyframes selP{0%,100%{opacity:.6}50%{opacity:.3}}
.topo-tip{pointer-events:none}
.topo-mode-tag{position:absolute;bottom:12px;left:50%;transform:translateX(-50%);padding:5px 16px;border-radius:8px;font-size:11px;font-weight:600;background:rgba(6,182,212,.12);color:#67e8f9;border:1px solid rgba(6,182,212,.2)}
.topo-right .label{margin-bottom:4px}
.topo-heading{font-size:clamp(1.6rem,3vw,2.2rem);font-weight:700;color:#f1f5f9;margin-bottom:24px;line-height:1.3}
.tf-list{display:flex;flex-direction:column;gap:8px}
.tf-card{display:flex;gap:12px;padding:12px 16px;border-radius:12px;border:1px solid rgba(51,65,85,.3);background:rgba(15,23,42,.4);cursor:pointer;transition:all .3s}
.tf-card:hover{background:rgba(30,41,59,.6)}.tf-card.active{background:rgba(6,182,212,.1);border-color:rgba(6,182,212,.3)}
.tf-icon{font-size:20px;flex-shrink:0;margin-top:2px}
.tf-text h4{font-size:13px;font-weight:700;color:#f1f5f9;margin-bottom:2px}.tf-text p{font-size:11px;color:#64748b}
.tf-card.active .tf-text h4{color:#67e8f9}

/* ═══ EXPECTATIONS ═══ */
.exp-tabs{display:flex;justify-content:center;gap:8px;margin-bottom:32px}
.exp-tabs button{padding:10px 24px;border-radius:10px;font-size:14px;font-weight:600;background:rgba(30,41,59,.6);color:#94a3b8;border:1px solid transparent;cursor:pointer;transition:all .25s}
.exp-tabs button:hover{color:#e2e8f0}.exp-tabs button.active{background:rgba(6,182,212,.15);color:#67e8f9;border-color:rgba(6,182,212,.3)}
.exp-showcase{display:flex;flex-direction:column;gap:16px;max-width:700px;margin:0 auto}
.exp-card-lg{background:rgba(15,23,42,.7);border:1px solid rgba(51,65,85,.4);border-radius:16px;padding:20px 24px;transition:border-color .3s;box-shadow:0 8px 30px rgba(0,0,0,.25),inset 0 1px 0 rgba(255,255,255,.03)}
.exp-card-lg.pass{border-color:rgba(34,197,94,.25)}.exp-card-lg.fail{border-color:rgba(239,68,68,.25)}
.ec-device{margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid rgba(51,65,85,.3);font-size:15px;font-weight:600;color:#f1f5f9}
.ec-body{display:flex;align-items:center;gap:16px;margin-bottom:8px}
.ec-col{flex:1}.ec-col-hd{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#64748b;margin-bottom:6px}
.ec-col-hd.actual{color:#06b6d4}
.ec-val{font-size:13px;color:#cbd5e1;font-family:monospace;line-height:1.6}
.ec-arrow{flex-shrink:0}
.ec-result{font-size:15px;font-weight:700;flex-shrink:0;padding:6px 14px;border-radius:8px}
.ec-result.pass{background:rgba(34,197,94,.1);color:#4ade80}.ec-result.fail{background:rgba(239,68,68,.1);color:#f87171}
.ec-reason{font-size:12px;color:#f87171;opacity:.8;margin-top:4px}

/* ═══ CASES ═══ */
.case-flow{display:flex;justify-content:center;gap:0;margin-bottom:40px;flex-wrap:wrap}
.cf-step{display:flex;flex-direction:column;align-items:center;gap:6px;padding:12px 20px;position:relative}
.cf-dot{font-size:28px}.cf-label{font-size:12px;font-weight:600;color:#94a3b8}
.cf-step.err .cf-label{color:#f87171}.cf-step.ok .cf-label{color:#4ade80}.cf-step.active .cf-label{color:#67e8f9}
.cf-arrow{position:absolute;right:-6px;top:18px;color:#334155;font-size:18px;font-weight:700}
.case-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;max-width:900px;margin:0 auto}
.cc-item{background:rgba(15,23,42,.7);border:1px solid rgba(51,65,85,.4);border-radius:14px;padding:18px 20px;box-shadow:0 8px 24px rgba(0,0,0,.2),inset 0 1px 0 rgba(255,255,255,.03)}
.cc-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.cc-badge{padding:3px 10px;border-radius:6px;font-size:11px;font-weight:600}
.cc-badge.inp{background:rgba(59,130,246,.2);color:#60a5fa}.cc-badge.asg{background:rgba(234,179,8,.2);color:#fbbf24}
.cc-badge.res{background:rgba(34,197,94,.2);color:#4ade80}
.cc-summary{font-size:13px;color:#cbd5e1;margin-bottom:6px;line-height:1.5}.cc-meta{font-size:12px;color:#64748b}

/* ═══ WIZARD ═══ */
.wiz-showcase{max-width:560px;margin:0 auto}
.wiz-steps.four{display:flex;margin-bottom:24px}
.wiz-step{flex:1;display:flex;flex-direction:column;align-items:center;gap:8px;position:relative;cursor:pointer}
.wiz-step::after{content:'';position:absolute;top:14px;left:55%;width:90%;height:2px;background:rgba(51,65,85,.5);z-index:0}
.wiz-step:last-child::after{display:none}.wiz-step.done::after{background:#06b6d4}
.wiz-dot{width:28px;height:28px;border-radius:50%;background:rgba(51,65,85,.6);color:#94a3b8;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;z-index:1;transition:all .4s}
.wiz-step.active .wiz-dot{background:#06b6d4;color:#fff;box-shadow:0 0 12px rgba(6,182,212,.4)}
.wiz-step.done .wiz-dot{background:#22c55e;color:#fff}
.wiz-step span{font-size:11px;color:#64748b;font-weight:500}.wiz-step.active span{color:#67e8f9}.wiz-step.done span{color:#4ade80}
.wiz-panel{background:rgba(15,23,42,.7);border:1px solid rgba(51,65,85,.4);border-radius:16px;padding:24px;min-height:200px}
.wp-info{display:flex;flex-direction:column;gap:0}
.wp-row{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid rgba(51,65,85,.3);font-size:14px;color:#94a3b8}
.wp-row:last-child{border-bottom:none}.wp-row span:last-child{color:#f1f5f9;font-weight:600}
.wp-loading{display:flex;flex-direction:column;align-items:center;gap:14px;padding:24px 0}
.wiz-spinner-lg{position:relative;width:48px;height:48px}
.wiz-spin-ring{position:absolute;inset:0;border-radius:50%;border:3px solid rgba(6,182,212,.15);border-top-color:#06b6d4;animation:spin .9s linear infinite}
.wiz-spin-ring.inner{inset:8px;border-top-color:#818cf8;animation-direction:reverse;animation-duration:.7s}
@keyframes spin{to{transform:rotate(360deg)}}
.wiz-pbar-bg{height:6px;background:rgba(51,65,85,.5);border-radius:3px;overflow:hidden;width:200px}
.wiz-pbar{height:100%;border-radius:3px;background:linear-gradient(90deg,#06b6d4,#22c55e)}
.wp-review{display:flex;flex-direction:column;gap:12px}
.wp-review-hd{display:flex;justify-content:space-between;font-size:13px}
.wiz-sel-badge{padding:3px 10px;border-radius:6px;font-size:11px;background:rgba(6,182,212,.15);color:#67e8f9}
.wp-table{border:1px solid rgba(51,65,85,.4);border-radius:10px;overflow:hidden}
.wpt-hd{display:grid;grid-template-columns:30px 1.5fr .8fr .6fr .6fr;padding:6px 10px;background:rgba(30,41,59,.6);font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase}
.wpt-row{display:grid;grid-template-columns:30px 1.5fr .8fr .6fr .6fr;padding:5px 10px;font-size:12px;border-top:1px solid rgba(51,65,85,.3);align-items:center}
.wpt-row.checked{background:rgba(6,182,212,.06)}
.wiz-chk{color:#64748b;font-size:14px}.wpt-row.checked .wiz-chk{color:#06b6d4}
.wiz-tag{padding:1px 6px;border-radius:4px;font-size:10px;background:rgba(6,182,212,.15);color:#67e8f9}
.wp-done{display:flex;flex-direction:column;align-items:center;gap:14px;padding:16px 0}
.wiz-check-svg{width:56px;height:56px}
.wiz-check-path{stroke-dasharray:50;stroke-dashoffset:50;animation:checkDraw .6s ease forwards .2s}
@keyframes checkDraw{to{stroke-dashoffset:0}}
.wp-done-num{font-size:48px;font-weight:800;color:#22c55e}.wp-done-lbl{font-size:16px;color:#94a3b8}
.wp-done-row{font-size:14px;color:#64748b;display:flex;gap:16px}.wp-done-row span{font-weight:700}
.wiz-actions{display:flex;gap:10px;justify-content:flex-end;margin-top:16px}
.wiz-btn{padding:10px 24px;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;transition:all .25s;border:none}
.wiz-btn.fill{background:linear-gradient(135deg,#06b6d4,#6366f1);color:#fff;box-shadow:0 2px 12px rgba(6,182,212,.25)}
.wiz-btn.fill:hover{transform:translateY(-1px)}.wiz-btn.ghost{background:rgba(51,65,85,.5);color:#94a3b8}

/* ═══ CASE DEMO ═══ */
.cases-fp{padding:80px 48px}
.case-demo{display:grid;grid-template-columns:1.1fr 1fr;gap:40px;max-width:960px;margin:0 auto;align-items:start}

.cd-card{background:rgba(15,23,42,.8);border:1px solid rgba(51,65,85,.5);border-radius:18px;padding:24px 28px;box-shadow:0 20px 60px rgba(0,0,0,.4),inset 0 1px 0 rgba(255,255,255,.03)}
.cd-card-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;font-size:16px;font-weight:700;color:#f1f5f9}
.cd-ping{font-size:13px;font-weight:600}.cd-ping.ok{color:#4ade80}.cd-ping.down{color:#f87171;animation:blink2 1.5s infinite}
@keyframes blink2{0%,100%{opacity:1}50%{opacity:.4}}
.cd-status-row{display:flex;align-items:center;gap:12px;margin-bottom:12px}
.cd-status-badge{padding:5px 14px;border-radius:8px;font-size:13px;font-weight:700}
.cd-status-badge.unassigned{background:rgba(100,116,139,.2);color:#94a3b8}
.cd-status-badge.assigned{background:rgba(234,179,8,.2);color:#fbbf24}
.cd-status-badge.inprogress{background:rgba(59,130,246,.2);color:#60a5fa}
.cd-status-badge.resolved{background:rgba(34,197,94,.2);color:#4ade80}
.cd-assignee{font-size:13px;color:#94a3b8}
.cd-changes{display:flex;flex-direction:column;gap:6px;margin-bottom:12px}
.cd-change{display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:8px;font-size:12px;font-family:monospace}
.cd-change.err{background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.2)}
.cd-change.ok{background:rgba(34,197,94,.08);border:1px solid rgba(34,197,94,.2)}
.cd-change-attr{font-weight:700;color:#f1f5f9;min-width:36px}
.cd-change-from{color:#64748b}.cd-change-arrow{color:#475569}
.cd-change.err .cd-change-to{color:#f87171;font-weight:600}
.cd-change.ok .cd-change-to{color:#4ade80;font-weight:600}
.cd-summary{font-size:13px;color:#cbd5e1;margin-bottom:12px;padding:10px 14px;background:rgba(30,41,59,.5);border-radius:10px;line-height:1.6}
.cd-notes{display:flex;flex-direction:column;gap:6px;margin-bottom:14px}
.cd-note{padding:8px 12px;background:rgba(30,41,59,.4);border-radius:8px;font-size:12px;display:flex;gap:8px}
.cd-note-author{color:#67e8f9;font-weight:600;flex-shrink:0}
.cd-note-text{color:#94a3b8}
.cd-actions{display:flex;gap:8px;justify-content:flex-end}
.cd-btn{padding:8px 18px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;transition:all .25s;border:none}
.cd-btn.primary{background:linear-gradient(135deg,#06b6d4,#6366f1);color:#fff;box-shadow:0 2px 12px rgba(6,182,212,.25)}
.cd-btn.primary:hover{transform:translateY(-1px)}
.cd-btn.ghost{background:rgba(51,65,85,.5);color:#94a3b8}
.cd-btn.ghost:hover{color:#e2e8f0}
.cd-btn.disabled{background:rgba(51,65,85,.3);color:#475569;cursor:default;animation:pulse2 2s infinite}
@keyframes pulse2{0%,100%{opacity:.6}50%{opacity:1}}

.cd-timeline{background:rgba(15,23,42,.6);border:1px solid rgba(51,65,85,.4);border-radius:18px;padding:24px 28px}
.cd-tl-title{font-size:16px;font-weight:700;color:#f1f5f9;margin-bottom:16px}
.cd-tl-items{display:flex;flex-direction:column;gap:0;margin-bottom:20px}
.cd-tl-item{display:flex;gap:14px;padding:10px 0;position:relative}
.cd-tl-item::before{content:'';position:absolute;left:7px;top:30px;bottom:-10px;width:2px;background:rgba(51,65,85,.4)}
.cd-tl-item:last-child::before{display:none}
.cd-tl-item.done::before{background:#22c55e}
.cd-tl-item.active::before{background:#06b6d4}
.cd-tl-dot{width:16px;height:16px;border-radius:50%;flex-shrink:0;margin-top:2px;background:rgba(51,65,85,.6);transition:background .4s}
.cd-tl-item.err .cd-tl-dot{background:#ef4444}
.cd-tl-item.active .cd-tl-dot{background:#06b6d4;box-shadow:0 0 10px rgba(6,182,212,.4)}
.cd-tl-item.done .cd-tl-dot{background:#22c55e}
.cd-tl-item.ok .cd-tl-dot{background:#22c55e;box-shadow:0 0 10px rgba(34,197,94,.4)}
.cd-tl-label{font-size:13px;font-weight:700;color:#f1f5f9}
.cd-tl-item.err .cd-tl-label{color:#f87171}
.cd-tl-item.ok .cd-tl-label{color:#4ade80}
.cd-tl-item.active .cd-tl-label{color:#67e8f9}
.cd-tl-item.done .cd-tl-label{color:#94a3b8}
.cd-tl-desc{font-size:11px;color:#64748b;margin-top:2px}
.cd-controls{display:flex;gap:8px;justify-content:flex-end}
.cd-ctrl-btn{padding:8px 18px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;border:none;background:rgba(51,65,85,.5);color:#94a3b8;transition:all .25s}
.cd-ctrl-btn:hover{color:#e2e8f0;background:rgba(51,65,85,.7)}
.cd-ctrl-btn.primary{background:linear-gradient(135deg,#06b6d4,#6366f1);color:#fff}
.cd-ctrl-btn.primary:hover{transform:translateY(-1px)}

/* ═══ IMAGE HERO (full-width screenshot) ═══ */
.img-hero{width:100%;max-width:960px;margin:0 auto}
.img-hero-main{width:100%;border-radius:16px;box-shadow:0 24px 80px rgba(0,0,0,.5);-webkit-mask-image:linear-gradient(to bottom,#000 70%,transparent 100%);mask-image:linear-gradient(to bottom,#000 70%,transparent 100%)}

/* ═══ STATS ═══ */
.stats-hl{font-size:clamp(2.2rem,5vw,3.6rem);font-weight:800;text-align:center;margin-bottom:64px;color:#f1f5f9}
.stats-mega{display:grid;grid-template-columns:repeat(3,1fr);gap:32px}
.sm-item{text-align:center;padding:32px 16px}
.sm-val{font-size:clamp(3.5rem,7vw,5rem);font-weight:800;line-height:1;margin-bottom:12px;background:linear-gradient(135deg,#06b6d4,#818cf8);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;filter:drop-shadow(0 0 20px rgba(6,182,212,.15))}
.sm-lbl{font-size:16px;font-weight:700;color:#f1f5f9;margin-bottom:4px}
.sm-desc{font-size:13px;color:#64748b}

/* ═══ CTA ═══ */
.cta-bg{background:rgba(0,0,0,.15)}
.cta-title{font-size:clamp(2rem,5vw,3.2rem);font-weight:800;text-align:center;color:#f1f5f9;margin-bottom:12px}
.cta-sub{font-size:18px;color:#64748b;text-align:center;margin-bottom:40px}
.text-sm{font-size:.875rem}.text-xs{font-size:.75rem}
</style>
