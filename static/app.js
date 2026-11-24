const $ = (id) => document.getElementById(id);
const fmt = (n) => (n == null ? "—" : Math.round(n).toLocaleString("en-IN"));
const pct = (x) => (x * 100).toFixed(1) + "%";
const dur = (s) => `${Math.floor(s / 60)}m ${String(Math.round(s % 60)).padStart(2, "0")}s`;
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const addDays = (iso, n) => { const d = new Date(iso + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const spanDays = (a, b) => Math.round((new Date(b) - new Date(a)) / 864e5) + 1;

/** Period-over-period change. isRatio: percentage points; invert: lower is better (e.g. average position). */
function delta(cur, prev, { isRatio = false, invert = false } = {}) {
  if (cur == null || prev == null || (!isRatio && !prev)) return "";
  const d = isRatio ? (cur - prev) * 100 : ((cur - prev) / prev) * 100;
  if (!isFinite(d) || Math.abs(d) < 0.05) return `<span class="sub">no change</span>`;
  const good = invert ? d < 0 : d > 0;
  return `<span class="sub ${good ? "up" : "down"}">${d > 0 ? "↑" : "↓"} ${d > 0 ? "+" : ""}${d.toFixed(1)}${isRatio ? " pts" : "%"}</span>`;
}

let cfg, runId = 0;
let lastTracker = null, lastSocial = null, socialDone = true;   // for export

async function load(start, end) {
  const id = ++runId;                       // ignore responses from a superseded request
  $("canvas").classList.add("loading");
  $("banner").className = "banner hidden";
  const q = start ? `?start=${start}&end=${end}` : "";
  loadSocial(q, id);                        // slow (LinkedIn) – runs in parallel, renders when ready
  try {
    const r = await fetch("/api/tracker" + q);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    const d = await r.json();
    if (id === runId) render(d);
  } catch (e) {
    $("banner").textContent = e.message;
    $("banner").className = "banner err";
  } finally {
    if (id === runId) $("canvas").classList.remove("loading");
  }
}

function render(d) {
  lastTracker = d;
  $("printPeriod").textContent = `Weekly report · ${d.period.label} ${d.period.end.slice(0, 4)} · compared with ${d.previous.label}`;
  $("from").value = d.period.start;
  $("to").value = d.period.end;
  if (d.mode === "sample") {
    $("banner").textContent = "Showing SAMPLE data — Google credentials are not configured.";
    $("banner").className = "banner";
  } else if (d.period.end > cfg.latest_date) {
    $("banner").textContent = `This period is still in progress — data runs to ${cfg.latest_date}, so totals will be lower than a full week.`;
    $("banner").className = "banner";
  }
  const c = d.traffic.current, p = d.traffic.previous, T = d.targets;
  $("trafficSub").textContent = `${d.period.label} · compared with ${d.previous.label} · job/career pages excluded`;

  const rows = [
    ["Total Traffic", (x) => fmt(x.total_users), "total_users", {}],
    ["New Users", (x) => fmt(x.new_users), "new_users", {}],
    ["Session", (x) => fmt(x.sessions), "sessions", {}],
    ["Engagement Rate", (x) => pct(x.engagement_rate), "engagement_rate", { isRatio: true }],
    ["Avg Session Duration", (x) => dur(x.avg_session_duration_sec), "avg_session_duration_sec", {}],
  ];
  let h = `<tr><th></th><th>Overall</th><th>India traffic</th><th>Target</th></tr>`;
  for (const [label, f, key, o] of rows) {
    let tgt = "";
    if (key === "total_users") tgt = `<span class="target">${fmt(T.weekly_traffic)}/wk</span>`;
    if (key === "avg_session_duration_sec") {
      const ok = c.india[key] >= T.avg_session_duration_sec;
      tgt = `<span class="target ${ok ? "met" : ""}">&gt;${T.avg_session_duration_sec}s</span>`;
    }
    h += `<tr><td>${label}</td><td>${f(c.overall)}${delta(c.overall[key], p.overall[key], o)}</td>
      <td>${f(c.india)}${delta(c.india[key], p.india[key], o)}</td><td>${tgt}</td></tr>`;
  }
  for (const ch of cfg.channels) {
    h += `<tr><td>${ch}</td><td>${fmt(c.channels_overall[ch])}${delta(c.channels_overall[ch], p.channels_overall[ch])}</td>
      <td>${fmt(c.channels_india[ch])}${delta(c.channels_india[ch], p.channels_india[ch])}</td><td></td></tr>`;
  }
  $("trafficTable").innerHTML = h;
  drawChart(d.trend, T.weekly_traffic);
  renderSearch(d);
}

function renderSearch(d) {
  $("kwSub").textContent = `${d.period.label} · India · keywords ranking 1–100 with Google Keyword Planner volume (same rule as the dashboard) · compared with ${d.previous.label} · newest GSC data ≈ ${d.notes.gsc_latest_date}`;
  const cur = d.keywords.current, prev = d.keywords.previous;
  const top10 = (o) => o["1-5"] + o["6-10"];
  // One table: rows = position buckets, columns = any list of {label, cur, prev}
  const table = (first, cols) => {
    const cell = (c, v) => `<td>${fmt(v(c.cur))}${delta(v(c.cur), v(c.prev))}</td>`;
    const row = (label, v, cls = "") => `<tr class="${cls}"><td>${label}</td>${cols.map((c) => cell(c, v)).join("")}</tr>`;
    return `<tr><th>${first}</th>${cols.map((c) => `<th>${c.label}</th>`).join("")}</tr>` +
      row("Position 1–5", (o) => o["1-5"]) + row("Position 6–10", (o) => o["6-10"]) +
      row("= Keywords between 1–10", top10, "top") +
      row("Position 11–20", (o) => o["11-20"]) + row("Position 21–50", (o) => o["21-50"]) + row("Position 51–100", (o) => o["51-100"]) +
      row("Total keywords (with volume)", (o) => o.total, "total") +
      row("Branded", (o) => o.branded, "top") + row("Non-branded", (o) => o.non_branded, "top") +
      row("No volume (ranking 1–100)", (o) => o.no_volume, "top");
  };
  $("kwTable").innerHTML = table("Whole site", [
    { label: "Exclusive of blogs", cur: cur.no_blogs, prev: prev.no_blogs },
    { label: "Inclusive of blogs", cur: cur.all, prev: prev.all },
  ]);
  $("productKwTable").innerHTML = table("By product", Object.keys(cur.products).map((k) => ({
    label: cur.products[k].label, cur: cur.products[k], prev: prev.products[k] })));
  $("kwNote").textContent = cur.volume_applied
    ? "Product keywords are the queries that ranked on each product's pages (fluidPrint: non-blog fluidprint / managed-print pages · floTax: its four product pages · GST Verification: every page with “gst” in its URL, so it includes GST blogs and overlaps floTax · fluidPro: its service page)."
    : "Keyword volume is not available, so keywords without Keyword Planner volume are included in these counts.";
}

// ---------------------------------------------------------------- social
const PCOL = { facebook: "#1e40af", instagram: "#be185d", linkedin: "#0f766e" };
const PNAME = { facebook: "Facebook", instagram: "Instagram", linkedin: "LinkedIn" };

async function loadSocial(q, id) {
  socialDone = false; lastSocial = null;
  if (!cfg.social) {
    socialDone = true;
    $("socialSub").textContent = "Social is not configured (add META_ACCESS_TOKEN, META_PAGE_ID, IG_USER_ID).";
    return;
  }
  $("socialSub").innerHTML = `<span class="spin"></span>Loading Facebook, Instagram and LinkedIn (LinkedIn can take ~20 seconds)…`;
  $("platforms").innerHTML = $("liBreakdown").innerHTML = $("liCards").innerHTML = $("liNote").textContent = "";
  try {
    const r = await fetch("/api/social" + q);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    const s = await r.json();
    if (id === runId) renderSocial(s);
  } catch (e) {
    if (id === runId) $("socialSub").innerHTML = `<span class="down">${esc(e.message)}</span>`;
  } finally {
    if (id === runId) socialDone = true;
  }
}

function renderSocial(s) {
  lastSocial = s;
  $("socialSub").textContent = `${s.period.label} · compared with ${s.previous.label} · Facebook & Instagram via Meta Graph API, LinkedIn via Apify`;
  let cards = "";
  for (const key of ["linkedin", "facebook", "instagram"]) {
    const p = s.platforms[key];
    let body;
    if (!p) body = `<div class="err">Could not load: ${esc(s.errors[key] || "unknown error")}</div>`;
    else {
      body = `<div class="fol"><b>${fmt(p.followers)}</b>followers${p.followers_asof ? ` · at ${s.period.end}` : " · now"}</div>` +
        p.metrics.map(([name, v]) => `<div class="row"><span>${name}</span><span><b>${v.cur == null ? '<span class="na">tracking…</span>' : fmt(v.cur)}</b>${delta(v.cur, v.prev) || (v.prev != null ? `<span class="sub">prev ${fmt(v.prev)}</span>` : "")}</span></div>`).join("") +
        (p.unavailable ? p.unavailable.map((n) => `<div class="row"><span>${n}</span><span class="na">needs LinkedIn admin data</span></div>`).join("") : "") +
        (p.admin_error ? `<div class="err" style="margin-top:8px;font-size:12px">LinkedIn admin analytics unavailable: ${esc(p.admin_error)}</div>` : "");
    }
    cards += `<div class="pcard" style="--c:${PCOL[key]}"><h4><i></i>${PNAME[key]}</h4>${body}</div>`;
  }
  $("platforms").innerHTML = cards;

  renderLiPosts(s);
}

const PRODCOL = { fluidPrint: "#0f766e", fluidPro: "#1e40af", floTax: "#b45309", "Company / brand": "#6b7280" };

function renderLiPosts(s) {
  const posts = s.li_posts || [], rows = s.li_breakdown || [];
  $("liHead").textContent = `LinkedIn posts by product and post type · ${s.period.label} · ${posts.length} post${posts.length === 1 ? "" : "s"}`;
  let h = `<tr><th>Product</th><th>Post type</th><th>Posts</th><th>Reactions</th><th>Comments</th><th>Shares</th><th>Engagement</th><th>Avg / post</th></tr>`;
  if (!rows.length) h += `<tr><td colspan="8" style="text-align:center;color:var(--muted)">No LinkedIn posts in this period</td></tr>`;
  for (const r of rows) {
    h += `<tr class="total"><td style="color:${PRODCOL[r.product] || "#6b7280"}">${esc(r.product)}</td><td>All types</td><td>${fmt(r.posts)}</td><td>${fmt(r.reactions)}</td><td>${fmt(r.comments)}</td><td>${fmt(r.shares)}</td><td>${fmt(r.engagement)}</td><td>${r.avg}</td></tr>`;
    for (const t of r.types) h += `<tr class="top"><td></td><td>${esc(t.type)}</td><td>${fmt(t.posts)}</td><td>${fmt(t.reactions)}</td><td>${fmt(t.comments)}</td><td>${fmt(t.shares)}</td><td>${fmt(t.engagement)}</td><td>${t.avg}</td></tr>`;
  }
  $("liBreakdown").innerHTML = h;
  $("liNote").textContent = "Engagement = reactions + comments + shares. Impressions and clicks per post are only in LinkedIn's page-admin content export, so they are not shown here. Product and post type are read from each post's text and media.";
  $("liCards").innerHTML = posts.map((p) => `
    <a class="pc" href="${esc(p.url || "#")}" target="_blank" rel="noopener">
      <div class="pc-img" style="${p.image ? `background-image:url('${esc(p.image)}')` : ""}">${p.image ? "" : "<span>no image</span>"}
        <span class="badge" style="background:${PRODCOL[p.product] || "#6b7280"}">${esc(p.product)}</span></div>
      <div class="pc-body">
        <div class="pc-meta"><span>${p.date}</span><span class="tag">${esc(p.ptype)}</span></div>
        <p>${esc(p.text)}</p>
        <div class="pc-nums"><div><b>${fmt(p.likes)}</b><small>Reactions</small></div><div><b>${fmt(p.comments)}</b><small>Comments</small></div>
          <div><b>${fmt(p.shares)}</b><small>Shares</small></div><div class="eng"><b>${fmt(p.engagement)}</b><small>Engagement</small></div></div>
      </div>
    </a>`).join("");
}

// ---------------------------------------------------------------- chart
function drawChart(trend, target) {
  const W = 560, H = 300, m = { l: 48, r: 48, t: 20, b: 36 };
  const series = [["new_users", "#2f6df6"], ["total_users", "#12b5c8"], ["sessions", "#e4004f"]];
  const vals = trend.flatMap((t) => series.map(([k]) => t[k])).concat(target);
  const max = Math.ceil((Math.max(...vals) * 1.1) / 100) * 100 || 100;
  const x = (i) => m.l + (i * (W - m.l - m.r)) / Math.max(1, trend.length - 1);
  const y = (v) => H - m.b - (v / max) * (H - m.t - m.b);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Traffic trend">`;
  for (let i = 0; i <= 4; i++) {
    const v = (max / 4) * i;
    s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}" stroke="rgba(20,22,31,.08)"/>
      <text x="${m.l - 8}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="#6b7280">${fmt(v)}</text>`;
  }
  s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(target)}" y2="${y(target)}" stroke="#6b7280" stroke-dasharray="6 5"/>`;
  trend.forEach((t, i) => (s += `<text x="${x(i)}" y="${H - 10}" text-anchor="middle" font-size="11" fill="#6b7280">${t.label}</text>`));
  for (const [k, col] of series) {
    s += `<polyline fill="none" stroke="${col}" stroke-width="2.5" points="${trend.map((t, i) => `${x(i)},${y(t[k])}`).join(" ")}"/>`;
    trend.forEach((t, i) => (s += `<circle cx="${x(i)}" cy="${y(t[k])}" r="4" fill="#fff" stroke="${col}" stroke-width="2"/>
      <text x="${x(i)}" y="${y(t[k]) - 9}" text-anchor="middle" font-size="11" font-weight="600" fill="${col}">${fmt(t[k])}</text>`));
  }
  $("chart").innerHTML = s + "</svg>";
}

// ---------------------------------------------------------------- controls
// Picking a start date fills end = start + 6 (a week); the end can still be edited for a custom range.
$("from").addEventListener("change", () => { if ($("from").value) $("to").value = addDays($("from").value, 6); });
$("apply").addEventListener("click", () => $("from").value && $("to").value && load($("from").value, $("to").value));
function step(dir) {
  const a = $("from").value, b = $("to").value;
  if (!a || !b) return;
  const n = spanDays(a, b) * dir;
  load(addDays(a, n), addDays(b, n));
}
$("prev").addEventListener("click", () => step(-1));
$("next").addEventListener("click", () => step(1));

// ---------------------------------------------------------------- export (PDF / CSV)
const waitFor = (fn, ms) => new Promise((ok) => { const t0 = Date.now(); const tick = () => (fn() || Date.now() - t0 > ms ? ok() : setTimeout(tick, 300)); tick(); });
const csvCell = (v) => { const t = v == null ? "" : String(v); return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t; };

async function exportPdf() {
  if (!lastTracker) return;
  if (!socialDone) {                         // the social block loads last; wait so it is not missing from the PDF
    $("banner").textContent = "Waiting for the social data to finish loading before creating the PDF…";
    $("banner").className = "banner";
    await waitFor(() => socialDone, 120000);
    $("banner").className = "banner hidden";
  }
  const old = document.title;
  document.title = `Wepsol weekly report ${lastTracker.period.start} to ${lastTracker.period.end}`;   // becomes the PDF file name
  window.addEventListener("afterprint", () => { document.title = old; }, { once: true });
  window.print();                            // in the print dialog choose "Save as PDF"
}

function exportCsv() {
  const d = lastTracker, s = lastSocial;
  if (!d) return;
  const out = [];
  const section = (title, rows) => { out.push([title], ...rows, []); };
  const c = d.traffic.current, p = d.traffic.previous;
  section(`Website traffic (GA4) · ${d.period.label} vs ${d.previous.label}`, [
    ["Metric", "Overall", "Overall (previous)", "India", "India (previous)"],
    ...[["Total users", "total_users"], ["New users", "new_users"], ["Sessions", "sessions"], ["Engagement rate (%)", "engagement_rate"], ["Avg session duration (seconds)", "avg_session_duration_sec"]]
      .map(([l, k]) => { const f = (v) => (k === "engagement_rate" ? Math.round(v * 1000) / 10 : k === "avg_session_duration_sec" ? Math.round(v) : v);
        return [l, f(c.overall[k]), f(p.overall[k]), f(c.india[k]), f(p.india[k])]; }),
    ...cfg.channels.map((ch) => [`${ch} (users)`, c.channels_overall[ch], p.channels_overall[ch], c.channels_india[ch], p.channels_india[ch]]),
  ]);
  const k = d.keywords.current, kp = d.keywords.previous;
  const buckets = [["Position 1-5", "1-5"], ["Position 6-10", "6-10"], ["Position 11-20", "11-20"], ["Position 21-50", "21-50"], ["Position 51-100", "51-100"],
    ["Total keywords (with volume)", "total"], ["Branded", "branded"], ["Non-branded", "non_branded"], ["No volume (ranking 1-100)", "no_volume"]];
  section("Keywords · India · Search Console with Keyword Planner volume", [
    ["Rank", "Exclusive of blogs", "Exclusive of blogs (previous)", "Inclusive of blogs", "Inclusive of blogs (previous)"],
    ...buckets.map(([l, key]) => [l, k.no_blogs[key], kp.no_blogs[key], k.all[key], kp.all[key]]),
  ]);
  const prods = Object.keys(k.products);
  section("Keywords by product", [
    ["Rank", ...prods.flatMap((x) => [k.products[x].label, `${k.products[x].label} (previous)`])],
    ...buckets.map(([l, key]) => [l, ...prods.flatMap((x) => [k.products[x][key], kp.products[x][key]])]),
  ]);
  if (s) {
    const rows = [["Platform", "Metric", "This period", "Previous period"]];
    for (const key of ["linkedin", "facebook", "instagram"]) {
      const pl = s.platforms[key];
      if (!pl) continue;
      rows.push([PNAME[key], "Followers", pl.followers, ""]);
      for (const [n, v] of pl.metrics) rows.push([PNAME[key], n, v.cur, v.prev]);
    }
    section(`Social media · ${s.period.label}`, rows);
    section("LinkedIn posts", [["Date", "Product", "Post type", "Reactions", "Comments", "Shares", "Engagement", "Link"],
      ...(s.li_posts || []).map((x) => [x.date, x.product, x.ptype, x.likes, x.comments, x.shares, x.engagement, x.url])]);
  }
  const text = "\ufeff" + out.map((r) => r.map(csvCell).join(",")).join("\n");   // BOM so Excel reads UTF-8
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  a.download = `wepsol-weekly-report-${d.period.start}_${d.period.end}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

const exportMenu = $("exportMenu");
$("exportBtn").addEventListener("click", (e) => { e.stopPropagation(); exportMenu.hidden = !exportMenu.hidden; });
document.addEventListener("click", () => { exportMenu.hidden = true; });
exportMenu.addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-f]");
  if (!b) return;
  exportMenu.hidden = true;
  if (b.dataset.f === "pdf") await exportPdf(); else exportCsv();
});

(async () => {
  cfg = await (await fetch("/api/config")).json();
  const qs = new URLSearchParams(location.search);   // e.g. /?start=2026-11-10&end=2026-11-16
  load(qs.get("start") || cfg.default_start, qs.get("end") || cfg.default_end);
})();
