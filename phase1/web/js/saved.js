/* P5 已保存行程：查看 / 继续编辑 / 复制 / 删除 */
const $ = (id) => document.getElementById(id);

async function load() {
  const box = $("list");
  try {
    const r = await API.list(50);
    const rows = r.trips || [];
    $("count").textContent = rows.length ? `共 ${rows.length} 条` : "";
    if (!rows.length) {
      box.innerHTML = `<div class="empty">还没有行程<br><br><a class="btn" href="/">去生成一份</a></div>`;
      return;
    }
    box.innerHTML = rows.map((t) => {
      const over = t.budget_limit && t.total_cost > t.budget_limit;
      const saved = t.status === "saved";
      return `
      <div class="trip-card" data-id="${esc(t.trip_id)}">
        <div class="cover">${esc((t.city || "行").slice(0, 1))}</div>
        <div>
          <div class="t">${esc(t.title || t.city)} <span class="badge ${saved ? "saved" : ""}">${
            saved ? "已保存" : "未完成"}</span></div>
          <div class="m">${esc(t.start_date || "")} 起 · ${t.days} 天 · ${t.people} 人</div>
          <div class="m amt ${over ? "over" : ""}">${yuan(t.total_cost)}${
            t.budget_limit ? " / " + yuan(t.budget_limit) : ""}</div>
        </div>
        <div class="ops">
          <button class="btn sm ghost" data-op="edit">打开</button>
          <button class="btn sm ghost" data-op="dup">复制</button>
          <button class="btn sm danger" data-op="del">删除</button>
        </div>
      </div>`;
    }).join("");

    box.querySelectorAll(".trip-card").forEach((card) => {
      const id = card.dataset.id;
      card.onclick = async (e) => {
        const op = e.target.dataset.op;
        if (op === "dup") {
          e.stopPropagation();
          try {
            const n = await API.duplicate(id);
            toast("已复制一份");
            location.href = `/plan.html?trip=${encodeURIComponent(n.trip_id)}`;
          } catch (err) { toast(err.message); }
          return;
        }
        if (op === "del") {
          e.stopPropagation();
          if (!confirm("删除这份行程？无法恢复")) return;
          try {
            await API.remove(id);
            card.remove();
            const n = box.querySelectorAll(".trip-card").length;
            $("count").textContent = n ? `共 ${n} 条` : "";
            toast("已删除");
          } catch (err) { toast(err.message); }
          return;
        }
        location.href = `/plan.html?trip=${encodeURIComponent(id)}`;
      };
    });
  } catch (e) {
    box.innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
}

document.addEventListener("DOMContentLoaded", load);
