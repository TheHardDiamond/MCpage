<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { withBase } from 'vitepress'
import PixelCard from './components/ui/PixelCard.vue'
import config from '../../src/data/site.json'
import chronicle from '../../src/data/chronicle.json'
import archive from '../../src/data/archive.json'

const props = defineProps({ page: String })
const DAY = 86400000
const labels = { ok: '正常', degraded: '部分异常', down: '全天中断', unknown: '无数据' }
const days = value => Date.parse(value + 'T00:00:00Z')
const date = value => new Date(value).toISOString().slice(0, 10)
const dateTime = value => new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
const cutoff = archive.cutoff ? date(Date.parse(archive.cutoff) + 8 * 3600000) : ''
const firstDay = archive.services.flatMap(service => Object.keys(service.days)).sort()[0] || cutoff
const byDate = [...chronicle].sort((a, b) => b.date.localeCompare(a.date))
const years = [...new Set(byDate.map(item => item.date.slice(0, 4)))]
const year = ref('')
const month = ref('')
const months = computed(() => [...new Set(byDate.filter(item => !year.value || item.date.startsWith(year.value)).map(item => item.date.slice(0, 7)))])
const cards = computed(() => byDate.filter(item => item.date.startsWith(month.value || year.value)))
const offset = ref(0)
const period = computed(() => cutoff ? Array.from({ length: 90 }, (_, i) => date(days(cutoff) - (offset.value * 90 + 89 - i) * DAY)) : [])
const calendarMonth = ref(cutoff.slice(0, 7))
const jumpYear = ref(calendarMonth.value.slice(0, 4))
const jumpMonth = ref(calendarMonth.value.slice(5))
const jumpError = ref('')
function setCalendarMonth(value) {
  if (value < '2020-01' || value > '2099-12') return
  calendarMonth.value = value
  jumpYear.value = value.slice(0, 4)
  jumpMonth.value = value.slice(5)
  jumpError.value = ''
}
function jumpToMonth() {
  const year = String(jumpYear.value).trim()
  const month = String(jumpMonth.value).trim()
  if (!/^\d{4}$/.test(year) || +year < 2020 || +year > 2099 ||
      !/^\d{1,2}$/.test(month) || +month < 1 || +month > 12) {
    jumpError.value = '请输入 2020–2099 年和 1–12 月。'
    return
  }
  setCalendarMonth(year + '-' + month.padStart(2, '0'))
}
const calendar = computed(() => {
  if (!calendarMonth.value) return []
  const start = days(calendarMonth.value + '-01')
  const cursor = new Date(start)
  const padding = cursor.getUTCDay()
  cursor.setUTCMonth(cursor.getUTCMonth() + 1)
  return Array.from({ length: Math.ceil((padding + (cursor.getTime() - start) / DAY) / 7) * 7 },
    (_, i) => date(start + (i - padding) * DAY))
})
function changeMonth(delta) {
  const cursor = new Date(days(calendarMonth.value + '-01'))
  cursor.setUTCMonth(cursor.getUTCMonth() + delta)
  setCalendarMonth(date(cursor).slice(0, 7))
}
function changePeriod(delta) {
  offset.value += delta
  setCalendarMonth(period.value.at(-1).slice(0, 7))
}
const dayDetail = ref('')
const dialog = ref()
const tooltip = ref(null)
function showHint(event, text) {
  const rect = event.currentTarget.getBoundingClientRect()
  tooltip.value = { text, x: Math.max(8, Math.min(rect.left, window.innerWidth - 238)), y: Math.min(rect.bottom + 7, window.innerHeight - 72) }
}
function hideHint() { tooltip.value = null }
function rate(service) {
  const rows = period.value.map(key => day(service, key))
  if (!rows.length || rows.some((row, i) => row.coveredSeconds !== (
    period.value[i] === cutoff ? (Date.parse(archive.cutoff) + 8 * 3600000 - days(cutoff)) / 1000 : 86400
  ) || !Number.isFinite(row.uptimeSeconds))) return ''
  const sum = field => rows.reduce((total, row) => total + row[field], 0)
  return sum('coveredSeconds') ? (100 * sum('uptimeSeconds') / sum('coveredSeconds')).toFixed(2) + '% 可用性' : ''
}
function describe(service, key) {
  const value = day(service, key)
  return [key, labels[value.state], ...value.events.map(event => event.title)].join(' · ')
}
function openLinkedStory() {
  const hash = window.location.hash
  if (!/^#issue-\d+$/.test(hash)) return
  const story = document.getElementById(hash.slice(1))
  if (story) story.open = true
}
function day(service, key) { return service.days[key] || { state: 'unknown', events: [] } }
function calendarLabel(key) {
  return [key, ...archive.services.flatMap(service => [
    service.name + '：' + labels[day(service, key).state],
    ...day(service, key).events.map(event => event.title),
  ])].join(' · ')
}
function openDay(key) {
  hideHint()
  dayDetail.value = key
  dialog.value.showModal()
}
function approved(id) { return byDate.some(item => item.id === id) }

const servers = ref([])
const apiError = ref(false)
const skinChecks = ref([])
const hasStatusSource = Boolean(config.mcApi || config.statusSnapshot)
const cooldowns = ref({})
const pending = ref({})
const now = ref(0)
let refreshTimer, clockTimer
function merge(server) {
  const expires = Date.now() + (server.retryAfter ?? 0) * 1000
  cooldowns.value[server.id] = Math.max(cooldowns.value[server.id] || 0, expires)
  const previous = servers.value.find(item => item.id === server.id)
  if (previous?.checkedAt && (!server.checkedAt || Date.parse(previous.checkedAt) > Date.parse(server.checkedAt))) return
  servers.value = [...servers.value.filter(item => item.id !== server.id), server].sort((a, b) => a.id.localeCompare(b.id))
}
function remaining(id) { return Math.max(0, Math.ceil(((cooldowns.value[id] || 0) - now.value) / 1000)) }
async function load() {
  if (!hasStatusSource || document.hidden) return
  try {
    const response = await fetch(config.mcApi ? config.mcApi + '/api/servers' : config.statusSnapshot, {
      cache: 'no-store', signal: AbortSignal.timeout(10000),
    })
    if (!response.ok) throw new Error()
    const snapshot = await response.json()
    for (const server of (config.mcApi ? snapshot : snapshot.servers)) merge(server)
    if (!config.mcApi) skinChecks.value = snapshot.http
    apiError.value = false
  } catch { apiError.value = true }
}
async function refresh(id) {
  if (pending.value[id] || remaining(id)) return
  pending.value[id] = true
  try {
    const response = await fetch(config.mcApi + '/api/servers/' + encodeURIComponent(id) + '/refresh', {
      method: 'POST', signal: AbortSignal.timeout(12000),
    })
    if (response.status === 429) {
      cooldowns.value[id] = Date.now() + (await response.json()).retryAfter * 1000
    } else {
      if (!response.ok) throw new Error()
      const server = await response.json()
      merge(server)
      if (server.busy) setTimeout(load, 5500)
    }
    apiError.value = false
  } catch { apiError.value = true }
  finally { pending.value[id] = false }
}
onMounted(() => {
  if (props.page === 'chronicle') openLinkedStory()
  if (props.page !== 'status' || !hasStatusSource) return
  now.value = Date.now()
  load()
  clockTimer = setInterval(() => { now.value = Date.now() }, 250)
  refreshTimer = setInterval(load, 300000)
  document.addEventListener('visibilitychange', load)
})
onUnmounted(() => {
  clearInterval(clockTimer)
  clearInterval(refreshTimer)
  document.removeEventListener('visibilitychange', load)
})
</script>

<template>
  <template v-if="page === 'home'">
    <section class="hero" :style="{ '--hero-image': 'url(' + withBase('/background/15.jpg') + ')' }">
      <img v-if="config.legacyLogo" :src="withBase(config.legacyLogo)" alt="">
      <h1>服务器纪念站</h1>
      <p>{{ config.welcome || '记录服务器里发生过的事。' }}</p>
      <a class="pixel-link" :href="withBase('/chronicle.html')">翻阅纪事</a>
    </section>
    <section class="entries" aria-label="站点入口">
      <a v-for="entry in [['纪事','chronicle','翻看社区语录与截图'],['服务状态','status','查看服务器与皮肤站存档'],['Mod Wiki','wiki','查阅旧版模组文档']]" :key="entry[1]" :href="withBase('/' + entry[1] + '.html')">
        <PixelCard><h2>{{ entry[0] }}</h2><p>{{ entry[2] }}</p></PixelCard>
      </a>
    </section>
    <p v-if="config.legacyLinks.length" class="legacy"><a v-for="link in config.legacyLinks" :key="link.url" :href="link.url">{{ link.label }}</a></p>
  </template>

  <section v-else-if="page === 'chronicle'">
    <h1>纪事</h1>
    <div v-if="byDate.length" class="filters">
      <label>年份 <select v-model="year" @change="month = ''"><option value="">全部</option><option v-for="value in years" :key="value">{{ value }}</option></select></label>
      <label>月份 <select v-model="month"><option value="">全部</option><option v-for="value in months" :key="value">{{ value }}</option></select></label>
    </div>
    <p v-else>暂无公开纪事。</p>
    <details v-for="item in cards" :id="'issue-' + item.id" :key="item.id" class="chronicle">
      <summary><time :datetime="item.date">{{ item.date }}</time><strong>{{ item.quote }}</strong></summary>
      <div class="story">
        <p>{{ item.body }}</p>
        <img v-for="(image, index) in item.images" :key="image.src" :src="withBase(image.src)" :alt="image.alt || '纪事截图 ' + (index + 1)" loading="lazy">
      </div>
    </details>
  </section>

  <section v-else-if="page === 'wiki'">
    <h1>Mod Wiki</h1>
    <a v-if="config.wikiUrl" class="pixel-link" :href="config.wikiUrl">详细阅读</a>
    <p v-else>Wiki 链接待补充。</p>
  </section>

  <section v-else>
    <h1>服务状态</h1>
    <div v-if="tooltip" class="floating-hint" aria-hidden="true" :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }">{{ tooltip.text }}</div>
    <section class="panel">
      <h2>Minecraft</h2>
      <button v-if="config.statusSnapshot && !config.mcApi" type="button" @click="load">刷新探测结果</button>
      <p v-if="!hasStatusSource">查询后端待配置。</p>
      <p v-else-if="apiError" role="status">查询后端暂不可用。已加载的结果保留原探测时间。</p>
      <p v-else-if="!servers.length" role="status">暂无服务器结果。</p>
      <article v-for="server in servers" :key="server.id" class="server">
        <img v-if="server.icon" :src="server.icon" alt="" width="48" height="48">
        <span v-else class="server-placeholder" aria-hidden="true">▦</span>
        <div>
          <h3>{{ server.name }}</h3>
          <p>{{ server.status === 'online' ? ('在线人数 ' + (server.online ?? '未知') + ' / ' + (server.max ?? '未知')) : server.status === 'pending' ? '等待首次探测' : '探测无响应' }}</p>
          <p v-if="server.motd" class="motd">{{ server.motd }}</p>
          <details v-if="server.status === 'online'">
            <summary>玩家样本</summary>
            <p>{{ server.sample?.join('、') || '暂无公开名称' }}</p>
            <p v-if="server.anonymous">匿名条目 {{ server.anonymous }} 个，可能包含假人。</p>
          </details>
          <small v-if="server.checkedAt">最后探测 {{ dateTime(server.checkedAt) }}</small>
        </div>
        <button v-if="config.mcApi" :disabled="pending[server.id] || remaining(server.id) > 0" @click="refresh(server.id)">{{ pending[server.id] ? '查询中' : remaining(server.id) ? remaining(server.id) + ' 秒后可查询' : '立即查询' }}</button>
      </article>
    </section>

    <section v-if="config.statusSnapshot && !config.mcApi" class="panel">
      <h2>皮肤站探测</h2>
      <p v-if="!skinChecks.length">等待探测快照。</p>
      <p v-for="check in skinChecks" :key="check.id">
        {{ check.name }} · {{ check.ok ? '正常' : '探测失败' }}{{ check.code ? ' · HTTP ' + check.code : '' }}
        <small> · {{ dateTime(check.checkedAt) }}</small>
      </p>
      <button type="button" @click="load">刷新探测结果</button>
    </section>
    <div class="archive-banner">
      <strong>旧 Upptime 监控存档</strong>
      <p>{{ archive.cutoff ? '存档截止 ' + dateTime(archive.cutoff) : '历史数据待导入。' }}</p>
    </div>
    <template v-if="period.length && archive.services.length">
      <section class="panel">
        <div class="section-heading">
          <h2>系统状态</h2>
          <div class="pager">
            <button aria-label="更早的 90 天" :disabled="period[0] <= firstDay" @click="changePeriod(1)">‹</button>
            <span>{{ period[0] }} 至 {{ period.at(-1) }}</span>
            <button aria-label="更新的 90 天" :disabled="offset === 0" @click="changePeriod(-1)">›</button>
          </div>
        </div>
        <div v-for="service in archive.services" :key="service.id" class="service">
          <div class="section-heading"><h3>{{ service.name }}</h3><span v-if="rate(service)">{{ rate(service) }}</span></div>
          <div class="strip-scroll" @scroll="hideHint"><div class="strip">
            <button v-for="key in period" :key="key" :class="day(service,key).state" :aria-label="service.name + ' ' + describe(service, key)"
              @mouseenter="showHint($event, describe(service,key))" @mouseleave="hideHint" @focus="showHint($event, describe(service,key))" @blur="hideHint" @click="openDay(key)"></button>
          </div></div>
        </div>
        <div class="legend"><span v-for="(label, state) in labels" :key="state"><i :class="state"></i>{{ label }}</span></div>
      </section>
      <section class="panel">
        <div class="section-heading">
          <h2>事件日历</h2>
          <div class="pager">
            <button aria-label="上个月" :disabled="calendarMonth <= '2020-01'" @click="changeMonth(-1)">‹</button>
            <span>{{ calendarMonth }}</span>
            <button aria-label="下个月" :disabled="calendarMonth >= '2099-12'" @click="changeMonth(1)">›</button>
          </div>
        </div>
        <form class="calendar-jump" novalidate @submit.prevent="jumpToMonth">
          <label>年份 <input v-model="jumpYear" type="text" inputmode="numeric" maxlength="4"></label>
          <label>月份 <input v-model="jumpMonth" type="text" inputmode="numeric" maxlength="2"></label>
          <button type="submit">跳转</button>
          <span v-if="jumpError" role="alert">{{ jumpError }}</span>
        </form>
        <div class="calendar">
          <span v-for="weekday in '日一二三四五六'" :key="weekday">{{ weekday }}</span>
          <template v-for="key in calendar" :key="key">
            <button v-if="key.startsWith(calendarMonth)" :aria-label="calendarLabel(key)" :class="{ incident: archive.services.some(service => day(service,key).events.length) }"
              @mouseenter="showHint($event, calendarLabel(key))" @mouseleave="hideHint" @focus="showHint($event, calendarLabel(key))" @blur="hideHint" @click="openDay(key)">
              {{ Number(key.slice(-2)) }}
            </button>
            <span v-else aria-hidden="true"></span>
          </template>
        </div>
      </section>
      <dialog ref="dialog">
        <form method="dialog"><button aria-label="关闭日期详情">关闭</button></form>
        <h2>{{ dayDetail }}</h2>
        <section v-for="service in archive.services" :key="service.id" class="day-service" :data-state="day(service,dayDetail).state">
          <h3>{{ service.name }} · {{ labels[day(service,dayDetail).state] }}</h3>
          <article v-for="(event, index) in day(service,dayDetail).events" :key="index" class="day-event">
            <strong>{{ event.title }}</strong>
            <p v-if="event.start || event.end">{{ event.start ? dateTime(event.start) : '' }}{{ event.end ? ' 至 ' + dateTime(event.end) : '' }}</p>
            <p v-if="event.summary">{{ event.summary }}</p>
            <a v-if="approved(event.chronicleId)" :href="withBase('/chronicle.html#issue-' + event.chronicleId)">查看关联纪事</a>
          </article>
        </section>
      </dialog>
    </template>
  </section>
</template>
