/* 结伴页：多人偏好 → 合并 → 冲突选择 */
const TAGS = ["自然", "美食", "拍照", "人文", "夜景", "购物", "亲子"];
const AVOID = ["爬山", "人多", "早起", "长距离步行", "商业化"];
const PACE = { slow: "慢逛", normal: "正常", fast: "多逛" };
const BUDGET = { low: "省一点", mid: "中等", high: "不介意" };

let TRIP_ID = null;
let members = [
  { name: "我", prefs: { interests: [], avoid: [], pace: "normal", budget_level: "mid" } },
  { name: "同伴", prefs: { interests: [], avoid: [], pace: "normal", budget_level: "mid" } },
];

function renderMembers() {
  document.getElementById("members").innerHTML = members.map((m, i) => `
    <div class="card" style="box-shadow:none;border:1px solid var(--line);margin-bottom:10px">
      <div class="row" style="margin-bottom:8px">
        <input data-i="${i}" data-k="name" value="${esc(m.name)}" placeholder="称呼" />
      </div>
      <label class="field">想玩</label>
      <div class="chips" style="margin-bottom:8px">
        ${TAGS.map((t) => `<button class="chip ${m.prefs.interests.includes(t) ? "on" : ""}" data-i="${i}" data-k="interests" data-tag="${t}">${t}</button>`).join("")}
      </div>
      <label class="field">不想要</label>
      <div class="chips" style="margin-bottom:8px">
        ${AVOID.map((t) => `<button class="chip ${m.prefs.avoid.includes(t) ? "on" : ""}" data-i="${i}" data-k="avoid" data-tag="${t}">${t}</button>`).join("")}
      </div>
      <div class="row">
        <div>
          <label class="field">节奏</label>
          <select data-i="${i}" data-k="pace">
            ${Object.entries(PACE).map(([v, t]) => `<option value="${v}" ${m.prefs.pace === v ? "selected" : ""}>${t}</option>`).join("")}
          </select>
        </div>
        <div>
          <label class="field">花钱</label>
          <select data-i="${i}" data-k="budget_level">
            ${Object.entries(BUDGET).map(([v, t]) => `<option value="${v}" ${m.prefs.budget_level === v ? "selected" : ""}>${t}</option>`).join("")}
          </select>
        </div>
      </div>
    </div>`).join("");
}

function bind() {
  document.querySelectorAll("#members input").forEach((el) => {
    el.oninput = () => { members[el.dataset.i].name = el.value; };
  });
  document.querySelectorAll("#members select").forEach((el) => {
    el.onchange = () => { members[el.dataset.i].prefs[el.dataset.k] = el.value; };
  });
  document.querySelectorAll("#members .chip").forEach((el) => {
    el.onclick = () => {
      const arr = members[el.dataset.i].prefs[el.dataset.k];
      const t = el.dataset.tag;
      const idx = arr.indexOf(t);
      if (idx >= 0) arr.splice(idx, 1);
      else if (arr.length < 3) arr.push(t);
      else return toast("每人最多 3 个");
      renderMembers();
      bind();
    };
  });
}

async function doMerge() {
  const btn = document.getElementById("btn-merge");
  btn.disabled = true;
  btn.textContent = "计算中…";
  try {
    const data = await API.members(TRIP_ID, members);
    renderResult(data.merge || {});
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "计算折中方案";
  }
}

function renderResult(m) {
  const consensus = (m.consensus || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("") || `<span class="muted">暂无共同点</span>`;
  const conflicts = (m.conflicts || []).map((t) => `
    <div class="conflict">
      <span class="lv">冲突</span>
      <div>
        <p>有人想去「${esc(t)}」，有人明确不想</p>
        <small>方案 A：保留，安排半天，其他人自由活动；方案 B：换成同类但没争议的地点</small>
        <div style="margin-top:6px">
          <button class="btn sm" data-avoid="${esc(t)}">按方案 B 调整行程</button>
        </div>
      </div>
    </div>`).join("") || `<p class="muted">没有明显冲突。</p>`;

  document.getElementById("result").innerHTML = `
    <section class="card">
      <h2>合并结果</h2>
      <div class="budget-line"><span>共同想玩</span><span>${consensus}</span></div>
      <div class="budget-line"><span>节奏</span><span>${PACE[m.pace] || "-"}</span></div>
      <div class="budget-line"><span>花钱</span><span>${BUDGET[m.budget_level] || "-"}</span></div>
    </section>
    <section class="card">
      <h2>需要商量的点</h2>
      ${conflicts}
    </section>`;

  document.querySelectorAll("[data-avoid]").forEach((b) => {
    b.onclick = async () => {
      b.disabled = true;
      b.textContent = "调整中…";
      try {
        await API.regenAll(TRIP_ID, b.dataset.avoid);
        toast("已按方案 B 调整，正在返回行程");
        setTimeout(() => location.href = `/plan.html?trip=${TRIP_ID}`, 700);
      } catch (e) {
        toast(e.message);
        b.disabled = false;
      }
    };
  });
}

document.addEventListener("DOMContentLoaded", () => {
  TRIP_ID = qs("trip");
  if (!TRIP_ID) { location.href = "/"; return; }
  document.getElementById("back").href = `/plan.html?trip=${TRIP_ID}`;

  renderMembers();
  bind();

  document.getElementById("btn-add").onclick = () => {
    if (members.length >= 5) return toast("最多 5 人");
    members.push({ name: "同伴" + (members.length + 1), prefs: { interests: [], avoid: [], pace: "normal", budget_level: "mid" } });
    renderMembers();
    bind();
  };
  document.getElementById("btn-merge").onclick = doMerge;
});
