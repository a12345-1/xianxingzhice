/* P1 首页 · 需求输入（按 design/pages/P1 实现） */
const $ = (id) => document.getElementById(id);
const state = { days: 3, budget: null, daysTouched: false, budgetTouched: false };

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

/* ---------- 天数步进器 ---------- */
function renderDays() {
  $("days").textContent = state.days;
  $("minus").disabled = state.days <= 1;
  $("plus").disabled = state.days >= 15;
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
  if (state.days < 1 || state.days > 15) errs.push("天数填 1–15 天");
  if (state.budget !== null && state.budget > 0 && state.budget < 100) {
    $("budget").classList.add("invalid");
    errs.push("预算至少 100 元，或选不限");
  }
  return errs;
}

/* ---------- 生成 ---------- */
async function submit(force, dayOverride) {
  const errs = validate();
  if (errs.length) { $("err").textContent = errs[0]; return; }

  const days = dayOverride || state.days;
  const btn = $("gen");
  btn.disabled = true;
  btn.textContent = "正在规划…";
  $("err").textContent = "";
  $("ask").innerHTML = "";
  try {
    const trip = await API.generate($("text").value.trim(), days, state.budget, null, force,
                                    state.daysTouched);
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
  document.querySelectorAll("#examples button").forEach((b) => {
    b.onclick = () => { $("text").value = b.dataset.fill; scheduleEcho(); };
  });
  loadRecent();
});
