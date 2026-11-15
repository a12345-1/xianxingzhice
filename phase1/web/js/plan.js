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

  renderDayNav();
  renderDayHead();
  renderItems();
  renderSide();
  renderBottom();
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
    box.innerHTML = `<div class="empty">这天还空着</div>`;
    return;
  }
  box.innerHTML = d.items.map((it) => itemCard(it)).join("");
  box.querySelectorAll(".item").forEach((el) => {
    const id = el.dataset.id;
    el.querySelector(".body").onclick = (ev) => {
      if (ev.target.closest("button")) return;
      OPEN = OPEN === id ? null : id;
      renderItems();
    };
  });
  box.querySelectorAll("[data-act]").forEach((b) => {
    b.onclick = (ev) => { ev.stopPropagation(); onAct(b.dataset.act, b.dataset.id); };
  });
}

function itemCard(it) {
  const d = currentDay();
  const conflict = (it.warnings || []).some((w) => w.code !== "INFO");
  const warns = (it.warnings || []).map((w) => esc(w.message)).join("；");
  const tags = (it.labels || []).map((l) => `<span class="tag">${esc(l)}</span>`).join("");
  const src = it.source === "model" ? `<span class="tag warn">推测</span>` : "";
  const hours = it.open_hours ? "" : `<span class="tag warn">待核实</span>`;
  const tr = it.transport && it.transport.from_prev_min
    ? `${MODE_LABEL[it.transport.mode] || it.transport.mode} ${it.transport.from_prev_min} 分`
    : "";
  const open = OPEN === it.item_id;
  return `
  <div class="item ${conflict ? "conflict" : ""} ${open ? "open" : ""}" data-id="${esc(it.item_id)}">
    <div class="time">${esc(it.start_time)}</div>
    <div class="body">
      <div class="name">${esc(it.name)}<span class="type">${TYPE_LABEL[it.type] || it.type}</span></div>
      <div class="sub">${it.duration_min} 分钟 · ${yuan(it.cost)}${tr ? " · " + tr : ""}</div>
      ${tags || src || hours ? `<div class="tags">${tags}${src}${hours}</div>` : ""}
      ${warns && conflict ? `<div class="warnline">⚠ ${warns}</div>` : ""}
      <div class="item-actions">
        <button class="btn sm ghost" data-act="swap" data-id="${esc(it.item_id)}">换一个</button>
        <button class="btn sm ghost" data-act="dur" data-id="${esc(it.item_id)}">调时长</button>
        <button class="btn sm danger" data-act="del" data-id="${esc(it.item_id)}">删除</button>
      </div>
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
  const pct = b.limit ? Math.min(100, Math.round(b.total / b.limit * 100)) : 0;

  document.getElementById("side").innerHTML = `
    <div class="card">
      <h2>当天预算 ${yuan(d.day_cost)}</h2>
      <div class="bar ${b.over_budget ? "warn" : ""}"><i style="width:${pct}%"></i></div>
      <div class="stat"><span>门票</span><span>${yuan(dayCats.ticket)}</span></div>
      <div class="stat"><span>餐饮</span><span>${yuan(dayCats.food)}</span></div>
      <div class="stat"><span>交通</span><span>${yuan(dayCats.transport)}</span></div>
      <div class="stat"><span>住宿</span><span>${yuan(dayCats.hotel)}</span></div>
      <div class="stat" style="margin-top:8px"><b>合计</b><b class="${b.over_budget ? "hint over" : ""}">${yuan(b.total)}${
        b.limit ? " / " + yuan(b.limit) : ""}</b></div>
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
    if (act === "up" || act === "down") {
      const d = currentDay();
      const idx = d.items.findIndex((x) => x.item_id === itemId);
      const target = idx + (act === "up" ? 0 : 2);
      DATA = await API.patch(TRIP_ID, itemId, "reorder", { seq: target });
      markDirty(); render();
    }
  } catch (e) { toast(e.message); }
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
