/* 已保存行程 */
(async () => {
  const box = document.getElementById("list");
  try {
    const r = await API.list();
    if (!r.trips.length) {
      box.innerHTML = `<div class="empty">还没有保存的行程<br><br><a class="btn" href="/">去生成一份</a></div>`;
      return;
    }
    box.innerHTML = r.trips.map((t) => `
      <a class="card" href="/plan.html?trip=${encodeURIComponent(t.code)}" style="display:block;text-decoration:none;color:inherit">
        <h2 style="margin:0 0 4px">${esc(t.title || t.city)}</h2>
        <p class="muted">${esc(t.start_date || "")} · ${t.days} 天 · ${t.budget_limit ? "￥" + t.budget_limit : "不限"} · 保存于 ${esc((t.saved_at || "").slice(0, 16).replace("T", " "))}</p>
      </a>`).join("");
  } catch (e) {
    box.innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
})();
