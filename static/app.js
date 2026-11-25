const $ = (id) => document.getElementById(id);
// every data request goes through the one function file, which hosts like Vercel route reliably: /api/index?op=...&start=...&end=...
const apiUrl = (op, q = "") => "/api/index?op=" + op + q.replace("?", "&");
const fmt = (n) => (n == null ? "—" : Math.round(n).toLocaleString("en-IN"));
const pct = (x) => (x == null ? "—" : (x * 100).toFixed(1) + "%");
const dur = (s) => (s == null ? "—" : `${Math.floor(s / 60)}m ${String(Math.round(s % 60)).padStart(2, "0")}s`);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const addDays = (iso, n) => { const d = new Date(iso + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const spanDays = (a, b) => Math.round((new Date(b) - new Date(a)) / 864e5) + 1;
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const dayName = (iso) => `${+iso.slice(8)} ${MON[+iso.slice(5, 7) - 1]}`;
const rangeLabel = (a, b) => (a.slice(5, 7) === b.slice(5, 7) ? `${+a.slice(8)}–${dayName(b)}` : `${dayName(a)} – ${dayName(b)}`);
const weekName = (a, b) => (spanDays(a, b) === 7 ? `Week ${dayName(a)}` : "Period " + dayName(a));

/** Change vs the earlier column. ratio: percentage points. */
function dl(cur, prev, { ratio = false, stack = false } = {}) {
  if (cur == null || prev == null || (!ratio && !prev)) return "";
  const d = ratio ? (cur - prev) * 100 : ((cur - prev) / prev) * 100;
  if (!isFinite(d)) return "";
  const k = stack ? "dstack" : "d";
  if (Math.abs(d) < 0.05) return `<span class="${k} flat">${ratio ? "0.0 pts" : "0.0%"}</span>`;
  return `<span class="${k} ${d > 0 ? "up" : "down"}">${d > 0 ? "▲" : "▼"} ${Math.abs(d).toFixed(1)}${ratio ? " pts" : "%"}</span>`;
}

let cfg, runId = 0, D = null, S = null, socialDone = true;
const ui = { scope: "india", group: "site", blogs: "all", liWeek: 2 };

// ---------------------------------------------------------------- loading
async function load(start, end) {
  const id = ++runId;
  document.querySelector(".content").classList.add("loading");
  $("banner").className = "banner hidden";
  const q = `?start=${start}&end=${end}`;
  buildPicker(start, end);
  loadSocial(q, id);
  try {
    const r = await fetch(apiUrl("tracker", q));
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    const d = await r.json();
    if (id === runId) render(d);
  } catch (e) {
    $("banner").textContent = e.message;
    $("banner").className = "banner err";
  } finally {
    if (id === runId) document.querySelector(".content").classList.remove("loading");
  }
}

function buildPicker(start, end) {
  const n = spanDays(start, end), opts = [];
  const seen = new Set();
  const add = (a, b) => { const v = a + "|" + b; if (seen.has(v)) return; seen.add(v); opts.push([v, `${weekName(a, b)} ${a.slice(0, 4)} · ${rangeLabel(a, b)}`]); };
  let a = cfg.default_start, b = cfg.default_end;
  for (let i = 0; i < 12; i++) { add(a, b); a = addDays(a, -7); b = addDays(b, -7); }
  if (!seen.has(start + "|" + end)) opts.unshift([start + "|" + end, `${rangeLabel(start, end)} (custom)`]);
  $("weekSelect").innerHTML = opts.map(([v, t]) => `<option value="${v}">${t}</option>`).join("") + `<option value="custom">Custom range…</option>`;
  $("weekSelect").value = start + "|" + end;
  $("from").value = start; $("to").value = end;
  $("custom").hidden = true;
}

function render(d) {
  D = d;
  const s = d.period.start, e = d.period.end, ps = d.previous.start, pe = d.previous.end;
  document.title = `Executive Snapshot - ${weekName(s, e)} ${s.slice(0, 4)}`;
  $("weekTitle").textContent = `${weekName(s, e)} ${s.slice(0, 4)}`;
  $("rangeText").textContent = `${dayName(s)} – ${dayName(e)}`;
  const t = d.periods;
  $("compareText").textContent = `Compared with ${weekName(t[1].start, t[1].end)} and ${weekName(t[0].start, t[0].end)}`;
  $("dataThrough").textContent = `Data through ${dayName(cfg.latest_date)}`;
  if (d.mode === "sample") {
    $("banner").textContent = "Showing SAMPLE data — Google credentials are not configured.";
    $("banner").className = "banner";
  } else if (e > cfg.latest_date) {
    $("banner").textContent = `This period is still in progress — data runs to ${cfg.latest_date}, so totals will be lower than a full week.`;
    $("banner").className = "banner";
  }
  renderTraffic();
  renderSearch();
}

// ---------------------------------------------------------------- 01 traffic
function weekHead(p, i, n, cols = 1, cls = "wk") {
  const cur = i === n - 1;
  return `<th class="${cls} ${cur ? "cur" : ""}" colspan="${cols}">${weekName(p.start, p.end)}${cur ? ' <span class="latest">LATEST</span>' : ""}<small>${rangeLabel(p.start, p.end)}</small></th>`;
}

function renderTraffic() {
  const P = D.periods, n = P.length;
  const rows = [
    ["Traffic", null],
    ["Total Traffic", (x) => fmt(x.total_users), "total_users"], ["New Users", (x) => fmt(x.new_users), "new_users"], ["Session", (x) => fmt(x.sessions), "sessions"],
    ["Quality", null],
    ["Engagement Rate", (x) => pct(x.engagement_rate), "engagement_rate", true], ["Avg Session Duration", (x) => dur(x.avg_session_duration_sec), "avg_session_duration_sec"],
    ["Channels", null],
  ];
  let h = `<tr><th class="first" rowspan="2">Metric</th>${P.map((p, i) => weekHead(p, i, n, 2)).join("")}</tr><tr>${P.map(() => `<th class="lw">India</th><th>Overall</th>`).join("")}</tr>`;
  const cell = (val, dh, i, ov) => `<td class="${i === n - 1 ? "cur" : ""} ${ov ? "ov" : "lw"}">${val}${dh}</td>`;
  for (const r of rows) {
    if (!r[1]) { h += `<tr class="sec"><td colspan="${1 + 2 * n}">${r[0]}</td></tr>`; continue; }
    const [label, f, key, ratio] = r;
    h += `<tr><td class="first">${label}</td>` + P.map((p, i) => {
      const g = p.ga, pg = i ? P[i - 1].ga : null;
      return cell(f(g.india), pg ? dl(g.india[key], pg.india[key], { ratio }) : "", i, false) + cell(f(g.overall), pg ? dl(g.overall[key], pg.overall[key], { ratio }) : "", i, true);
    }).join("") + `</tr>`;
  }
  for (const ch of cfg.channels) {
    h += `<tr><td class="first">${ch}</td>` + P.map((p, i) => {
      const g = p.ga, pg = i ? P[i - 1].ga : null;
      return cell(fmt(g.channels_india[ch]), pg ? dl(g.channels_india[ch], pg.channels_india[ch]) : "", i, false) +
        cell(fmt(g.channels_overall[ch]), pg ? dl(g.channels_overall[ch], pg.channels_overall[ch]) : "", i, true);
    }).join("") + `</tr>`;
  }
  $("trafficTable").innerHTML = h;
  $("trafficNote").innerHTML = "<b>India</b> = visitors in India. <b>Overall</b> = visitors from every country, leaving out the traffic the Weekly Report filters as bot traffic. Career and job pages are left out of India. Channel rows count users; AI assistants and unassigned traffic are inside Total Traffic but have no row of their own.";
  drawTraffic();
}

const COL = { users: "#e4004f", sessions: "#1e2f8a", news: "#0f8a7a" };
const CHCOL = { Direct: "#1e3a8a", Organic: "#0f766e", Referral: "#d4930d", Social: "#be185d", "Paid+Display": "#7c3aed" };

function niceMax(v) {
  const m = Math.max(v * 1.12, 4), mag = Math.pow(10, Math.floor(Math.log10(m))), step = mag / 2;
  return Math.ceil(m / step) * step;
}
function axes(W, H, m, max) {
  let s = "";
  for (let i = 0; i <= 4; i++) {
    const v = (max / 4) * i, y = H - m.b - (v / max) * (H - m.t - m.b);
    s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y}" y2="${y}" stroke="rgba(20,22,31,.08)" stroke-dasharray="${i ? "3 4" : ""}"/><text x="${m.l - 8}" y="${y + 4}" text-anchor="end" font-size="11" fill="#6b7280">${fmt(v)}</text>`;
  }
  return s;
}
const xLabels = (P, x, H) => P.map((p, i) => `<text x="${x(i)}" y="${H - 22}" text-anchor="middle" font-size="12" font-weight="600" fill="#14161f">${weekName(p.start, p.end)}</text><text x="${x(i)}" y="${H - 7}" text-anchor="middle" font-size="11" fill="#6b7280">${rangeLabel(p.start, p.end)}</text>`).join("");

function drawTraffic() {
  const P = D.periods, sc = ui.scope, g = (p) => p.ga[sc];
  // line chart
  const W = 560, H = 330, m = { l: 48, r: 30, t: 24, b: 44 };
  const series = [["total_users", COL.users], ["sessions", COL.sessions], ["new_users", COL.news]];
  const max = niceMax(Math.max(...P.flatMap((p) => series.map(([k]) => g(p)[k]))));
  const x = (i) => m.l + 40 + (i * (W - m.l - m.r - 80)) / Math.max(1, P.length - 1);
  const y = (v) => H - m.b - (v / max) * (H - m.t - m.b);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Traffic trend">` + axes(W, H, m, max) + xLabels(P, x, H);
  const main = series[0];
  s += `<path d="M${P.map((p, i) => `${x(i)},${y(g(p)[main[0]])}`).join(" L")} L${x(P.length - 1)},${y(0)} L${x(0)},${y(0)} Z" fill="${COL.users}" opacity=".08"/>`;
  for (const [k, col] of series) {
    s += `<polyline fill="none" stroke="${col}" stroke-width="2.5" points="${P.map((p, i) => `${x(i)},${y(g(p)[k])}`).join(" ")}"/>`;
    P.forEach((p, i) => { s += `<circle cx="${x(i)}" cy="${y(g(p)[k])}" r="5" fill="#fff" stroke="${col}" stroke-width="2.5"/><text x="${x(i)}" y="${y(g(p)[k]) - 11}" text-anchor="middle" font-size="12" font-weight="700" fill="${col}">${fmt(g(p)[k])}</text>`; });
  }
  $("trendChart").innerHTML = s + "</svg>";
  // stacked channel bars (users)
  const chs = cfg.channels, key = sc === "india" ? "channels_india" : "channels_overall";
  const tot = P.map((p) => chs.reduce((a, c) => a + (p.ga[key][c] || 0), 0));
  const cmax = niceMax(Math.max(...tot)), cy = (v) => H - m.b - (v / cmax) * (H - m.t - m.b);
  const bw = 62, cx = (i) => m.l + 60 + (i * (W - m.l - m.r - 120)) / Math.max(1, P.length - 1);
  s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Channel mix">` + axes(W, H, m, cmax) + xLabels(P, cx, H);
  P.forEach((p, i) => {
    let acc = 0;
    for (const c of chs) {
      const v = p.ga[key][c] || 0;
      if (!v) continue;
      const y0 = cy(acc + v), hgt = cy(acc) - y0;
      s += `<rect x="${cx(i) - bw / 2}" y="${y0}" width="${bw}" height="${hgt}" fill="${CHCOL[c]}"><title>${c}: ${fmt(v)}</title></rect>`;
      if (hgt > 17) s += `<text x="${cx(i)}" y="${y0 + hgt / 2 + 4}" text-anchor="middle" font-size="12" font-weight="700" fill="#fff">${fmt(v)}</text>`;
      acc += v;
    }
  });
  $("channelChart").innerHTML = s + "</svg>";
  $("channelLegend").innerHTML = chs.map((c) => `<span style="--c:${CHCOL[c]}">${c}</span>`).join("");
}

// ---------------------------------------------------------------- 02 search
function kwGroups() {
  const cur = D.keywords.current;
  return [{ key: "site", label: "Whole site" }, ...Object.keys(cur.products).map((k) => ({ key: k, label: cur.products[k].label }))];
}
function kwData(key, blogs) {
  const get = (kw) => (key === "site" ? kw[blogs] : kw.products[key]);
  return [D.keywords.previous2, D.keywords.previous, D.keywords.current].map(get);
}
function kwTable(key, blogs) {
  const P = D.periods, rows = kwData(key, blogs), n = rows.length;
  const row = (label, f, cls = "") => `<tr class="${cls}"><td class="first">${label}</td>${rows.map((o, i) =>
    `<td class="${i === n - 1 ? "cur" : ""}"><b>${fmt(f(o))}</b>${i ? dl(f(o), f(rows[i - 1]), { stack: false }) : ""}</td>`).join("")}</tr>`;
  return `<tr><th class="first">Metric</th>${P.map((p, i) => weekHead(p, i, n)).join("")}</tr>` +
    row("Keywords between 1-10", (o) => o["1-5"] + o["6-10"]) + row("Keywords between 11-20", (o) => o["11-20"]) +
    row("Keywords between 21-50", (o) => o["21-50"]) + row("Keywords between 51-100", (o) => o["51-100"]) +
    row("TOTAL", (o) => o.total, "totalrow");
}
function renderSearch() {
  const groups = kwGroups();
  if (!groups.find((g) => g.key === ui.group)) ui.group = "site";
  $("kwTabs").innerHTML = groups.map((g) => `<button class="${g.key === ui.group ? "on" : ""}" data-g="${g.key}">${esc(g.label)}</button>`).join("");
  $("blogSeg").style.display = ui.group === "site" ? "" : "none";
  [...$("blogSeg").children].forEach((b) => b.classList.toggle("on", b.dataset.b === ui.blogs));
  const g = groups.find((x) => x.key === ui.group);
  $("kwTitle").textContent = ui.group === "site" ? `Whole site · keywords ranking on Google${ui.blogs === "all" ? " (with blogs)" : " (without blogs)"}` : `${g.label} · keywords ranking on Google`;
  $("kwTable").innerHTML = kwTable(ui.group, ui.blogs);
  const cur = D.keywords.current;
  let note = "Queries ranking 1–100 in India that have search volume (Keyword Planner), counted by average position that week. 1–10 is page one.";
  if (ui.group !== "site") note += " " + ({ fluidprint: "fluidPrint: non-blog fluidprint / managed-print pages.", flotax: "floTax: its four product pages.", gst_verification: "GST Verification: every page with “gst” in its URL, so it includes GST blogs and overlaps floTax.", fluidpro: "fluidPro: its service page." }[ui.group] || "");
  if (!cur.volume_applied) note = "Keyword volume is not available, so keywords without Keyword Planner volume are included in these counts.";
  if (cur.volume_warning) note += "  ⚠ " + cur.volume_warning;
  $("kwNote").textContent = note;
  drawKw();
  // PDF prints every tab, not just the selected one
  $("kwPrint").innerHTML = groups.map((x) => `<div class="panel" style="margin-top:14px"><h4>${esc(x.label)}${x.key === "site" ? " · inclusive of blogs" : ""}</h4><table class="grid small">${kwTable(x.key, "all")}</table></div>`).join("") +
    `<div class="panel" style="margin-top:14px"><h4>Whole site · exclusive of blogs</h4><table class="grid small">${kwTable("site", "no_blogs")}</table></div>`;
}
function drawKw() {
  const P = D.periods, rows = kwData(ui.group, ui.blogs);
  const ser = [["1–10", "#e4004f", (o) => o["1-5"] + o["6-10"]], ["11–20", "#f59e0b", (o) => o["11-20"]], ["21–50", "#475569", (o) => o["21-50"]]];
  const W = 520, H = 330, m = { l: 44, r: 20, t: 26, b: 44 };
  const max = niceMax(Math.max(...rows.flatMap((o) => ser.map(([, , f]) => f(o)))));
  const y = (v) => H - m.b - (v / max) * (H - m.t - m.b);
  const gw = (W - m.l - m.r) / P.length, bw = Math.min(30, gw / 4);
  const gx = (i) => m.l + gw * i + gw / 2;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Keywords by position band">` + axes(W, H, m, max) + xLabels(P, gx, H);
  rows.forEach((o, i) => ser.forEach(([name, col, f], j) => {
    const v = f(o), bx = gx(i) + (j - 1) * (bw + 4) - bw / 2;
    s += `<rect x="${bx}" y="${y(v)}" width="${bw}" height="${y(0) - y(v)}" rx="3" fill="${col}"><title>${name}: ${fmt(v)}</title></rect><text x="${bx + bw / 2}" y="${y(v) - 6}" text-anchor="middle" font-size="11.5" font-weight="700" fill="${col}">${fmt(v)}</text>`;
  }));
  $("kwChart").innerHTML = s + "</svg>";
}

// ---------------------------------------------------------------- 03 social
const PCOL = { facebook: "#1e40af", instagram: "#be185d", linkedin: "#0a66c2" };
const PNAME = { linkedin: "LinkedIn stats", facebook: "Facebook", instagram: "Instagram" };

async function loadSocial(q, id) {
  socialDone = false; S = null;
  if (!cfg.social) {
    socialDone = true;
    $("socialSub").textContent = "Social is not configured (add META_ACCESS_TOKEN, META_PAGE_ID, IG_USER_ID).";
    return;
  }
  $("socialSub").innerHTML = `<span class="spin"></span>Loading Facebook, Instagram and LinkedIn (this can take up to a minute)…`;
  $("platforms").innerHTML = $("liBreakdown").innerHTML = $("liCards").innerHTML = $("liNote").textContent = $("socialFoot").textContent = "";
  $("liWeekSeg").innerHTML = "";
  try {
    const r = await fetch(apiUrl("social", q));
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    const s = await r.json();
    if (id === runId) { S = s; ui.liWeek = 2; renderSocial(); }
  } catch (e) {
    if (id === runId) $("socialSub").innerHTML = `<span style="color:var(--bad)">${esc(e.message)}</span>`;
  } finally {
    if (id === runId) socialDone = true;
  }
}

function renderSocial() {
  const s = S, W = [...s.li_weeks].reverse();       // oldest first, like the other sections
  $("socialSub").textContent = "";
  const head = `<tr><th class="first">Metrics</th>${W.map((w, i) => `<th class="${i === 2 ? "cur" : ""}">${weekName(w.start, w.end).toUpperCase()}</th>`).join("")}</tr>`;
  let cards = "";
  for (const key of ["linkedin", "facebook", "instagram"]) {
    const p = s.platforms[key];
    let body;
    if (!p) body = `<div class="err">Could not load: ${esc(s.errors[key] || "unknown error")}</div>`;
    else {
      const rowsHtml = [];
      if (key === "linkedin") rowsHtml.push(`<tr><td class="first">Followers</td><td class="na">–</td><td class="na">–</td><td class="cur"><b>${fmt(p.followers)}</b></td></tr>`);
      for (const [name, v] of p.metrics) {
        const vals = [v.prev2, v.prev, v.cur];
        rowsHtml.push(`<tr><td class="first">${esc(name)}</td>${vals.map((x, i) => `<td class="${i === 2 ? "cur" : ""}">${x == null ? '<span class="na">–</span>' : `<b>${fmt(x)}</b>`}${i ? dl(x, vals[i - 1], { stack: true }) : ""}</td>`).join("")}</tr>`);
      }
      body = `<table class="grid small">${head}${rowsHtml.join("")}</table>` +
        (p.admin_error ? `<div class="warn">${esc(p.admin_error)}</div>` : "") +
        (p.unavailable && p.unavailable.length ? `<div class="warn">${p.unavailable.join(", ")}: needs LinkedIn admin data.</div>` : "");
    }
    cards += `<div class="panel pcard" style="--c:${PCOL[key]}"><h5><i></i>${PNAME[key]}</h5>${body}</div>`;
  }
  $("platforms").innerHTML = cards;
  $("liWeekSeg").innerHTML = W.map((w, i) => `<button class="${i === ui.liWeek ? "on" : ""}" data-w="${i}">${weekName(w.start, w.end)}</button>`).join("");
  renderLiPosts();
  $("socialFoot").textContent = (s.notes || []).join(" ");
}

const PRODCOL = { fluidPrint: "#1e2f8a", fluidPro: "#0f8a7a", floTax: "#b45309", "Company / brand": "#6b7280" };

function renderLiPosts() {
  const w = [...S.li_weeks].reverse()[ui.liWeek], posts = w.posts, rows = w.breakdown;
  [...$("liWeekSeg").children].forEach((b) => b.classList.toggle("on", +b.dataset.w === ui.liWeek));
  let h = `<tr><th>Product</th><th>Post type</th><th>Posts</th><th>Reactions</th><th>Comments</th><th>Shares</th><th>Engagement</th></tr>`;
  if (!w.ok) h += `<tr><td colspan="7" style="text-align:center" class="na">LinkedIn posts could not be loaded for this week</td></tr>`;
  else if (!rows.length) h += `<tr><td colspan="7" style="text-align:center" class="na">No LinkedIn posts in this week</td></tr>`;
  const t = { posts: 0, reactions: 0, comments: 0, shares: 0, engagement: 0 };
  for (const r of rows) for (const x of r.types) {
    h += `<tr><td class="first"><span class="dot" style="background:${PRODCOL[r.product] || "#6b7280"}"></span><b>${esc(r.product)}</b></td><td><span class="chip">${esc(x.type)}</span></td><td>${fmt(x.posts)}</td><td>${fmt(x.reactions)}</td><td>${fmt(x.comments)}</td><td>${fmt(x.shares)}</td><td><b>${fmt(x.engagement)}</b></td></tr>`;
    for (const k in t) t[k] += x[k];
  }
  if (rows.length) h += `<tr class="totalrow"><td class="first">Total</td><td></td><td>${fmt(t.posts)}</td><td>${fmt(t.reactions)}</td><td>${fmt(t.comments)}</td><td>${fmt(t.shares)}</td><td>${fmt(t.engagement)}</td></tr>`;
  $("liBreakdown").innerHTML = h;
  $("liNote").textContent = "A post belongs to the product it names (its product name or hashtag); a post that names none is company/brand. Post type comes from LinkedIn. Engagement = reactions + comments + shares.";
  $("postDetails").hidden = !posts.length;
  $("liCards").innerHTML = posts.map((p) => `
    <a class="pc" href="${esc(p.url || "#")}" target="_blank" rel="noopener">
      <div class="pc-img" style="${p.image ? `background-image:url('${esc(p.image)}')` : ""}">${p.image ? "" : "<span>no image</span>"}
        <span class="badge" style="background:${PRODCOL[p.product] || "#6b7280"}">${esc(p.product)}</span></div>
      <div class="pc-body">
        <div class="pc-meta"><span>${p.date}</span><span class="chip">${esc(p.ptype)}</span></div>
        <p>${esc(p.text)}</p>
        <div class="pc-nums"><div><b>${fmt(p.likes)}</b><small>Reactions</small></div><div><b>${fmt(p.comments)}</b><small>Comments</small></div>
          <div><b>${fmt(p.shares)}</b><small>Shares</small></div><div class="eng"><b>${fmt(p.engagement)}</b><small>Engagement</small></div></div>
      </div>
    </a>`).join("");
}

// ---------------------------------------------------------------- controls
$("scopeSeg").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b || !D) return; ui.scope = b.dataset.s; [...$("scopeSeg").children].forEach((x) => x.classList.toggle("on", x === b)); drawTraffic(); });
$("kwTabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b || !D) return; ui.group = b.dataset.g; renderSearch(); });
$("blogSeg").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b || !D) return; ui.blogs = b.dataset.b; renderSearch(); });
$("liWeekSeg").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b || !S) return; ui.liWeek = +b.dataset.w; renderLiPosts(); });
$("weekSelect").addEventListener("change", () => {
  const v = $("weekSelect").value;
  if (v === "custom") { $("custom").hidden = false; return; }
  const [a, b] = v.split("|"); load(a, b);
});
$("from").addEventListener("change", () => { if ($("from").value) $("to").value = addDays($("from").value, 6); });
$("apply").addEventListener("click", () => $("from").value && $("to").value && load($("from").value, $("to").value));
function step(dir) {
  const a = D ? D.period.start : $("from").value, b = D ? D.period.end : $("to").value;
  if (!a || !b) return;
  const n = spanDays(a, b) * dir;
  load(addDays(a, n), addDays(b, n));
}
$("prev").addEventListener("click", () => step(-1));
$("next").addEventListener("click", () => step(1));
// highlight the sidebar entry of the section in view
const navs = [...document.querySelectorAll(".nav")];
window.addEventListener("scroll", () => {
  let cur = "top";
  for (const id of ["traffic", "search", "social"]) if ($(id).getBoundingClientRect().top < 160) cur = id;
  navs.forEach((n) => n.classList.toggle("active", n.dataset.nav === cur));
}, { passive: true });

// ---------------------------------------------------------------- export (PDF / CSV)
const waitFor = (fn, ms) => new Promise((ok) => { const t0 = Date.now(); const tick = () => (fn() || Date.now() - t0 > ms ? ok() : setTimeout(tick, 300)); tick(); });
const csvCell = (v) => { const t = v == null ? "" : String(v); return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t; };

async function exportPdf() {
  if (!D) return;
  if (!socialDone) {
    $("banner").textContent = "Waiting for the social data to finish loading before creating the PDF…";
    $("banner").className = "banner";
    await waitFor(() => socialDone, 120000);
    $("banner").className = "banner hidden";
  }
  const old = document.title;
  document.title = `Wepsol weekly report ${D.period.start} to ${D.period.end}`;   // becomes the PDF file name
  window.addEventListener("afterprint", () => { document.title = old; }, { once: true });
  window.print();                            // in the print dialog choose "Save as PDF"
}

function exportCsv() {
  const d = D, s = S;
  if (!d) return;
  const out = [];
  const section = (title, rows) => { out.push([title], ...rows, []); };
  const P = d.periods, hdr = (x) => P.map((p) => `${weekName(p.start, p.end)} ${x}`);
  const f2 = (k, v) => (v == null ? "" : k === "engagement_rate" ? Math.round(v * 1000) / 10 : k === "avg_session_duration_sec" ? Math.round(v) : v);
  section("Website traffic (GA4)", [
    ["Metric", ...P.flatMap((p) => [`${weekName(p.start, p.end)} India`, `${weekName(p.start, p.end)} Overall`])],
    ...[["Total users", "total_users"], ["New users", "new_users"], ["Sessions", "sessions"], ["Engagement rate (%)", "engagement_rate"], ["Avg session duration (seconds)", "avg_session_duration_sec"]]
      .map(([l, k]) => [l, ...P.flatMap((p) => [f2(k, p.ga.india[k]), f2(k, p.ga.overall[k])])]),
    ...cfg.channels.map((ch) => [`${ch} (users)`, ...P.flatMap((p) => [p.ga.channels_india[ch], p.ga.channels_overall[ch]])]),
  ]);
  const buckets = [["Position 1-5", "1-5"], ["Position 6-10", "6-10"], ["Position 11-20", "11-20"], ["Position 21-50", "21-50"], ["Position 51-100", "51-100"],
    ["Total keywords (with volume)", "total"], ["Branded", "branded"], ["Non-branded", "non_branded"], ["No volume (ranking 1-100)", "no_volume"]];
  for (const g of kwGroups()) {
    const sets = g.key === "site" ? [["inclusive of blogs", "all"], ["exclusive of blogs", "no_blogs"]] : [["", "all"]];
    for (const [tag, b] of sets) {
      const rows = kwData(g.key, b);
      section(`Keywords · India · ${g.label} ${tag}`.trim(), [["Rank", ...hdr("")], ...buckets.map(([l, key]) => [l, ...rows.map((o) => o[key])])]);
    }
  }
  if (s) {
    const W = [...s.li_weeks].reverse();
    const rows = [["Platform", "Metric", ...W.map((w) => weekName(w.start, w.end))]];
    for (const key of ["linkedin", "facebook", "instagram"]) {
      const pl = s.platforms[key];
      if (!pl) continue;
      for (const [n, v] of pl.metrics) rows.push([PNAME[key], n, v.prev2, v.prev, v.cur]);
    }
    section("Social media", rows);
    for (const w of W) section(`LinkedIn posts · ${weekName(w.start, w.end)}`, [["Date", "Product", "Post type", "Reactions", "Comments", "Shares", "Engagement", "Link"],
      ...w.posts.map((x) => [x.date, x.product, x.ptype, x.likes, x.comments, x.shares, x.engagement, x.url])]);
  }
  const text = "﻿" + out.map((r) => r.map(csvCell).join(",")).join("\n");   // BOM so Excel reads UTF-8
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  a.download = `wepsol-weekly-report-${d.period.start}_${d.period.end}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
$("pdfBtn").addEventListener("click", exportPdf);
$("csvBtn").addEventListener("click", exportCsv);

(async () => {
  cfg = await (await fetch(apiUrl("config"))).json();
  const qs = new URLSearchParams(location.search);   // e.g. /?start=2026-11-10&end=2026-11-16
  load(qs.get("start") || cfg.default_start, qs.get("end") || cfg.default_end);
})();
