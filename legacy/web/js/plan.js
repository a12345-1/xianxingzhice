/* 行程页：渲染 / 改一项 / 换一个 / 重排一天 / 预算联动 */
let TRIP_ID = null;
let DATA = null;

const YUAN = (n) => "￥" + (Number(n) || 0).toFixed(0);
const RISK = { high: "需处理", medium: "建议调整", low: "提醒" };

async function load() {
  TRIP_ID = qs("trip");
  if (!TRIP_ID) { location.href = "/"; return; }
  try {
    DATA = await API.get(TRIP_ID);
    render();
  } catch (e) {
    document.getElementById("days").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
}

function render() {
  const { trip, need, days, budget, conflicts, tips } = DATA;

  document.getElementById("summary").innerHTML = `
    <span class="pill">${esc(trip.city)}</span>
    <span class="pill">${days.length} 天</span>
    <span class="pill">${esc(need.pace === "slow" ? "慢逛" : need.pace === "fast" ? "多逛" : "正常")}</span>
    <span class="pill" style="margin-left:auto">${YUAN(budget.total)}</span>`;

  renderConflicts(conflicts);
  renderDays(days);
  renderBudget(budget);
  renderTips(tips);

  document.getElementById("btn-group").href = `/trip.html?trip=${TRIP_ID}`;
}

function renderConflicts(list) {
  const box = document.getElementById("conflicts");
  if (!list || !list.length) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="card"><h2>发现 ${list.length} 处需要留意</h2>` +
    list.slice(0, 6).map((c) => `
      <div class="conflict">
        <span class="lv ${c.level}">${RISK[c.level] || ""}</span>
        <div>
          <p>${esc(c.reason)}</p>
          <small>${esc(c.fix || "")}</small>
        </div>
      </div>`).join("") + `</div>`;
}

function renderDays(days) {
  const box = document.getElementById("days");
  if (!days.length) { box.innerHTML = `<div class="empty">这一天还没安排</div>`; return; }
  box.innerHTML = days.map((d) => `
    <section class="day">
      <header>
        <strong>第 ${d.day} 天</strong>
        <span>${esc(d.theme || "自由安排")} · ${d.items.length} 个安排</span>
      </header>
      ${d.items.map(itemRow).join("")}
      <footer>
        <button class="btn link" data-act="regen" data-day="${d.day}">重排这一天</button>
      </footer>
    </section>`).join("");
}

function itemRow(it) {
  const free = Number(it.cost) === 0;
  return `
    <div class="item ${it.type === "hotel" ? "hotel" : ""}" data-id="${it.id}">
      <time>${esc(it.start_time)}</time>
      <div class="name">
        <b title="${esc(it.name)}">${esc(it.name)}</b>
        <small>${it.duration_min > 0 ? it.duration_min + " 分钟 · " : ""}${free ? "免费" : YUAN(it.cost)}</small>
      </div>
      <div class="ops">
        <button data-act="up" title="上移">↑</button>
        <button data-act="down" title="下移">↓</button>
        <button data-act="swap" title="换一个">换</button>
        <button data-act="del" title="删除">删</button>
      </div>
    </div>`;
}

function renderBudget(b) {
  const pct = b.limit ? Math.min(100, (b.total / b.limit) * 100) : 0;
  const cats = Object.entries(b.by_category || {}).map(([k, v]) => `<div class="budget-line"><span>${esc(k)}</span><span>${YUAN(v)}</span></div>`).join("");
  document.getElementById("budget").innerHTML = `
    <div class="card">
      <h2>预算</h2>
      <div class="budget-line"><span class="budget-total ${b.over_budget ? "over" : ""}">${YUAN(b.total)}</span>
        <span class="muted">${b.limit ? "预算 " + YUAN(b.limit) : "未设上限"} · 人均 ${YUAN(b.per_person)}</span></div>
      ${b.limit ? `<div class="bar ${b.over_budget ? "warn" : ""}"><i style="width:${pct}%"></i></div>` : ""}
      ${b.over_budget ? `<p class="hint over">超出预算 ${YUAN(b.gap)}，可以删一个收费点，或点“换一个”</p>` : ""}
      ${cats}
    </div>`;
}

function renderTips(t) {
  const w = t.weather || {};
  document.getElementById("tips").innerHTML = `
    <div class="card">
      <h2>出行贴士</h2>
      <p class="muted">${esc(w.text || "")} ${w.low}—${w.high}℃ · 降雨概率 ${w.rain}%</p>
      <div class="budget-line"><span>穿衣</span><span>${esc(t.clothing)}</span></div>
      <div style="margin-top:8px">${(t.packing || []).map((x) => `<span class="tag">${esc(x)}</span>`).join("")}</div>
      ${(t.pitfalls || []).map((x) => `<p class="hint">· ${esc(x)}</p>`).join("")}
      <p class="hint">${esc(t.updated || "")}</p>
    </div>`;
}

/* ---------------------------------------------------------------- 交互 */
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const act = btn.dataset.act;
  const row = btn.closest(".item");
  const id = row ? row.dataset.id : null;
  btn.disabled = true;
  try {
    let data;
    if (act === "up" || act === "down") {
      data = await API.move(TRIP_ID, id, act === "up" ? "up" : "down");
    } else if (act === "swap") {
      data = await API.swap(TRIP_ID, id);
      toast("换好了");
    } else if (act === "del") {
      data = await API.delItem(TRIP_ID, id);
      toast("已删除，预算已更新");
    } else if (act === "regen") {
      data = await API.regenDay(TRIP_ID, btn.dataset.day);
      toast(`第 ${btn.dataset.day} 天已重排，其他天没动`);
    }
    if (data) { DATA = data; render(); }
  } catch (err) {
    toast(err.message || "操作失败");
  } finally {
    btn.disabled = false;
  }
});

document.addEventListener("DOMContentLoaded", async () => {
  await load();
  document.getElementById("btn-share").onclick = async () => {
    try {
      const r = await API.share(TRIP_ID);
      const url = location.origin + r.url;
      try { await navigator.clipboard.writeText(url); toast("分享链接已复制"); }
      catch (e) { prompt("复制这个链接", url); }
    } catch (e) { toast(e.message); }
  };
  try {
    const h = await API.health();
    document.getElementById("mock-tip").textContent = h.mock ? "本地规则模式" : "模型模式";
  } catch (e) { /* ignore */ }
});
