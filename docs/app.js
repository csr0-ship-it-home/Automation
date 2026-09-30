(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
  };
  const pct = (x, d = 1, sign = true) => x == null ? "—" : `${sign && x > 0 ? "+" : ""}${(x * 100).toFixed(d)}%`;
  const num = (x, d = 2) => x == null ? "—" : Number(x).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  const cls = (x) => x == null ? "" : x > 0 ? "up" : x < 0 ? "down" : "";
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  const FACTOR_LABELS = {
    curve_steepening: "Yield curve steepening", rates_falling: "Rates falling (easing)", credit_stress: "Credit stress",
    recession_risk: "Recession risk", inflation_pressure: "Inflation pressure", dollar_strength: "Dollar strengthening",
    real_yields_rising: "Real yields rising", fear_contrarian: "Fear elevated (VIX)", oil_up: "Oil rising",
  };
  const FACTOR_OPPOSITE = {
    curve_steepening: "Yield curve flattening", rates_falling: "Rates rising (tightening)", credit_stress: "Credit calm",
    recession_risk: "Low recession risk", inflation_pressure: "Inflation cooling", dollar_strength: "Dollar weakening",
    real_yields_rising: "Real yields falling", fear_contrarian: "Fear low (VIX)", oil_up: "Oil falling",
  };
  const factorName = (k) => ((DATA.macro_factors[k] || 0) < 0 ? FACTOR_OPPOSITE[k] : FACTOR_LABELS[k]) || k;
  const COMP = [["trend", "Trend", 25], ["momentum", "Momentum", 20], ["value", "Value", 20], ["timing", "Timing", 15], ["macro", "Macro", 20]];
  const SEV_LABEL = { opportunity: "Opportunity", warning: "Warning", info: "Info" };
  const VERDICT = { reliable: "Historically reliable", mixed: "Mixed track record", unreliable: "Historically unreliable", insufficient: "Few past cases" };

  let DATA, HISTORY = [], LOG = [], bySym = {};
  let alertFilter = "all", group = store.get("mts.group", "all"), sortKey = "score", sortDir = -1, showAllAlerts = false;

  // ---------- theme ----------
  const theme = store.get("mts.theme", null);
  if (theme) document.documentElement.dataset.theme = theme;
  $("#themeBtn").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    store.set("mts.theme", document.documentElement.dataset.theme);
    if (DATA) renderAll();
  });

  // ---------- color helpers (diverging: red <- gray -> blue) ----------
  function hexRgb(h) { h = h.replace("#", ""); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)); }
  function mix(a, b, t) { const A = hexRgb(a), B = hexRgb(b); return `rgb(${A.map((v, i) => Math.round(v + (B[i] - v) * t)).join(",")})`; }
  function divColor(v) { // v in [-1, 1]
    const t = Math.min(1, Math.abs(v));
    return mix(css("--mid"), v >= 0 ? css("--pos") : css("--neg"), Math.pow(t, 0.8));
  }
  const scoreColor = (s) => divColor((s - 50) / 30);
  function inkOn(bg) { const m = bg.match(/\d+/g).map(Number); const L = (0.299 * m[0] + 0.587 * m[1] + 0.114 * m[2]) / 255; return L > 0.6 ? "#0b0b0b" : "#ffffff"; }

  // ---------- tooltip ----------
  const tip = $("#tip");
  function showTip(html, x, y) {
    tip.innerHTML = html; tip.hidden = false;
    const r = tip.getBoundingClientRect();
    let left = x + 14, top = y + 14;
    if (left + r.width > innerWidth - 8) left = x - r.width - 14;
    if (top + r.height > innerHeight - 8) top = y - r.height - 14;
    tip.style.left = `${Math.max(8, left)}px`; tip.style.top = `${Math.max(8, top)}px`;
  }
  const hideTip = () => { tip.hidden = true; };

  // ---------- load ----------
  async function load() {
    const get = (u) => fetch(u, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    [DATA, HISTORY, LOG] = await Promise.all([get("data/latest.json"), get("data/history.json"), get("data/alert_log.json")]);
    if (!DATA) { $("#updated").textContent = "No data yet: run the GitHub Action (see README)."; return; }
    HISTORY = HISTORY || []; LOG = LOG || [];
    bySym = Object.fromEntries(DATA.assets.map((a) => [a.symbol, a]));
    renderAll();
    browserNotify();
    const hash = decodeURIComponent(location.hash.slice(1));
    if (bySym[hash]) openDetail(hash);
  }

  function renderAll() {
    const t = new Date(DATA.generated_at);
    $("#updated").textContent = `Updated ${t.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })} · ${DATA.assets.length} assets · ${DATA.gauges.length} macro indicators`;
    $("#demoBanner").hidden = !DATA.demo;
    const errs = Object.keys(DATA.errors || {});
    const eb = $("#errBanner");
    eb.hidden = !errs.length;
    if (errs.length) eb.innerHTML = `<strong>Some data could not be fetched on the last run:</strong> ${esc(errs.join(", "))}. The affected items are skipped.`;
    renderSummary(); renderAlerts(); renderStyleBox(); renderPairs(); renderTabs(); renderTable(); renderMacro(); renderLog();
  }

  // ---------- summary ----------
  function renderSummary() {
    const r = DATA.regime;
    const opp = DATA.alerts.filter((a) => a.severity === "opportunity").length;
    const warn = DATA.alerts.filter((a) => a.severity === "warning").length;
    const fresh = DATA.alerts.filter((a) => a.new).length;
    const sorted = [...DATA.assets].sort((a, b) => b.score - a.score);
    const li = (a) => `<li data-sym="${esc(a.symbol)}"><span><span class="sym">${esc(a.symbol)}</span> <span class="hint">${esc(a.name)}</span></span><span>${a.score}</span></li>`;
    $("#summary").innerHTML = `
      <div class="tile">
        <div class="label">Market regime</div>
        <div class="big">${esc(r.label)} <span class="hint" style="font-size:16px">${r.score > 0 ? "+" : ""}${r.score}</span></div>
        <div class="regime-bar" title="Regime score ${r.score} on a −100…+100 scale"><i style="left:${(r.score + 100) / 2}%"></i></div>
        <div class="axis-ends"><span>Risk-off −100</span><span>+100 Risk-on</span></div>
        <div class="small" style="margin-top:6px">${esc(r.summary)}</div>
      </div>
      <div class="tile">
        <div class="label">Active alerts</div>
        <div class="big">${DATA.alerts.length}</div>
        <div class="small"><span class="chip opportunity">${opp} opportunities</span> <span class="chip warning">${warn} warnings</span></div>
        <div class="small" style="margin-top:6px">${fresh} new since the previous update</div>
      </div>
      <div class="tile"><div class="label">Highest scores</div><ol>${sorted.slice(0, 5).map(li).join("")}</ol></div>
      <div class="tile"><div class="label">Lowest scores</div><ol>${sorted.slice(-5).reverse().map(li).join("")}</ol></div>`;
    $("#summary").querySelectorAll("li[data-sym]").forEach((el) => el.addEventListener("click", () => openDetail(el.dataset.sym)));
  }

  // ---------- alerts ----------
  function btLine(bt) {
    if (!bt || !bt.h63) return "";
    const h = bt.h63, b = bt.base63 || {};
    return `<div class="bt">
      <span class="chip ${esc(bt.verdict)}">${VERDICT[bt.verdict] || ""}</span>
      <span>Next 3 months after this signal: <b>${pct(h.avg)}</b> avg, <b>${Math.round(h.win * 100)}%</b> positive (${bt.episodes} past cases)</span>
      <span>Normal 3-month period: ${pct(b.avg)} avg, ${b.win != null ? Math.round(b.win * 100) : "—"}% positive</span>
      ${bt.h126 ? `<span>6 months after: ${pct(bt.h126.avg)} avg</span>` : ""}
    </div>`;
  }
  function alertHtml(a) {
    const sym = a.symbol ? `<span class="link" data-sym="${esc(a.symbol)}">${esc(a.symbol)}</span>` : "";
    return `<div class="alert ${esc(a.severity)}">
      <div class="alert-title">${a.new ? '<span class="chip new">NEW</span>' : ""}<span class="chip ${esc(a.severity)}">${SEV_LABEL[a.severity]}</span>${sym}<span>${esc(a.title.replace(/^[A-Z]+: /, ""))}</span></div>
      <div class="detail">${esc(a.detail)}</div>
      ${btLine(a.backtest)}
      <div class="hint">Active since ${esc(a.first_seen)}${a.scope === "macro" ? " · macro" : ""}</div>
    </div>`;
  }
  function renderAlerts() {
    const list = DATA.alerts.filter((a) => alertFilter === "all" || a.severity === alertFilter);
    const shown = showAllAlerts ? list : list.slice(0, 12);
    const el = $("#alerts");
    el.innerHTML = shown.length ? shown.map(alertHtml).join("") : `<div class="empty">No ${alertFilter === "all" ? "" : SEV_LABEL[alertFilter].toLowerCase() + " "}alerts right now.</div>`;
    if (list.length > 12) el.insertAdjacentHTML("beforeend", `<button class="btn more" id="moreAlerts">${showAllAlerts ? "Show fewer" : `Show all ${list.length}`}</button>`);
    el.querySelectorAll("[data-sym]").forEach((s) => s.addEventListener("click", () => openDetail(s.dataset.sym)));
    const more = $("#moreAlerts");
    if (more) more.addEventListener("click", () => { showAllAlerts = !showAllAlerts; renderAlerts(); });
  }
  $("#alertFilter").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    alertFilter = b.dataset.f;
    $("#alertFilter").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    renderAlerts();
  });

  // ---------- style box ----------
  function renderStyleBox() {
    const sizes = ["Large", "Mid", "Small"], styles = ["Value", "Blend", "Growth"];
    let h = `<div class="sbox"><div></div>${styles.map((s) => `<div class="hd">${s}</div>`).join("")}`;
    for (const size of sizes) {
      h += `<div class="hd row-hd">${size}</div>`;
      for (const style of styles) {
        const a = DATA.assets.find((x) => x.size === size && x.style === style);
        if (!a) { h += `<div class="cell" style="background:var(--surface-2)">—</div>`; continue; }
        const bg = scoreColor(a.score);
        h += `<div class="cell" data-sym="${esc(a.symbol)}" style="background:${bg};color:${inkOn(bg)}">
          <span class="n">${a.score}</span><span class="s">${esc(a.symbol)} · ${esc(a.rating)}</span><span class="s">3m ${pct(a.metrics.r3m, 0)}</span></div>`;
      }
    }
    h += `</div><div class="scale"><span>20 Avoid</span><span class="bar"></span><span>Strong Buy 80</span></div>`;
    $("#stylebox").innerHTML = h;
    $("#stylebox").querySelectorAll("[data-sym]").forEach((c) => {
      c.addEventListener("click", () => openDetail(c.dataset.sym));
      c.addEventListener("mousemove", (e) => { const a = bySym[c.dataset.sym]; showTip(`<b>${esc(a.name)}</b><br>Score ${a.score} (${esc(a.rating)})<br>12m ${pct(a.metrics.r12m)} · RSI ${a.metrics.rsi14}`, e.clientX, e.clientY); });
      c.addEventListener("mouseleave", hideTip);
    });
  }

  // ---------- pairs ----------
  function renderPairs() {
    $("#pairs").innerHTML = DATA.pairs.map((p) => `
      <div class="pair">
        <div><div class="pl">${esc(p.label)}</div><div class="pr">${esc(p.read)} · 3m ${pct(p.r3m)} · 12m ${pct(p.r12m)}</div></div>
        <div><div class="track" title="${Math.round(p.pct10y * 100)}th percentile of its ~10-year range"><i style="left:${p.pct10y * 100}%"></i></div>
        <div class="track-ends"><span>${esc(p.a)} cheap</span><span>${Math.round(p.pct10y * 100)}th pct</span><span>${esc(p.a)} rich</span></div></div>
      </div>`).join("") || `<div class="empty">No pair data.</div>`;
  }

  // ---------- rankings ----------
  function renderTabs() {
    const tabs = [{ id: "all", label: "All" }, ...DATA.groups];
    $("#groupTabs").innerHTML = tabs.map((g) => `<button data-g="${g.id}" class="${g.id === group ? "on" : ""}">${esc(g.label)}</button>`).join("");
    $("#groupTabs").onclick = (e) => {
      const b = e.target.closest("button"); if (!b) return;
      group = b.dataset.g; store.set("mts.group", group); renderTabs(); renderTable();
    };
  }
  const COLS = [
    ["symbol", "Symbol", (a) => a.symbol, "l"], ["name", "Name", (a) => a.name, "l"],
    ["score", "Score", (a) => a.score], ["rating", "Rating", (a) => a.score],
    ["r1m", "1M", (a) => a.metrics.r1m], ["r3m", "3M", (a) => a.metrics.r3m], ["r12m", "12M", (a) => a.metrics.r12m],
    ["ytd", "YTD", (a) => a.metrics.ytd], ["vs200", "vs 200d", (a) => a.metrics.vs_sma200], ["rsi", "RSI", (a) => a.metrics.rsi14],
    ["dd", "From 52w high", (a) => a.metrics.dd52], ["rel", "Rel. vs SPY (10y pct)", (a) => a.metrics.rel ? a.metrics.rel.pct10y : null],
    ["sig", "Signals", (a) => a.signals.length],
  ];
  function renderTable() {
    const col = COLS.find((c) => c[0] === sortKey) || COLS[2];
    const rows = DATA.assets.filter((a) => group === "all" || a.group === group)
      .sort((a, b) => { const x = col[2](a), y = col[2](b); if (x == null) return 1; if (y == null) return -1; return (x > y ? 1 : x < y ? -1 : 0) * sortDir; });
    const th = COLS.map((c) => `<th class="${c[3] || ""}" data-k="${c[0]}" aria-sort="${c[0] === sortKey ? (sortDir > 0 ? "ascending" : "descending") : "none"}">${c[1]}${c[0] === sortKey ? (sortDir > 0 ? " ▲" : " ▼") : ""}</th>`).join("");
    const td = (a) => {
      const m = a.metrics, bg = scoreColor(a.score);
      const relp = m.rel && m.rel.pct10y != null ? `${Math.round(m.rel.pct10y * 100)}` : "—";
      const rsiCls = m.rsi14 < 30 ? "up" : m.rsi14 > 70 ? "down" : "";
      return `<tr data-sym="${esc(a.symbol)}">
        <td class="l sym">${esc(a.symbol)}</td><td class="l nm" title="${esc(a.name)}">${esc(a.name)}</td>
        <td><span class="scorecell"><span class="scorebar"><i style="width:${a.score}%;background:${bg}"></i></span>${a.score}</span></td>
        <td>${esc(a.rating)}</td>
        <td class="${cls(m.r1m)}">${pct(m.r1m)}</td><td class="${cls(m.r3m)}">${pct(m.r3m)}</td><td class="${cls(m.r12m)}">${pct(m.r12m)}</td>
        <td class="${cls(m.ytd)}">${pct(m.ytd)}</td><td class="${cls(m.vs_sma200)}">${pct(m.vs_sma200)}</td>
        <td class="${rsiCls}">${m.rsi14 ?? "—"}</td><td>${pct(m.dd52)}</td><td>${relp}</td>
        <td>${a.signals.length ? a.signals.length : ""}</td></tr>`;
    };
    $("#rankTable").innerHTML = `<thead><tr>${th}</tr></thead><tbody>${rows.map(td).join("")}</tbody>`;
    $("#rankTable").querySelectorAll("th").forEach((h) => h.addEventListener("click", () => {
      if (sortKey === h.dataset.k) sortDir = -sortDir; else { sortKey = h.dataset.k; sortDir = ["symbol", "name"].includes(sortKey) ? 1 : -1; }
      renderTable();
    }));
    $("#rankTable").querySelectorAll("tbody tr").forEach((tr) => tr.addEventListener("click", () => openDetail(tr.dataset.sym)));
  }

  // ---------- macro ----------
  function spark(values, w = 240, h = 36) {
    const v = (values || []).filter((x) => x != null);
    if (v.length < 2) return "";
    const lo = Math.min(...v), hi = Math.max(...v), rng = hi - lo || 1;
    const pts = v.map((y, i) => `${(i / (v.length - 1)) * w},${h - 3 - ((y - lo) / rng) * (h - 6)}`).join(" ");
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="${css("--s1")}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
  }
  function dbar(v) {
    const w = Math.abs(v) * 50;
    return `<div class="dbar"><i style="${v >= 0 ? `left:50%;width:${w}%;border-radius:0 4px 4px 0` : `left:${50 - w}%;width:${w}%;border-radius:4px 0 0 4px`};background:${divColor(v >= 0 ? 0.9 : -0.9)}"></i></div>`;
  }
  const STATE_LABEL = { positive: "Supportive", neutral: "Neutral", warning: "Caution", danger: "Danger", opportunity: "Opportunity" };
  function renderMacro() {
    $("#regimeHint").textContent = `Regime: ${DATA.regime.label} (${DATA.regime.score > 0 ? "+" : ""}${DATA.regime.score})`;
    $("#factors").innerHTML = Object.entries(DATA.macro_factors).map(([k, v]) =>
      `<div class="factor"><div class="fl"><span>${FACTOR_LABELS[k] || k}</span><span>${v > 0 ? "+" : ""}${v.toFixed(2)}</span></div>${dbar(v)}</div>`).join("");
    $("#gauges").innerHTML = DATA.gauges.map((g) => `
      <div class="gauge">
        <div class="gh"><span class="gn">${esc(g.name)}</span><span class="chip ${esc(g.state)}">${STATE_LABEL[g.state] || g.state}</span></div>
        <div><span class="gv">${g.unit === "$" ? "$" : ""}${num(g.value, Math.abs(g.value) >= 100 ? 0 : 2)}${g.unit && g.unit !== "$" ? `<span class="gm"> ${esc(g.unit)}</span>` : ""}</span>
          <span class="gm"> · ${g.chg3m != null ? `3m chg ${g.chg3m > 0 ? "+" : ""}${num(g.chg3m, 2)} · ` : ""}${g.pct10y != null ? `${Math.round(g.pct10y * 100)}th pct (10y)` : ""} · ${esc(g.date)}</span></div>
        ${spark(g.spark)}
        <div class="gr">${esc(g.read)}</div>
      </div>`).join("");
  }

  function renderLog() {
    const rows = (LOG || []).slice(0, 80);
    $("#log").innerHTML = rows.length ? rows.map((l) => `<div><span class="hint">${esc(l.date)}</span><span><span class="chip ${esc(l.severity)}">${SEV_LABEL[l.severity]}</span></span><span>${esc(l.title)}</span></div>`).join("")
      : `<div class="empty" style="display:block">No alert history yet. It builds up with each daily update.</div>`;
  }

  // ---------- line chart with crosshair ----------
  function lineChart(el, dates, series, fmt) {
    const W = el.clientWidth || 600, H = el.clientHeight || 240, P = { l: 48, r: 12, t: 8, b: 22 };
    const all = series.flatMap((s) => s.values.filter((v) => v != null));
    if (!all.length) { el.innerHTML = ""; return; }
    let lo = Math.min(...all), hi = Math.max(...all); const pad = (hi - lo) * 0.06 || 1; lo -= pad; hi += pad;
    const x = (i) => P.l + (i / (dates.length - 1)) * (W - P.l - P.r);
    const y = (v) => P.t + (1 - (v - lo) / (hi - lo)) * (H - P.t - P.b);
    const ticks = 4; let grid = "";
    for (let i = 0; i <= ticks; i++) {
      const v = lo + ((hi - lo) * i) / ticks;
      grid += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(v)}" y2="${y(v)}" stroke="${css("--grid")}" stroke-width="1"/>
        <text x="${P.l - 6}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="${css("--muted")}">${fmt(v)}</text>`;
    }
    const xt = [0, Math.floor(dates.length / 2), dates.length - 1].map((i) =>
      `<text x="${x(i)}" y="${H - 4}" text-anchor="${i === 0 ? "start" : i === dates.length - 1 ? "end" : "middle"}" font-size="11" fill="${css("--muted")}">${esc(dates[i])}</text>`).join("");
    const paths = series.map((s) => {
      let d = "", pen = false;
      s.values.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true; });
      return `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" ${s.dash ? `stroke-dasharray="${s.dash}"` : ""}/>`;
    }).join("");
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(series.map((s) => s.name).join(", "))} chart">${grid}${xt}${paths}
      <line class="xh" y1="${P.t}" y2="${H - P.b}" stroke="${css("--muted")}" stroke-width="1" visibility="hidden"/>
      ${series.map((s, k) => `<circle class="dot${k}" r="4" fill="${s.color}" stroke="${css("--surface")}" stroke-width="2" visibility="hidden"/>`).join("")}
      <rect x="${P.l}" y="0" width="${W - P.l - P.r}" height="${H}" fill="transparent"/></svg>`;
    const svg = el.querySelector("svg"), xh = svg.querySelector(".xh");
    svg.addEventListener("mousemove", (e) => {
      const r = svg.getBoundingClientRect(); const px = ((e.clientX - r.left) / r.width) * W;
      const i = Math.max(0, Math.min(dates.length - 1, Math.round(((px - P.l) / (W - P.l - P.r)) * (dates.length - 1))));
      xh.setAttribute("x1", x(i)); xh.setAttribute("x2", x(i)); xh.setAttribute("visibility", "visible");
      series.forEach((s, k) => { const c = svg.querySelector(`.dot${k}`); const v = s.values[i]; if (v == null) { c.setAttribute("visibility", "hidden"); return; } c.setAttribute("cx", x(i)); c.setAttribute("cy", y(v)); c.setAttribute("visibility", "visible"); });
      showTip(`<b>${esc(dates[i])}</b>${series.map((s) => `<div class="row"><i class="sw" style="background:${s.color}"></i>${esc(s.name)}: ${s.values[i] == null ? "—" : fmt(s.values[i])}</div>`).join("")}`, e.clientX, e.clientY);
    });
    svg.addEventListener("mouseleave", () => { xh.setAttribute("visibility", "hidden"); svg.querySelectorAll("circle").forEach((c) => c.setAttribute("visibility", "hidden")); hideTip(); });
  }

  // ---------- detail drawer ----------
  function openDetail(sym) {
    const a = bySym[sym]; if (!a) return;
    const m = a.metrics;
    history.replaceState(null, "", `#${encodeURIComponent(sym)}`);
    const hist = HISTORY.filter((h) => h.scores && h.scores[sym] != null);
    const metric = (k, v) => `<div><span>${k}</span><span>${v}</span></div>`;
    const comps = COMP.map(([k, label, w]) => { const v = a.components[k]; return `<div class="comp"><span>${label} <span class="w">${w}%</span></span>${dbar(v)}<span style="text-align:right">${v > 0 ? "+" : ""}${v.toFixed(2)}</span></div>`; }).join("");
    const drivers = (a.macro_drivers || []).map((d) => `<div class="comp"><span style="font-size:12px">${esc(factorName(d.factor))}</span>${dbar(d.impact * 2)}<span style="text-align:right">${d.impact > 0 ? "+" : ""}${d.impact.toFixed(2)}</span></div>`).join("");
    const sigs = a.signals.length ? a.signals.map((s) => alertHtml({ ...s, symbol: null, first_seen: (DATA.alerts.find((x) => x.id === s.id) || {}).first_seen || "today" })).join("") : `<div class="empty">No timing signals active.</div>`;
    $("#drawerBody").innerHTML = `
      <div class="dh"><h2 id="dTitle">${esc(a.symbol)}</h2><span class="hint">${esc(a.name)}</span></div>
      <div class="dh" style="margin-top:6px"><span class="price">$${num(m.price)}</span><span class="${cls(m.chg1d)}">${pct(m.chg1d, 2)} today</span>
        <span class="chip ${a.score >= 60 ? "positive" : a.score < 45 ? "warning" : "neutral"}">${esc(a.rating)} · ${a.score}/100</span><span class="hint">as of ${esc(m.date)}</span></div>
      <div class="legend"><span><i style="background:${css("--s1")}"></i>Price</span><span><i style="background:${css("--s2")}"></i>50-day avg</span><span><i style="background:${css("--s3")}"></i>200-day avg</span></div>
      <div class="chart" id="pChart"></div>
      ${a.chart.rel ? `<h3>Relative to S&amp;P 500 (rising = outperforming), ~5 years, indexed to 100</h3><div class="chart" id="rChart" style="height:160px"></div>` : ""}
      <h3>Score breakdown</h3>${comps}
      <h3>Macro drivers for this asset</h3>${drivers || '<div class="empty">None</div>'}
      <h3>Timing signals</h3><div class="alerts" style="margin-top:0">${sigs}</div>
      <h3>All metrics</h3>
      <div class="metrics">
        ${metric("1 week", pct(m.r1w))}${metric("1 month", pct(m.r1m))}${metric("3 months", pct(m.r3m))}${metric("6 months", pct(m.r6m))}
        ${metric("12 months", pct(m.r12m))}${metric("3 years", pct(m.r3y))}${metric("YTD", pct(m.ytd))}${metric("Momentum 12-1", pct(m.mom12_1))}
        ${metric("50-day avg", num(m.sma50))}${metric("200-day avg", num(m.sma200))}${metric("vs 50-day", pct(m.vs_sma50))}${metric("vs 200-day", pct(m.vs_sma200))}
        ${metric("200-day slope (1m)", pct(m.sma200_slope, 2))}${metric("Stretch vs history", m.stretch_pct == null ? "—" : `${Math.round(m.stretch_pct * 100)}th pct`)}
        ${metric("RSI (14)", m.rsi14 ?? "—")}${metric("From 52w high", pct(m.dd52))}${metric("From 10y high", pct(m.dd_max))}
        ${metric("52w range position", m.range52 == null ? "—" : `${Math.round(m.range52 * 100)}%`)}${metric("52w high / low", `${num(m.hi52)} / ${num(m.lo52)}`)}
        ${metric("Volatility (1m, ann.)", pct(m.vol21, 1, false))}${metric("Vol. percentile (5y)", m.vol_pct == null ? "—" : `${Math.round(m.vol_pct * 100)}th`)}
        ${metric("Last MA cross", m.cross ? `${m.cross} (${m.cross_ago}d ago)` : "none in 1y")}
        ${m.rel ? metric("Rel. vs SPY 3m", pct(m.rel.r3m)) + metric("Rel. vs SPY 12m", pct(m.rel.r12m)) + metric("Rel. vs SPY 10y pct", `${Math.round(m.rel.pct10y * 100)}th`) : ""}
        ${metric("History used", `${m.history_years} yrs`)}
      </div>
      ${hist.length > 1 ? `<h3>Score history</h3><div class="chart" id="hChart" style="height:140px"></div>` : ""}`;
    $("#drawer").hidden = false;
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => {
      lineChart($("#pChart"), a.chart.d, [
        { name: "Price", values: a.chart.c, color: css("--s1") },
        { name: "50-day", values: a.chart.s50, color: css("--s2") },
        { name: "200-day", values: a.chart.s200, color: css("--s3") },
      ], (v) => num(v, v >= 100 ? 0 : 2));
      if (a.chart.rel) lineChart($("#rChart"), a.chart.rel.d, [{ name: `${a.symbol} / SPY`, values: a.chart.rel.v, color: css("--s1") }], (v) => num(v, 1));
      if (hist.length > 1) lineChart($("#hChart"), hist.map((h) => h.date), [{ name: "Score", values: hist.map((h) => h.scores[sym]), color: css("--s1") }], (v) => num(v, 0));
    });
    $(".drawer-panel .close").focus();
  }
  function closeDetail() { $("#drawer").hidden = true; document.body.style.overflow = ""; hideTip(); history.replaceState(null, "", location.pathname + location.search); }
  $("#drawer").addEventListener("click", (e) => { if (e.target.closest("[data-close]")) closeDetail(); });
  addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#drawer").hidden) closeDetail(); });

  // ---------- browser notifications (while the page is opened) ----------
  const notifyBtn = $("#notifyBtn");
  function updateNotifyBtn() {
    if (!("Notification" in window)) { notifyBtn.hidden = true; return; }
    notifyBtn.textContent = Notification.permission === "granted" ? "Browser alerts on" : "Enable browser alerts";
    notifyBtn.disabled = Notification.permission === "granted";
  }
  notifyBtn.addEventListener("click", async () => {
    if (!("Notification" in window)) return;
    await Notification.requestPermission(); updateNotifyBtn(); browserNotify();
  });
  function browserNotify() {
    if (!DATA || DATA.demo) return;
    const seen = new Set(store.get("mts.seen", []));
    const fresh = DATA.alerts.filter((a) => a.severity !== "info" && !seen.has(a.id));
    store.set("mts.seen", DATA.alerts.map((a) => a.id));
    if (!fresh.length || !("Notification" in window) || Notification.permission !== "granted" || !seen.size) return;
    try {
      new Notification(`${fresh.length} new market signal${fresh.length > 1 ? "s" : ""}`, { body: fresh.slice(0, 4).map((a) => a.title).join("\n") });
    } catch { /* some mobile browsers only allow notifications from a service worker */ }
  }
  updateNotifyBtn();
  load();
})();
