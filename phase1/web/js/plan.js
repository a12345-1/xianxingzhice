/* 行程页：渲染 / 编辑 / 详情 / 突发重规划 */
let TRIP_ID = qs("trip");
let DATA = null;

async function load() {
  if (!TRIP_ID) { location.href = "/"; return; }
  try {
    DATA = await API.get(TRIP_ID);
    render();
  } catch (e) {
    document.getElementById("days").innerHTML =
      `<div class="empty">${esc(e.message)}<br><br><a class="btn" href="/">重新开始</a></div>`;
  }
}

function render() {
  renderSummary(document.getElementById("summary"), DATA);
  renderDays(document.getElementById("days"), DATA, { editable: true });
  renderAdjustments(document.getElementById("adjust"), (DATA.meta && DATA.meta.adjustments) || []);

  const bar = document.getElementById("budget-bar");
  if (DATA.budget) {
    bar.style.display = "block";
    renderBudgetBar(bar, DATA.budget, DATA.summary.people);
  }

  document.getElementById("nav-budget").href = `/budget.html?trip=${TRIP_ID}`;
  document.getElementById("nav-tips").href = `/tips.html?trip=${TRIP_ID}`;

  const box = document.getElementById("alert-box");
  const b = DATA.budget;
  if (b && b.over_budget) {
    box.style.display = "block";
    box.innerHTML = `<h2>预算超了</h2>
      <p class="hint over">已用 ${yuan(b.total)}，超出 ${yuan(b.over_amount)}</p>
      ${(b.suggestions || []).map((s) => `<p class="hint">· ${esc(s.message)}</p>`).join("")}`;
  } else {
    box.style.display = "none";
  }
}

function locate(itemId) {
  for (const d of DATA.days) {
    const idx = d.items.findIndex((x) => x.item_id === itemId);
    if (idx >= 0) return { day: d, idx };
  }
  return null;
}

function openMap(d) {
  if (!d.lat || !d.lng) return toast("这个地点没有坐标");
  const url = `https://uri.amap.com/marker?position=${d.lng},${d.lat}` +
              `&name=${encodeURIComponent(d.name)}&callnative=1`;
  window.open(url, "_blank");
}

async function openDetail(itemId) {
  try {
    const d = await API.detail(TRIP_ID, itemId);
    const stars = d.rating ? `评分 ${d.rating}` : "暂无评分";
    const reviews = (d.reviews || []).map((r) => `
      <div class="review">
        <b>${esc(r.user)}</b> <span class="muted">${"★".repeat(r.rating || 0)}</span>
        <p>${esc(r.text)}</p>
      </div>`).join("");
    document.getElementById("drawer-body").innerHTML = `
      <h2>${esc(d.name)}</h2>
      <p class="muted">${esc(d.area || "")} · ${esc(d.open_hours || "开放时间待核实")} · ${stars}</p>
      <p>${esc(d.intro)}</p>
      <div class="budget-line"><span>时间</span><span>${d.start_time} · ${d.duration_min} 分钟</span></div>
      <div class="budget-line"><span>花费</span><span>${yuan(d.cost)}</span></div>
      <div class="budget-line"><span>位置</span><span>${esc(d.address || "—")}</span></div>
      <div style="margin-top:10px">
        <button class="btn sm" id="drawer-map">在高德地图打开</button>
      </div>
      <h2 style="margin-top:16px">评价</h2>
      ${reviews || `<p class="hint">暂无评价</p>`}
      <p class="hint">${esc(d.reviews_source || "")}</p>`;
    document.getElementById("drawer").classList.add("open");
    const btn = document.getElementById("drawer-map");
    if (btn) btn.onclick = () => openMap(d);
  } catch (e) {
    toast(e.message);
  }
}

document.getElementById("drawer-close").onclick = () =>
  document.getElementById("drawer").classList.remove("open");
document.getElementById("drawer").onclick = (e) => {
  if (e.target.id === "drawer") e.target.classList.remove("open");
};

document.addEventListener("click", async (e) => {
  const el = e.target.closest("[data-act]");
  const row = e.target.closest(".item");
  if (!el || !row) return;
  const itemId = row.dataset.id;
  const act = el.dataset.act;
  const pos = locate(itemId);

  try {
    if (act === "detail") return openDetail(itemId);
    if (act === "map") {
      const d = await API.detail(TRIP_ID, itemId);
      return openMap(d);
    }
    if ((act === "up" || act === "down") && pos) {
      const target = pos.idx + (act === "up" ? 0 : 2);
      DATA = await API.patch(TRIP_ID, itemId, "reorder", { seq: target });
      return render();
    }
    if (act === "del") {
      DATA = await API.patch(TRIP_ID, itemId, "delete");
      toast("已删除，预算已更新");
      return render();
    }
    if (act === "rain") {
      DATA = await API.reroute(TRIP_ID, "rain", null, 0);
      toast("已按雨天重排：后面换成室内避雨");
      return render();
    }
  } catch (err) {
    toast(err.message);
  }
});

document.getElementById("btn-save").onclick = async () => {
  try {
    const r = await API.save(TRIP_ID);
    toast(`已保存（${r.saved_at.slice(11, 16)}），可在「我的行程」里查看`);
  } catch (e) { toast(e.message); }
};

document.getElementById("btn-cmd").onclick = async () => {
  const el = document.getElementById("cmd");
  const text = el.value.trim();
  const hint = document.getElementById("cmd-hint");
  if (!text) return toast("说说要改什么");
  const btn = document.getElementById("btn-cmd");
  btn.disabled = true;
  btn.textContent = "理解中…";
  try {
    const res = await API.command(TRIP_ID, text);
    const c = res.command || {};
    hint.textContent = c.message || "";
    DATA = res;
    render();
    if (c.ok) el.value = "";
    toast(c.ok ? "已修改" : "没有改动");
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "改一下";
  }
};

document.addEventListener("DOMContentLoaded", load);
