/* P2 行程浏览与编辑（按 design/pages/P2 实现）
   手机：天 Tab + 底部浮条；电脑：左天列表 + 中条目 + 右预算/校验/候选 */
let TRIP_ID = qs("trip");
let DATA = null;
let DAY = 1;
let OPEN = null;        // 当前展开的条目
let DIRTY = false;
let pendingDelete = null;

/* ---------------- 加载 ---------------- */
async function load() {
  if (!TRIP_ID) { location.href = "/"; return; }
  try {
    DATA = await API.get(TRIP_ID);
    DAY = DATA.days.length ? DATA.days[0].day_index : 1;
    render();
    if (DATA.command && DATA.command.message) toast(DATA.command.message);
  } catch (e) {
    document.getElementById("items").innerHTML =
      `<div class="empty">${esc(e.message)}<br><br><a class="btn" href="/">重新开始</a></div>`;
  }
}

function markDirty() {
  DIRTY = true;
  document.getElementById("dirty").style.display = "";
}

/* ---------------- 渲染 ---------------- */
function render() {
  const t = DATA.request, s = DATA.summary;
  document.getElementById("title").textContent = (t.destination || "") + " " + s.day_count + " 日";
  document.getElementById("meta").textContent = s.people + " 人";

  document.getElementById("summary").innerHTML = `
    <span>${esc(s.start_date || "")} 起</span>
    <span>${s.day_count} 天</span>
    <span class="amount ${s.over_budget ? "over" : ""}">${yuan(s.total_cost)}${
      s.budget_limit ? " / " + yuan(s.budget_limit) : ""}</span>
    <span class="muted">${s.item_count} 个地点</span>`;

  renderPlanNote();
  renderDayNav();
  renderDayHead();
  renderItems();
  renderSide();
  renderBottom();
}

/* 生成过程说明：模型提议了什么、代码改了什么（答辩时可以直接指给老师看） */
function renderPlanNote() {
  const box = document.getElementById("plan-note");
  if (!box) return;
  const p = (DATA.meta && DATA.meta.plan) || {};
  const fixes = p.fixes || [];
  if (!p.source) { box.innerHTML = ""; return; }

  const modelUsed = p.source === "llm+guard";
  const head = modelUsed
    ? `方案由 <b>模型提议</b>，<b>代码校验</b>${fixes.length ? `，修正 ${fixes.length} 处` : "，未发现问题"}`
    : "方案由本地规则生成（未启用模型）";
  const note = p.note ? `<div class="muted" style="margin-top:4px">模型思路：${esc(p.note)}</div>` : "";
  const list = fixes.length
    ? `<ul class="hint" style="margin:6px 0 0 16px;padding:0">${
        fixes.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>`
    : "";

  box.innerHTML = `
    <div class="card" style="background:#eef5ff;border-left:3px solid #2b4a8b;padding:10px 14px">
      <div style="font-size:13px">${head}</div>
      ${note}${list}
    </div>`;
}

function currentDay() {
  return DATA.days.find((d) => d.day_index === DAY) || DATA.days[0];
}

function renderDayNav() {
  const tabs = DATA.days.map((d) => `
    <button data-day="${d.day_index}" class="${d.day_index === DAY ? "on" : ""}">
      D${d.day_index} · ${esc((d.date || "").slice(5))}
    </button>`).join("");
  document.getElementById("dayTabs").innerHTML = tabs;

  document.getElementById("dayList").innerHTML = DATA.days.map((d) => `
    <div class="day-item ${d.day_index === DAY ? "on" : ""}" data-day="${d.day_index}">
      <div class="d">D${d.day_index} · ${esc((d.date || "").slice(5))}</div>
      <div class="m">${esc(d.weekday || "")} · ${yuan(d.day_cost)}</div>
    </div>`).join("");

  document.querySelectorAll("[data-day]").forEach((el) => {
    el.onclick = () => { DAY = Number(el.dataset.day); OPEN = null; render(); window.scrollTo({ top: 0 }); };
  });
}

function renderDayHead() {
  const d = currentDay();
  const w = d.weather;
  const wtext = w ? `${esc(w.condition)} ${w.temp_low}~${w.temp_high}° · 雨${w.rain_prob}%` : "";
  document.getElementById("dayHead").innerHTML = `
    <span class="big">${esc(d.weekday || "")}</span>
    <span class="m">${wtext}</span>
    <span class="m">今日 ${yuan(d.day_cost)}</span>
    <span class="m">体力${WALK_LABEL[d.walk_level] || "—"}</span>`;
}

function renderItems() {
  const d = currentDay();
  const box = document.getElementById("items");
  if (!d.items.length) {
    box.innerHTML = `
      <div class="card" style="background:#fff9ec;border-left:3px solid #c98a00">
        <strong>这天没有可安排的地点</strong>
        <p class="hint" style="margin-top:6px">${esc(d.empty_reason || "该城市收录的数据已用完")}</p>
      </div>
      <div class="add-item" id="add-item">＋ 手动加一个地点</div>`;
    const b = box.querySelector("#add-item");
    if (b) b.onclick = openAddPlace;
    return;
  }
  box.innerHTML = d.items.map((it) => itemCard(it)).join("") +
    `<div class="add-item" id="add-item">＋ 加一个地点</div>`;
  box.querySelectorAll(".item").forEach((el) => {
    const id = el.dataset.id;
    el.querySelector(".body").onclick = (ev) => {
      if (ev.target.closest("button")) return;
      if (JUST_DRAGGED) return;
      OPEN = OPEN === id ? null : id;
      renderItems();
    };
    bindDrag(el);
  });
  const cards = [...box.querySelectorAll(".item")];
  cards.forEach((el, i) => {
    const up = el.querySelector('[data-act="up"]');
    const down = el.querySelector('[data-act="down"]');
    if (up) up.disabled = i === 0;
    if (down) down.disabled = i === cards.length - 1;
  });
  box.querySelectorAll("[data-act]").forEach((b) => {
    b.onclick = (ev) => { ev.stopPropagation(); onAct(b.dataset.act, b.dataset.id); };
  });
  box.querySelectorAll("[data-time-for]").forEach((inp) => {
    inp.onclick = (ev) => ev.stopPropagation();
    inp.onchange = async () => {
      const id = inp.dataset.timeFor;
      const v = inp.value;
      if (!v) return;
      try {
        DATA = await API.patch(TRIP_ID, id, "update", { start_time: v });
        markDirty();
        render();
        toast("时间改好了，后面的安排已顺延");
      } catch (e) { toast(e.message); }
    };
  });
  box.querySelectorAll("[data-cost-for]").forEach((inp) => {
    inp.onclick = (ev) => ev.stopPropagation();
    const commit = async () => {
      const id = inp.dataset.costFor;
      const v = Math.max(0, Math.round(Number(inp.value) || 0));
      const it = currentDay().items.find((x) => x.item_id === id);
      if (it && itemBaseCost(it) === v) return;
      try {
        DATA = await API.patch(TRIP_ID, id, "update", { cost: v });
        markDirty();
        render();
        toast(`「${(it && it.name) || "这一项"}」改为 ¥${v}`);
      } catch (e) {
        toast(e.message);
      }
    };
    inp.onchange = commit;
    inp.onblur = commit;
    inp.onkeydown = (ev) => { if (ev.key === "Enter") { ev.preventDefault(); inp.blur(); } };
  });
  const addBtn = box.querySelector("#add-item");
  if (addBtn) addBtn.onclick = openAddPlace;
}

/* ---------------- 拖拽排序（手柄优先，长按作为补充） ----------------
   为什么用手柄：触屏上"长按再拖"会先触发布局滚动，往上拖几乎必被 scroll 抢走。
   手柄上的 touch-action:none 从按下瞬间就禁止滚动，方向不受限；
   卡片主体长按 0.4s 仍可作为补充入口（先滑动则视为滚动，不进入拖拽）。 */
const DRAG = { timer: null, active: false, el: null, id: null, from: 0, to: 0, startY: 0, startX: 0 };
let JUST_DRAGGED = false;

function beginDrag(el, ev, immediate) {
  DRAG.el = el;
  DRAG.id = el.dataset.id;
  DRAG.startY = ev.clientY;
  DRAG.startX = ev.clientX;
  DRAG.active = false;
  DRAG.to = DRAG.from = [...document.querySelectorAll("#items .item")].indexOf(el);

  const activate = () => {
    DRAG.active = true;
    el.classList.add("dragging");
    document.body.classList.add("drag-lock");
    if (navigator.vibrate) navigator.vibrate(12);
  };
  clearTimeout(DRAG.timer);
  if (immediate) activate();
  else DRAG.timer = setTimeout(activate, 400);
}

function bindDrag(el) {
  const handle = el.querySelector(".drag-handle");
  if (handle) {
    handle.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      beginDrag(el, ev, true);
    });
  }
  el.addEventListener("contextmenu", (ev) => {
    if (DRAG.active) ev.preventDefault();
  });
  el.addEventListener("pointerdown", (ev) => {
    if (ev.button && ev.button !== 0) return;
    if (ev.target.closest("button") || ev.target.closest(".drag-handle")) return;
    beginDrag(el, ev, false);
  });
}

/* 拖动过程与松手都挂在 document 上，指针跑到卡片外也不会断 */
document.addEventListener("pointermove", (ev) => {
  if (!DRAG.el) return;
  const dy = Math.abs(ev.clientY - DRAG.startY);
  const dx = Math.abs(ev.clientX - DRAG.startX);
  if (!DRAG.active) {
    if (dy > 8 || dx > 12) {          // 先动 = 想滚动，取消
      clearTimeout(DRAG.timer);
      DRAG.el = null;
    }
    return;
  }
  if (ev.cancelable) ev.preventDefault();
  placeAt(ev.clientY);
}, { passive: false });

document.addEventListener("touchmove", (ev) => {
  if (DRAG.active && ev.cancelable) ev.preventDefault();   // 拖拽期间禁止页面滚动
}, { passive: false });

document.addEventListener("pointerup", endDrag);
document.addEventListener("pointercancel", endDrag);

async function endDrag() {
  clearTimeout(DRAG.timer);
  if (!DRAG.el) return;
  const el = DRAG.el;
  const moved = DRAG.active && DRAG.to !== DRAG.from;
  el.classList.remove("dragging");
  document.body.classList.remove("drag-lock");
  DRAG.el = null;
  if (!DRAG.active) { DRAG.active = false; return; }
  DRAG.active = false;
  if (!moved) { renderItems(); return; }

  JUST_DRAGGED = true;
  setTimeout(() => { JUST_DRAGGED = false; }, 350);
  try {
    DATA = await API.patch(TRIP_ID, DRAG.id, "reorder", { seq: DRAG.to + 1 });
    markDirty();
    render();
    toast("已挪动，时间已重排");
  } catch (err) {
    toast(err.message);
    render();
  }
}

function placeAt(y) {
  const box = document.getElementById("items");
  const items = [...box.querySelectorAll(".item")];
  let target = items.findIndex((el) => {
    const r = el.getBoundingClientRect();
    return y < r.top + r.height / 2;
  });
  if (target === -1) target = items.length - 1;
  const cur = items.indexOf(DRAG.el);
  if (target === cur) { DRAG.to = cur; return; }
  if (target > cur) items[target].after(DRAG.el);
  else items[target].before(DRAG.el);
  DRAG.to = [...box.querySelectorAll(".item")].indexOf(DRAG.el);
}

function durationText(it) {
  if (it.type === "hotel") return "住宿";
  const n = Number(it.duration_min || 0);
  if (!n) return "即到即走";
  if (n >= 60) {
    const h = Math.floor(n / 60), m = n % 60;
    return m ? `${h} 小时 ${m} 分` : `${h} 小时`;
  }
  return `${n} 分钟`;
}

function itemBaseCost(it) {
  // 改价改的是“单价”：门票/餐饮按人份，住宿按房间；交通费另算
  if (it.unit_price != null) return Math.round(it.unit_price);
  const fare = (it.transport && it.transport.fare) || 0;
  const qty = it.qty || 1;
  return Math.max(0, Math.round(((it.cost || 0) - fare) / qty));
}

function qtyText(it) {
  const q = it.qty || 1;
  if (q <= 1) return "";
  return ` × ${q} ${it.qty_label || "人"}`;
}

function itemCard(it) {
  const d = currentDay();
  const conflict = (it.warnings || []).some((w) => w.code !== "INFO");
  const warns = (it.warnings || []).map((w) => esc(w.message)).join("；");
  const tags = (it.labels || []).map((l) => `<span class="tag${l === "已改" ? " warn" : ""}">${esc(l)}</span>`).join("");
  const src = it.source === "model" ? `<span class="tag warn">推测</span>` : "";
  const hours = it.open_hours ? "" : `<span class="tag warn">待核实</span>`;
  const tr = it.transport && it.transport.from_prev_min
    ? `${MODE_LABEL[it.transport.mode] || it.transport.mode} ${it.transport.from_prev_min} 分`
    : "";
  const open = OPEN === it.item_id;
  return `
  <div class="item ${conflict ? "conflict" : ""} ${open ? "open" : ""}" data-id="${esc(it.item_id)}">
    <span class="drag-handle" title="按住拖动排序" aria-label="拖动排序">⠿</span>
    <div class="time">${esc(it.start_time)}</div>
    <div class="body">
      <div class="name">${esc(it.name)}<span class="type">${TYPE_LABEL[it.type] || it.type}</span></div>
      <div class="sub">${durationText(it)} · ¥${itemBaseCost(it)}${qtyText(it)}${tr ? " · " + tr : ""}</div>
      ${tags || src || hours ? `<div class="tags">${tags}${src}${hours}</div>` : ""}
      ${warns && conflict ? `<div class="warnline">⚠ ${warns}</div>` : ""}
      <div class="item-actions">
        <button class="btn sm ghost" data-act="swap" data-id="${esc(it.item_id)}">换一个</button>
        <button class="btn sm ghost" data-act="dur" data-id="${esc(it.item_id)}">调时长</button>
        <button class="btn sm danger" data-act="del" data-id="${esc(it.item_id)}">删除</button>
      </div>
      ${open ? `
      <div class="dur-edit">
        <span>开始</span>
        <input type="time" value="${esc(it.start_time)}" data-time-for="${esc(it.item_id)}" />
        <span class="muted">改完后面几条一起顺延</span>
      </div>` : ""}
      ${open && it.type !== "hotel" ? `
      <div class="dur-edit" data-id="${esc(it.item_id)}">
        <button data-act="dur-15" data-id="${esc(it.item_id)}">−15 分</button>
        <span>${durationText(it)}</span>
        <button data-act="dur+15" data-id="${esc(it.item_id)}">+15 分</button>
      </div>` : ""}
      ${open ? `
      <div class="cost-edit">
        <span>单价 ¥${it.qty_label ? "（每" + it.qty_label + "）" : ""}</span>
        <input type="number" min="0" step="10" inputmode="numeric"
               value="${itemBaseCost(it)}" data-cost-for="${esc(it.item_id)}" />
        ${(it.transport && it.transport.fare) ? `<span class="muted">交通另计 ¥${it.transport.fare}</span>` : ""}
        <span class="muted">改完总预算自动重算</span>
      </div>` : ""}
      <div class="hover-ops">
        <button data-act="up" data-id="${esc(it.item_id)}" title="上移">↑</button>
        <button data-act="down" data-id="${esc(it.item_id)}" title="下移">↓</button>
      </div>
    </div>
  </div>`;
}

function renderSide() {
  const d = currentDay();
  const b = DATA.budget;
  const dayCats = { ticket: 0, transport: 0, food: 0, hotel: 0 };
  d.items.forEach((it) => {
    for (const k of Object.keys(it.cost_breakdown || {})) dayCats[k] = (dayCats[k] || 0) + it.cost_breakdown[k];
  });
  const warnList = [];
  d.items.forEach((it) => (it.warnings || []).forEach((w) => warnList.push(it.name + "：" + w.message)));

  // 当天预算占比：用“日均预算”做分母，条形才是动态的
  const days = (DATA.days || []).length || 1;
  const dayLimit = b.limit ? Math.round(b.limit / days) : 0;
  const dayPct = dayLimit ? Math.min(100, Math.round(d.day_cost / dayLimit * 100)) : 0;
  const dayOver = dayLimit && d.day_cost > dayLimit;
  const dayTotal = d.day_cost || 1;
  const catRow = (label, key) => {
    const amt = dayCats[key] || 0;
    const ratio = Math.round(amt / dayTotal * 100);
    return `<div class="stat"><span>${label}</span><span>${yuan(amt)}${
      amt ? ` <span class="muted">${ratio}%</span>` : ""}</span></div>`;
  };

  document.getElementById("side").innerHTML = `
    <div class="card">
      <h2>当天预算 ${yuan(d.day_cost)}${dayLimit ? `<span class="muted" style="font-size:12px;font-weight:400"> / 日均 ${yuan(dayLimit)}（${dayPct}%）</span>` : ""}</h2>
      <div class="stacked">${["ticket", "food", "transport", "hotel"].map((k) => {
        const amt = dayCats[k] || 0;
        return amt ? `<span title="¥${amt}" style="width:${(amt / (d.day_cost || 1) * 100).toFixed(1)}%;background:${CAT_COLOR[k]}"></span>` : "";
      }).join("")}</div>
      ${dayLimit ? `<div class="bar ${dayOver ? "warn" : ""}"><i style="width:${Math.max(dayPct, 2)}%"></i></div>` : ""}
      ${catRow("门票", "ticket")}
      ${catRow("餐饮", "food")}
      ${catRow("交通", "transport")}
      ${catRow("住宿", "hotel")}
      <div class="stat" style="margin-top:8px"><b>合计</b><b class="${b.over_budget ? "hint over" : ""}">${yuan(b.total)}${
        b.limit ? " / " + yuan(b.limit) + `（${Math.round(b.total / b.limit * 100)}%）` : ""}</b></div>
      ${warnList.length ? `<h2 style="margin-top:16px">时间校验</h2>
        <ul class="warn-list">${warnList.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
      <h2 style="margin-top:16px">候选地点</h2>
      <div id="cands" class="muted">点条目里的「换一个」查看</div>
    </div>`;
}

function renderBottom() {
  const d = currentDay();
  const b = DATA.budget;
  document.getElementById("bottom").innerHTML = `
    <span class="muted">今日 ${yuan(d.day_cost)}</span>
    <span class="amount ${b.over_budget ? "over" : ""}">合计 ${yuan(b.total)}${
      b.limit ? "/" + yuan(b.limit) : ""}</span>
    <span class="spacer"></span>
    <a class="btn sm ghost" href="/budget.html?trip=${TRIP_ID}" style="text-decoration:none">预算</a>
    <a class="btn sm ghost" href="/tips.html?trip=${TRIP_ID}" style="text-decoration:none">贴士</a>`;
}

/* ---------------- 交互 ---------------- */
async function onAct(act, itemId) {
  try {
    if (act === "del") return doDelete(itemId);
    if (act === "dur") return doDuration(itemId);
    if (act === "swap") return openSwap(itemId);
    if (act === "dur-15" || act === "dur+15") {
      const d = currentDay();
      const it = d.items.find((x) => x.item_id === itemId);
      const n = Math.max(15, Math.min(300, Number(it.duration_min || 0) + (act === "dur+15" ? 15 : -15)));
      DATA = await API.patch(TRIP_ID, itemId, "update", { duration_min: n });
      markDirty(); render();
      return;
    }
    if (act === "up" || act === "down") {
      const d = currentDay();
      const idx = d.items.findIndex((x) => x.item_id === itemId);
      const target = idx + (act === "up" ? 0 : 2);
      const res = await API.patch(TRIP_ID, itemId, "reorder", { seq: target });
      DATA = res;
      if (res.moved === false) {
        toast(act === "up" ? "已经是第一个了" : "已经是最后一个了");
        return;
      }
      markDirty(); render();
    }
  } catch (e) { toast(e.message); }
}

/* 加一个地点：本页抽屉，同区域候选，餐饮/景点切换 */
async function openAddPlace() {
  try {
    const r = await API.addCandidates(TRIP_ID, DAY, "attraction");
    renderAddDrawer(r.candidates || [], "attraction");
  } catch (e) { toast(e.message); }
}

function renderAddDrawer(list, type) {
  const tabs = `
    <div class="chips" style="margin-bottom:10px">
      <button class="chip ${type === "attraction" ? "on" : ""}" data-ptype="attraction">景点</button>
      <button class="chip ${type === "food" ? "on" : ""}" data-ptype="food">餐饮</button>
    </div>`;
  const rows = list.length
    ? list.map((c) => `
      <div class="cand" data-poi="${c.poi_id}" style="display:flex;justify-content:space-between;padding:10px 0;border-top:1px solid var(--line);cursor:pointer">
        <span>${esc(c.name)}<br><small class="muted">${esc(c.area || "")} · ${yuan(c.price)} · ${c.stay_min} 分钟</small></span>
        <span style="color:var(--brand)">加上 ›</span>
      </div>`).join("")
    : `<p class="empty">这一带没有可加的地点了</p>`;

  document.getElementById("drawer-body").innerHTML = `
    <h2>加一个地点</h2>
    <p class="muted">优先同区域，加完会自动重排当天时间</p>
    ${tabs}${rows}`;
  document.getElementById("drawer").classList.add("open");

  document.querySelectorAll("[data-ptype]").forEach((b) => {
    b.onclick = async () => {
      const t = b.dataset.ptype;
      try {
        const r = await API.addCandidates(TRIP_ID, DAY, t);
        renderAddDrawer(r.candidates || [], t);
      } catch (e) { toast(e.message); }
    };
  });
  document.querySelectorAll("[data-poi]").forEach((el) => {
    el.onclick = async () => {
      try {
        DATA = await API.addItem(TRIP_ID, DAY, Number(el.dataset.poi));
        document.getElementById("drawer").classList.remove("open");
        markDirty(); render();
        toast("已加入，时间已重排");
      } catch (e) { toast(e.message); }
    };
  });
}

function doDelete(itemId) {
  const d = currentDay();
  const idx = d.items.findIndex((x) => x.item_id === itemId);
  if (idx < 0) return;
  const backup = JSON.parse(JSON.stringify(d.items[idx]));
  d.items.splice(idx, 1);
  OPEN = null;
  render();
  pendingDelete = { itemId, backup, dayIndex: DAY };
  const box = document.getElementById("undo");
  document.getElementById("undo-text").textContent = `已删除「${backup.name}」`;
  box.classList.add("show");
  clearTimeout(pendingDelete.timer);
  pendingDelete.timer = setTimeout(async () => {
    box.classList.remove("show");
    try {
      DATA = await API.patch(TRIP_ID, itemId, "delete");
      markDirty(); render();
    } catch (e) { toast(e.message); }
    pendingDelete = null;
  }, 3000);
}

document.getElementById("undo-btn").onclick = () => {
  if (!pendingDelete) return;
  clearTimeout(pendingDelete.timer);
  const d = DATA.days.find((x) => x.day_index === pendingDelete.dayIndex);
  d.items.splice(0, 0, pendingDelete.backup);   // 位置近似还原
  d.items.sort((a, b) => (a.start_time > b.start_time ? 1 : -1));
  d.items.forEach((x, i) => { x.seq = i + 1; });
  pendingDelete = null;
  document.getElementById("undo").classList.remove("show");
  render();
};

async function doDuration(itemId) {
  const d = currentDay();
  const it = d.items.find((x) => x.item_id === itemId);
  const v = window.prompt("调整时长（分钟，15—300）", it.duration_min);
  if (v === null) return;
  const n = Math.max(15, Math.min(300, Number(v) || it.duration_min));
  try {
    DATA = await API.patch(TRIP_ID, itemId, "update", { duration_min: n });
    it.duration_min = n;
    markDirty(); render();
  } catch (e) { toast(e.message); }
}

async function openSwap(itemId) {
  try {
    const r = await API.candidates(TRIP_ID, itemId);
    const list = r.candidates || [];
    document.getElementById("drawer-body").innerHTML = `
      <h2>换一个</h2>
      <p class="muted">同城市、同类型，优先同区域</p>
      ${list.length ? list.map((c) => `
        <div class="side"><div class="cand" data-poi="${c.poi_id}">
          <span>${esc(c.name)}<br><small>${esc(c.area || "")} · ${yuan(c.price)} · ${c.stay_min} 分钟</small></span>
          <span>选它 ›</span>
        </div></div>`).join("") : `<p class="empty">没有可替换的地点</p>`}`;
    document.getElementById("drawer").classList.add("open");
    document.querySelectorAll("[data-poi]").forEach((el) => {
      el.onclick = async () => {
        try {
          DATA = await API.patch(TRIP_ID, itemId, "replace", { poi_id: Number(el.dataset.poi) });
          document.getElementById("drawer").classList.remove("open");
          markDirty(); render();
          toast("已替换");
        } catch (e) { toast(e.message); }
      };
    });
  } catch (e) { toast(e.message); }
}

document.getElementById("drawer-close").onclick = () =>
  document.getElementById("drawer").classList.remove("open");
document.getElementById("drawer").onclick = (e) => {
  if (e.target.id === "drawer") e.target.classList.remove("open");
};

document.getElementById("save").onclick = async () => {
  try {
    const r = await API.save(TRIP_ID);
    DIRTY = false;
    document.getElementById("dirty").style.display = "none";
    toast(`已保存（${r.saved_at.slice(11, 16)}）· <a href="/saved.html">查看我的行程</a>`);
  } catch (e) { toast(e.message); }
};

document.getElementById("back").onclick = (e) => {
  if (DIRTY && !confirm("有未保存的改动，放弃？")) e.preventDefault();
};

document.addEventListener("DOMContentLoaded", load);
