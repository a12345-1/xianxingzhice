/* 渲染工具：行程 / 预算 / 贴士，字段严格取自接口响应 */
const TYPE_LABEL = { spot: "景点", food: "餐饮", hotel: "住宿", transport: "交通", rest: "休息" };
const MODE_LABEL = { walk: "步行", bus: "公交", taxi: "打车", train: "地铁" };
const WALK_LABEL = { light: "轻松", medium: "适中", heavy: "偏累" };
const LEVEL_CLASS = { info: "low", warn: "medium" };
const CAT_COLOR = { ticket: "#4472c4", transport: "#2aa198", food: "#ed7d31", hotel: "#9e6cff" };

function yuan(n) {
  if (n === null || n === undefined) return "—";
  return "￥" + n;
}

function renderSummary(el, trip) {
  const s = trip.summary || {};
  const chips = [
    esc(trip.request.destination || "—"),
    (s.day_count || 0) + " 天",
    yuan(s.total_cost) + (s.budget_limit ? " / " + yuan(s.budget_limit) : ""),
  ];
  el.innerHTML = chips.map((c) => `<span class="pill">${c}</span>`).join("") +
    `<span class="pill" style="margin-left:auto">${{ok:"可用",partial:"部分缺失",error:"生成失败"}[trip.status] || trip.status}</span>`;
}

function renderDays(el, trip, opts = {}) {
  const editable = !!opts.editable;
  if (!trip.days || !trip.days.length) {
    el.innerHTML = `<div class="empty">还没有行程</div>`;
    return;
  }
  el.innerHTML = trip.days.map((d) => {
    const w = d.weather;
    const weather = w
      ? `<span class="tag">${esc(w.condition)} ${w.temp_low}—${w.temp_high}℃ · 雨${w.rain_prob}%</span>`
      : "";
    const walk = d.walk_level ? `<span class="tag">体力 ${WALK_LABEL[d.walk_level] || d.walk_level}</span>` : "";
    return `
    <section class="day" data-day="${d.day_index}">
      <header>
        <strong>第 ${d.day_index} 天</strong>
        <span>${esc(d.weekday || "")} ${weather} ${walk} · ${yuan(d.day_cost)}</span>
      </header>
      ${d.items.length ? d.items.map((it) => itemRow(it, editable)).join("")
                       : `<div class="empty" style="padding:20px">这天还没安排</div>`}
      ${editable ? `<footer><button class="btn link" data-act="rain" data-day="${d.day_index}">下雨了，重排这天</button></footer>` : ""}
    </section>`;
  }).join("");
}

function itemRow(it, editable) {
  const src = it.source === "model" ? `<span class="tag" title="模型推测">推测</span>` : "";
  const hours = it.open_hours ? "" : `<span class="tag" title="开放时间待核实">待核实</span>`;
  const warn = (it.warnings || []).length
    ? `<div class="hint warn">⚠ ${esc(it.warnings.map((w) => w.message).join("；"))}</div>` : "";
  const tr = it.transport && it.transport.from_prev_min
    ? `<small>${MODE_LABEL[it.transport.mode] || it.transport.mode} ${it.transport.from_prev_min} 分钟</small>`
    : "";
  return `
  <div class="item" data-id="${esc(it.item_id)}">
    <time>${esc(it.start_time)}</time>
    <div class="name">
      <b data-act="detail">${esc(it.name)}</b>
      <small>${it.start_time}—${it.end_time} · ${it.duration_min} 分钟 · ${yuan(it.cost)} ${tr} ${src} ${hours}</small>
      ${(it.labels || []).length ? `<div style="margin-top:4px">${(it.labels || []).map((l) => `<span class="tag">${esc(l)}</span>`).join("")}</div>` : ""}
      ${warn}
    </div>
    ${editable ? `<div class="ops">
      <button data-act="up" title="上移">↑</button>
      <button data-act="down" title="下移">↓</button>
      <button data-act="map" title="在地图打开">地图</button>
      <button data-act="del" title="删除">删</button>
    </div>` : ""}
  </div>`;
}

/* 自动调整提示（闭馆顺延/替换） */
function renderAdjustments(el, list) {
  if (!el) return;
  if (!list || !list.length) { el.innerHTML = ""; return; }
  el.innerHTML = `
    <div class="card" style="background:#fff8e6;border-left:3px solid #e0a020">
      <h2 style="margin-bottom:6px">已自动调整</h2>
      ${list.map((a) => `<p class="hint">· ${esc(a.message)}</p>`).join("")}
    </div>`;
}

/* 行程页顶部预算条 */
function renderBudgetBar(el, budget, people) {
  if (!budget) { el.innerHTML = ""; return; }
  const pct = budget.limit ? Math.min(100, Math.round(budget.total / budget.limit * 100)) : 0;
  el.innerHTML = `
    <div class="budget-line">
      <b>预算 ${budget.limit ? yuan(budget.limit) : "不限"} · 已用 ${yuan(budget.total)}</b>
      <span class="muted">${people} 人 · 人均 ${yuan(budget.per_person)}${
        budget.limit ? " · 剩余 " + yuan(Math.max(budget.limit - budget.total, 0)) : ""}</span>
    </div>
    ${budget.limit ? `<div class="bar ${budget.over_budget ? "warn" : ""}"><i style="width:${pct}%"></i></div>` : ""}
    ${budget.over_budget ? `<p class="hint over">超出 ${yuan(budget.over_amount)}</p>` : ""}`;
}

function renderBudget(el, budget) {
  if (!budget) { el.innerHTML = ""; return; }
  const pct = budget.limit ? Math.min(100, Math.round(budget.total / budget.limit * 100)) : 0;
  const total = budget.total || 1;
  const stack = (budget.categories || [])
    .filter((c) => c.amount > 0)
    .map((c) => `<span style="width:${(c.amount / total * 100).toFixed(1)}%;background:${CAT_COLOR[c.key] || "#c9cdd4"}"></span>`)
    .join("");
  const cats = (budget.categories || []).map((c) => `
    <div class="budget-line ${c.over ? "over-soft" : ""}">
      <span><i class="dot" style="background:${CAT_COLOR[c.key] || "#c9cdd4"}"></i>${esc(c.label)}</span>
      <span>${yuan(c.amount)} <small>${Math.round((c.ratio || 0) * 100)}%</small></span>
    </div>`).join("");
  const sug = (budget.suggestions || []).map((s) => `<p class="hint">· ${esc(s.message)}</p>`).join("");
  el.innerHTML = `
    <div class="card">
      <h2>预算</h2>
      <div class="stacked">${stack}</div>
      <div class="budget-line">
        <span class="budget-total ${budget.over_budget ? "over" : ""}">${yuan(budget.total)}</span>
        <span class="muted">${budget.limit ? "上限 " + yuan(budget.limit) + " · 人均 " + yuan(budget.per_person) : "未设上限"}</span>
      </div>
      ${budget.limit ? `<div class="bar ${budget.over_budget ? "warn" : ""}"><i style="width:${pct}%"></i></div>` : ""}
      ${budget.over_budget ? `<p class="hint over">超出 ${yuan(budget.over_amount)}</p>` : ""}
      ${cats}
      ${sug}
      <p class="hint">门票为参考价，以景区实际票价为准；住宿为参考价位。</p>
    </div>`;
}

function renderTips(el, tips) {
  if (!tips) { el.innerHTML = ""; return; }
  const packing = (tips.packing || []).map((p) => `<span class="tag">${esc(p)}</span>`).join("");
  const wt = (tips.weather_tips || []).map((w) => `
    <div class="conflict">
      <span class="lv ${LEVEL_CLASS[w.level] || "low"}">${w.level === "warn" ? "注意" : "提示"}</span>
      <div><p>第 ${w.day_index} 天 ${esc(w.condition)}：${esc(w.message)}</p>
      <small>${(w.actions || []).map(esc).join("、")}</small></div>
    </div>`).join("");
  const notes = (tips.spot_notes || []).map((n) => `
    <div class="conflict">
      <span class="lv ${LEVEL_CLASS[n.level] || "low"}">${n.level === "warn" ? "注意" : "提示"}</span>
      <div><p>${esc(n.name)}：${esc(n.message)}</p><small>${esc(n.source || "")}</small></div>
    </div>`).join("");
  el.innerHTML = `
    <div class="card">
      <h2>出行贴士</h2>
      ${tips.note ? `<p style="background:#eef5ff;padding:10px;border-radius:8px;margin:0 0 10px">${esc(tips.note)}</p>` : ""}
      <div style="margin-bottom:8px">${packing}</div>
      ${wt}${notes}
      <p class="hint">来源：${esc(tips.source || "—")}${tips.note_source === "model" ? " · 提示语由模型生成" : ""}</p>
    </div>`;
}

