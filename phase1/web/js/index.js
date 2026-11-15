/* 首页：一句话 → （缺信息就反问三连）→ 生成 */
const $ = (id) => document.getElementById(id);
let ASK = null;   // 当前待补的信息

function payload() {
  const text = $("text").value.trim();
  const days = Number($("f-days").value) || 2;
  const budget = $("f-budget").value ? Number($("f-budget").value) : null;
  return { text, days, budget };
}

function clearAsk() {
  ASK = null;
  $("ask").innerHTML = "";
}

/* 缺 city / days / budget 时，直接在页面上问 */
function renderAsk(chat) {
  ASK = chat;
  const cities = chat.supported_cities || [];
  const qs = chat.questions || [];

  const cityChips = cities.map((c) => `<button class="chip" data-city="${esc(c)}">${esc(c)}</button>`).join("");

  const block = (q) => {
    const msg = q.message ? `<span class="muted">（${esc(q.message)}）</span>` : "";
    if (q.slot === "city") {
      return `<div class="ask-row" data-slot="city">
        <label class="field">${esc(q.question)} ${msg}</label>
        <div class="chips" style="margin-top:6px">${cityChips}</div>
      </div>`;
    }
    if (q.slot === "days") {
      return `<div class="ask-row" data-slot="days">
        <label class="field">${esc(q.question)}</label>
        <input type="number" min="1" max="15" value="${Number($("f-days").value) || 2}" />
      </div>`;
    }
    return `<div class="ask-row" data-slot="budget">
      <label class="field">${esc(q.question)}</label>
      <input type="number" min="0" step="100" placeholder="留空=不限" />
    </div>`;
  };

  $("ask").innerHTML = `
    <div class="card" style="background:#fff8e6;border-left:3px solid #e0a020">
      <h2 style="margin-bottom:6px">还差一点信息</h2>
      ${qs.map(block).join("")}
      <button class="btn" id="ask-go" style="margin-top:10px">好，生成行程</button>
      <button class="btn ghost" id="ask-cancel" style="margin-top:8px">算了我重新说</button>
    </div>`;

  $("ask").querySelectorAll("[data-city]").forEach((b) => {
    b.onclick = () => {
      $("ask").querySelectorAll("[data-city]").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
    };
  });

  $("ask-go").onclick = () => {
    const picked = $("ask").querySelector("[data-city].on");
    const city = picked ? picked.dataset.city : null;
    const daysEl = $("ask").querySelector('[data-slot="days"] input');
    const budgetEl = $("ask").querySelector('[data-slot="budget"] input');
    if (!city) return toast("先选一个城市");

    const days = daysEl ? Number(daysEl.value) || 2 : Number($("f-days").value) || 2;
    const budget = budgetEl && budgetEl.value ? Number(budgetEl.value) : null;
    doGenerate(city, days, budget);
  };

  $("ask-cancel").onclick = clearAsk;
}

async function doGenerate(city, days, budget) {
  const { text } = payload();
  const btn = $("btn-gen");
  btn.disabled = true;
  btn.textContent = "正在生成…";
  try {
    const trip = await API.generate(text, days, budget, city);
    localStorage.setItem("last_trip", trip.trip_id);
    location.href = `/plan.html?trip=${encodeURIComponent(trip.trip_id)}`;
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "生成我的行程";
  }
}

async function onGenerate() {
  const { text, days, budget } = payload();
  if (!text) return toast("先说说想去哪、玩几天");
  try {
    // 先做输入检测：缺什么就问什么（TC-06）
    const chat = await API.chat(text, {}, { days, budget });
    if (!chat.ready) return renderAsk(chat);
    clearAsk();
    await doGenerate(chat.need.city, days, budget);
  } catch (e) {
    toast(e.message);
  }
}

async function onClarify() {
  const { text, days, budget } = payload();
  try {
    const chat = await API.chat(text, {}, { days, budget });
    if (chat.ready) {
      $("questions").innerHTML = `<p class="hint">信息够了，直接点上面的按钮生成。</p>`;
      return;
    }
    renderAsk(chat);
  } catch (e) {
    toast(e.message);
  }
}

async function onRefresh() {
  const btn = $("btn-refresh");
  const { text } = payload();
  if (!text) return toast("先在输入框里写一句想去哪");
  btn.disabled = true;
  btn.textContent = "正在联网获取…";
  try {
    const r = await API.chat(text, {}, {});
    const city = (r.need && r.need.city) || "";
    if (!city || city === "__unknown__") return toast("没识别出城市，写清楚一点，例如「去杭州」");
    const res = await API.refreshCity(city);
    toast(`已从高德获取 ${city} 的 ${res.imported} 个地点`);
    const h = await API.health();
    $("cities").textContent = `当前已收录：${h.cities.join("、")}`;
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "联网获取该城市地点";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("btn-gen").onclick = onGenerate;
  $("btn-clarify").onclick = onClarify;
  $("btn-refresh").onclick = onRefresh;
  document.querySelectorAll("[data-fill]").forEach((b) => {
    b.onclick = () => { $("text").value = b.dataset.fill; clearAsk(); };
  });
  const last = localStorage.getItem("last_trip");
  if (last) {
    $("nav-plan").href = `/plan.html?trip=${encodeURIComponent(last)}`;
    $("hint").textContent = `上次生成的行程：${last}（可在「我的行程」里查看）`;
  }
  API.health().then((h) => {
    const el = document.getElementById("cities");
    if (el && h.cities) el.textContent = `当前已收录：${h.cities.join("、")}（其他城市还在补充）`;
  }).catch(() => {});
});
