/* P1 首页 · 需求输入（按 design/pages/P1 实现） */
const $ = (id) => document.getElementById(id);
const state = { days: null, people: 1, budget: null, daysTouched: false, budgetTouched: false, city: null, startDate: null };

/* ---------- 解析回显：停止输入 600ms 后出现 ----------
   文本里说清楚的天数/预算会回填到控件上（用户手动改过控件则以控件为准）。 */
let echoTimer = null;
function scheduleEcho() {
  clearTimeout(echoTimer);
  echoTimer = setTimeout(async () => {
    const text = $("text").value.trim();
    if (text.length < 2) { $("echo").textContent = ""; return; }
    try {
      const r = await API.chat(text, {}, {
        days: state.daysTouched ? state.days : null,
        budget: state.budgetTouched ? state.budget : null,
      });
      const need = (r && r.need) || {};
      const city = need.city;
      const people = need.companions || 1;
      const days = need.days;
      const budget = need.budget;

      if (days && !state.daysTouched) {
        state.days = Math.max(1, Math.min(15, Number(days)));
        renderDays();
      }
      if (typeof budget === "number" && !state.budgetTouched) {
        state.budget = budget;
        $("budget").value = budget;
      }

      const parts = [];
      if (city && city !== "__unknown__") parts.push(city);
      parts.push(`${people} 人`);
      if (state.days) parts.push(`${state.days} 天`);
      if (state.budget) parts.push(`预算 ¥${state.budget}`);
      $("echo").textContent = parts.join(" · ");
    } catch (e) { /* 回显失败不打扰用户 */ }
  }, 600);
}

/* ---------- 人数步进器 ---------- */
function renderPeople() {
  $("people").textContent = state.people;
  $("people-minus").disabled = state.people <= 1;
  $("people-plus").disabled = state.people >= 10;
}

/* ---------- 天数步进器 ---------- */
function renderDays() {
  $("days").textContent = state.days == null ? "—" : state.days;
  $("minus").disabled = state.days == null || state.days <= 1;
  $("plus").disabled = state.days != null && state.days >= 15;
}

/* ---------- 校验 ---------- */
function validate() {
  const text = $("text").value.trim();
  const errs = [];
  $("text").classList.remove("invalid");
  $("budget").classList.remove("invalid");

  if (text.length < 4) {
    $("text").classList.add("invalid");
    errs.push("多说一句，比如想去哪、玩几天");
  }
  if (state.days == null) errs.push("先说说玩几天，或用「智能识别」自动填");
  else if (state.days < 1 || state.days > 15) errs.push("天数填 1–15 天");
  if (state.budget !== null && state.budget > 0 && state.budget < 100) {
    $("budget").classList.add("invalid");
    errs.push("预算至少 100 元，或选不限");
  }
  return errs;
}

/* ---------- 生成 ---------- */
async function submit(force, dayOverride, answers) {
  const errs = validate();
  if (errs.length) { $("err").textContent = errs[0]; return; }

  const text = $("text").value.trim();

  // 先做一次输入检测：缺城市/天数/预算就先问，不硬生成
  if (!answers) {
    try {
      const chat = await API.chat(text, {}, {
        days: state.daysTouched ? state.days : null,
        budget: state.budgetTouched ? state.budget : null,
      });
      if (!chat.ready) { renderAsk(chat); return; }
    } catch (e) { /* 检测失败就继续生成，交给后端兜底 */ }
  }

  const days = (answers && answers.days) || dayOverride || state.days;
  const budget = answers ? answers.budget : state.budget;
  const city = answers ? answers.city : null;
  const btn = $("gen");
  btn.disabled = true;
  btn.textContent = "正在规划…";
  $("err").textContent = "";
  $("ask").innerHTML = "";
  try {
    const trip = await API.generate(text, days, budget, city || state.city, force,
                                    state.daysTouched || !!answers, state.startDate, state.people);
    localStorage.setItem("last_trip", trip.trip_id);
    location.href = `/plan.html?trip=${encodeURIComponent(trip.trip_id)}`;
  } catch (e) {
    const d = e.detail || {};
    if (d.code === "UNKNOWN_CITY") {
      showCityAsk(d.supported || []);
    } else if (d.code === "BUDGET_TOO_LOW") {
      showBudgetAsk(d);
    } else if (d.code === "NO_DATA") {
      showCityAsk(d.supported || [], d.message);
    } else {
      $("err").textContent = "没生成出来，再试一次";
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "生成我的行程";
  }
}

/* 缺信息时直接问：城市给按钮、天数给步进器、预算给输入框 */
function renderAsk(chat) {
  const cities = chat.supported_cities || [];
  const qs = chat.questions || [];
  const blocks = qs.map((q) => {
    const msg = q.message ? `<span class="muted">（${esc(q.message)}）</span>` : "";
    if (q.slot === "city") {
      return `<div class="ask-row" data-slot="city">
        <label class="field">${esc(q.question)} ${msg}</label>
        <div class="chips" style="margin-top:6px">${
          cities.map((c) => `<button class="chip" data-city="${esc(c)}">${esc(c)}</button>`).join("")
        }</div>
      </div>`;
    }
    if (q.slot === "days") {
      return `<div class="ask-row" data-slot="days">
        <label class="field">${esc(q.question)}</label>
        <input type="number" min="1" max="15" value="${state.days || 2}" />
      </div>`;
    }
    return `<div class="ask-row" data-slot="budget">
      <label class="field">${esc(q.question)}</label>
      <input type="number" min="0" step="100" placeholder="留空 = 不限" />
    </div>`;
  }).join("");

  $("ask").innerHTML = `
    <div class="card" style="background:#fff9ec;border-left:3px solid #c98a00">
      <h2 style="margin-bottom:6px">还差一点信息</h2>
      ${blocks}
      <button class="btn block" id="ask-go" style="margin-top:10px">好，生成行程</button>
      <button class="btn ghost block" id="ask-cancel" style="margin-top:8px">算了，我重新说</button>
    </div>`;

  $("ask").querySelectorAll("[data-city]").forEach((b) => {
    b.onclick = () => {
      $("ask").querySelectorAll("[data-city]").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
    };
  });

  $("ask-cancel").onclick = () => { $("ask").innerHTML = ""; };
  $("ask-go").onclick = () => {
    const picked = $("ask").querySelector("[data-city].on");
    const city = picked ? picked.dataset.city : null;
    if (qs.some((q) => q.slot === "city") && !city) return toast("先选一个城市");
    const daysEl = $("ask").querySelector('[data-slot="days"] input');
    const budgetEl = $("ask").querySelector('[data-slot="budget"] input');
    const answers = {
      city: city,
      days: daysEl ? Number(daysEl.value) || state.days : state.days,
      budget: budgetEl && budgetEl.value ? Number(budgetEl.value) : null,
    };
    submit(false, null, answers);
  };
}

function showCityAsk(cities, message) {
  $("err").textContent = message || "没认出目的地，选一个城市：";
  $("ask").innerHTML = `<div class="chips" style="margin-top:8px">${
    cities.map((c) => `<button class="chip" data-city="${esc(c)}">${esc(c)}</button>`).join("")
  }</div>`;
  $("ask").querySelectorAll("[data-city]").forEach((b) => {
    b.onclick = () => {
      $("text").value = `去${b.dataset.city}${$("text").value.replace(/^去[^\u4e00-\u9fff]*/, "")}`;
      $("ask").innerHTML = "";
      $("err").textContent = "";
    };
  });
}

function showBudgetAsk(info) {
  $("err").textContent = "";
  $("ask").innerHTML = `
    <div class="card" style="background:#fff1f0;border-left:3px solid #d64545;margin-top:10px">
      <strong>${esc(info.message)}</strong>
      ${(info.suggestions || []).map((s) => `<p class="hint">· ${esc(s)}</p>`).join("")}
      <button class="btn sm" id="force" style="margin-top:10px">仍然生成</button>
    </div>`;
  $("force").onclick = () => submit(true);
}

/* ---------- 智能识别：一次把城市/日期/天数/预算填好 ---------- */
async function smartFill() {
  const text = $("text").value.trim();
  if (text.length < 2) return toast("先写一句想去哪儿");
  const btn = $("btn-smart");
  btn.disabled = true;
  btn.textContent = "正在读这句话…";
  try {
    const r = await API.chat(text, {}, {});
    const need = (r && r.need) || {};
    const filled = [];

    if (need.city && need.city !== "__unknown__") {
      state.city = need.city;
      paintCities();
      filled.push(need.city);
    }
    if (need.companions) {
      state.people = Math.max(1, Math.min(10, Number(need.companions)));
      renderPeople();
      filled.push(state.people + " 人");
    }
    if (need.days) {
      state.days = Math.max(1, Math.min(15, Number(need.days)));
      renderDays();
      filled.push(state.days + " 天");
    }
    if (typeof need.budget === "number") {
      state.budget = need.budget;
      $("budget").value = need.budget;
      filled.push("预算 ¥" + need.budget);
    }
    if (need.start_date) {
      state.startDate = need.start_date;
      $("start-date").value = need.start_date;
      filled.push(need.start_date);
    }
    toast(filled.length ? "已填入：" + filled.join(" · ") : "这句话里没读到新信息");
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "智能识别这段描述，自动填下面的信息";
  }
}

function paintCities() {
  $("city-chips").querySelectorAll("[data-city]").forEach((b) => {
    b.classList.toggle("on", b.dataset.city === state.city);
  });
}

async function loadCities() {
  try {
    const r = await API.cities();
    $("city-chips").innerHTML = (r.cities || []).map(
      (c) => `<button class="chip" data-city="${esc(c)}">${esc(c)}</button>`
    ).join("");
    $("city-chips").querySelectorAll("[data-city]").forEach((b) => {
      b.onclick = () => { state.city = b.dataset.city; paintCities(); };
    });
  } catch (e) { /* 城市列表拿不到不影响手填 */ }
}

/* ---------- AI 状态角标：配了 LLM_API_KEY 才亮 ---------- */
async function loadAiBadge() {
  const el = $("ai-badge");
  if (!el) return;
  try {
    const h = await API.health();
    if (h.model) {
      el.textContent = "AI 已连接 · " + h.model;
      el.style.color = "#1f7a4d";
    } else {
      el.textContent = "规则模式（未配 Key）";
      el.style.color = "#a35a00";
    }
  } catch (e) {
    el.textContent = "";
  }
}

/* ---------- 最近行程（最多 3 条） ---------- */
async function loadRecent() {
  try {
    const r = await API.list(3);
    const rows = (r.trips || []).slice(0, 3);
    if (!rows.length) { $("recent").innerHTML = ""; return; }
    $("recent").innerHTML = `<h2 style="font-size:13px;color:var(--sub);margin:0 0 8px">最近行程</h2>` +
      rows.map((t) => `
        <button class="recent-item" data-id="${esc(t.trip_id)}">
          <span class="t">${esc(t.title || t.city)} · ${esc((t.start_date || "").slice(5))} 生成</span>
          <span class="m">${t.total_cost ? "¥" + t.total_cost : ""} ›</span>
        </button>`).join("");
    $("recent").querySelectorAll("[data-id]").forEach((b) => {
      b.onclick = () => { location.href = `/plan.html?trip=${encodeURIComponent(b.dataset.id)}`; };
    });
  } catch (e) { $("recent").innerHTML = ""; }
}

/* ---------- 事件 ---------- */
document.addEventListener("DOMContentLoaded", () => {
  renderDays();
  $("text").addEventListener("input", scheduleEcho);
  $("minus").onclick = () => {
    state.daysTouched = true;
    state.days = Math.max(1, state.days - 1);
    renderDays();
  };
  $("plus").onclick = () => {
    state.daysTouched = true;
    state.days = Math.min(15, state.days + 1);
    renderDays();
  };
  $("budget").addEventListener("input", () => {
    state.budgetTouched = true;
    const v = $("budget").value.trim();
    state.budget = v === "" ? null : Number(v);
  });
  $("no-limit").onclick = () => {
    state.budgetTouched = true;
    $("budget").value = "";
    state.budget = null;
    $("no-limit").classList.add("on");
  };
  $("gen").onclick = () => submit(false);
  $("btn-smart").onclick = smartFill;
  $("people-minus").onclick = () => { state.people = Math.max(1, state.people - 1); renderPeople(); };
  $("people-plus").onclick = () => { state.people = Math.min(10, state.people + 1); renderPeople(); };
  renderPeople();
  const today = new Date().toISOString().slice(0, 10);
  $("start-date").min = today;
  $("start-date").onchange = () => { state.startDate = $("start-date").value || null; };
  loadCities();
  loadAiBadge();
  document.querySelectorAll("#examples button").forEach((b) => {
    b.onclick = () => { $("text").value = b.dataset.fill; scheduleEcho(); };
  });
  loadRecent();
});

