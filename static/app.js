"use strict";

/* Atlas Server: miljöer, import av filer från insamlaren, servrar och export. */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const store = {
  get(k, d) {
    try { const v = localStorage.getItem("atlas-server:" + k); return v === null ? d : JSON.parse(v); }
    catch (e) { return d; }
  },
  set(k, v) { try { localStorage.setItem("atlas-server:" + k, JSON.stringify(v)); } catch (e) { /* privat läge */ } },
};

let LANG = store.get("lang", null) === "en" ? "en" : "sv";
const L = (sv, en) => (LANG === "en" ? en : sv);
let CLASSIFICATIONS = [];

// ---------------------------------------------------------------------------
// Hjälp
// ---------------------------------------------------------------------------

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) {
    if (k === null || k === undefined || k === false) continue;
    e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
  return e;
}

async function api(path, opts = {}) {
  const headers = Object.assign({ "X-Lang": LANG }, opts.headers || {});
  if (opts.method && opts.method !== "GET") headers["X-Atlas-Server"] = "1";
  let bodyData = opts.body;
  if (bodyData && !(bodyData instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    bodyData = JSON.stringify(bodyData);
  }
  let res;
  try {
    res = await fetch(path, { method: opts.method || "GET", headers, body: bodyData, credentials: "same-origin" });
  } catch (e) {
    throw new Error(L("Servern svarar inte. Kontrollera att Atlas Server körs.", "The server does not respond. Check that Atlas Server is running."));
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* inte JSON */ }
  if (res.status === 401 || (data && data.must_change)) { location.replace("login"); throw new Error(""); }
  if (!res.ok) throw new Error((data && data.error) || L(`Servern svarade med fel ${res.status}.`, `The server responded with error ${res.status}.`));
  return data;
}

function setStatus(node, text, kind) { if (node) { node.textContent = text || ""; node.className = `status ${kind || ""}`.trim(); } }

function fnum(v, dec = 1) {
  if (v === null || v === undefined || v === "") return "";
  return Number(v).toLocaleString(LANG === "en" ? "en-GB" : "sv-SE", { minimumFractionDigits: 0, maximumFractionDigits: dec });
}

function localize(root = document) {
  document.documentElement.lang = LANG;
  try { document.cookie = `as_lang=${LANG}; max-age=31536000; SameSite=Strict`; } catch (e) { /* utan kakor */ }
  for (const n of $$("[data-en]", root)) {
    if (n.dataset.sv === undefined) n.dataset.sv = n.textContent;
    n.textContent = LANG === "en" ? n.dataset.en : n.dataset.sv;
  }
  for (const attr of ["placeholder", "title", "aria-label"]) {
    for (const n of $$(`[data-en-${attr}]`, root)) {
      if (!n.hasAttribute(`data-sv-${attr}`)) n.setAttribute(`data-sv-${attr}`, n.getAttribute(attr) || "");
      n.setAttribute(attr, n.getAttribute(LANG === "en" ? `data-en-${attr}` : `data-sv-${attr}`));
    }
  }
  for (const b of $$("#lang-switch button")) b.setAttribute("aria-pressed", String(b.dataset.lang === LANG));
}

function themeMode() { return store.get("theme", "dark"); }
function applyTheme(mode) {
  if (mode === "light" || mode === "dark") document.documentElement.setAttribute("data-theme", mode);
  else document.documentElement.removeAttribute("data-theme");
  store.set("theme", mode === "system" ? "" : mode);
  $("#theme-btn").dataset.mode = mode || "system";
}

function mount(tpl) {
  const view = $("#view");
  view.replaceChildren($(`#tpl-${tpl}`).content.cloneNode(true));
  localize(view);
  return view;
}

function table(node, cols, rows, onClick) {
  const thead = el("thead", {}, el("tr", {}, cols.map((c) => el("th", { class: c.num ? "num" : null }, el("span", { class: "th", text: c.label })))));
  const tbody = el("tbody");
  for (const r of rows) {
    const tr = el("tr", { class: onClick ? "clickable" : null });
    cols.forEach((c, i) => {
      const v = r[i];
      tr.append(el("td", { class: [c.num ? "num" : "", c.mono ? "mono" : ""].join(" ").trim() || null }, v instanceof Node ? v : (v ?? "")));
    });
    if (onClick) {
      tr.tabIndex = 0;
      tr.addEventListener("click", () => onClick(r));
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter") onClick(r); });
    }
    tbody.append(tr);
  }
  node.replaceChildren(thead, tbody);
}

function levelLabel(l) { return { crit: L("Hög", "High"), warn: L("Medel", "Medium"), info: "Info" }[l] || l; }

// ---------------------------------------------------------------------------
// Miljöer
// ---------------------------------------------------------------------------

async function showEnvs() {
  const view = mount("envs");
  const data = await api("api/envs");
  CLASSIFICATIONS = data.classifications || [];
  const list = $("#env-list", view);
  $("#env-empty", view).hidden = data.envs.length > 0;
  for (const e of data.envs) {
    list.append(el("a", { class: "card env-card", href: `#/env/${e.id}` },
      el("span", { class: "env-cust", text: e.customer || "" }),
      el("b", { text: e.name }),
      el("small", { text: L(`${e.count} servrar`, `${e.count} servers`) + (e.updated ? L(`, senast insamlat ${e.updated}`, `, last collected ${e.updated}`) : "") })));
  }
  $("#env-new", view).addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    try {
      const r = await api("api/envs", { method: "POST", body: { name: f.name.value, customer: f.customer.value } });
      location.hash = `#/env/${r.id}`;
    } catch (e) { setStatus($("#env-new-status"), e.message, "error"); }
  });
}

// ---------------------------------------------------------------------------
// En miljö
// ---------------------------------------------------------------------------

async function showEnv(id) {
  const view = mount("env");
  let env = await api(`api/envs/${encodeURIComponent(id)}`);
  if (!CLASSIFICATIONS.length) CLASSIFICATIONS = (await api("api/envs")).classifications || [];
  $("#doc-lang", view).value = store.get("docLang", LANG);
  $("#doc-lang", view).addEventListener("change", (e) => store.set("docLang", e.target.value));

  function render() {
    $("#env-eyebrow", view).textContent = `${env.customer || "Atlas Server"} · ${L("Miljö", "Environment")}`;
    $("#env-title", view).textContent = env.name;
    document.title = `${env.name}, Atlas Server`;
    const s = env.servers;
    const kpi = (label, value, small) => el("div", {}, el("dt", { text: label }), el("dd", {}, String(value), small ? el("small", { text: small }) : null));
    const versions = [...new Set(s.map((x) => x.windows).filter(Boolean))];
    $("#env-kpis", view).replaceChildren(
      kpi(L("Servrar", "Servers"), s.length),
      kpi(L("Domänkontrollanter", "Domain controllers"), s.filter((x) => x.is_dc).length),
      kpi(L("Windows-versioner", "Windows versions"), versions.length, versions.join(", ")),
      kpi(L("Iakttagelser", "Observations"), env.observations.filter((o) => o.level !== "info").length));
    renderServers();
    const obs = env.observations;
    $("#obs-block", view).hidden = !obs.length;
    $("#obs-list", view).replaceChildren(...obs.map((o) => el("li", {}, el("span", { class: `dot dot-${o.level}` }),
      el("b", { text: o.server }), el("span", { class: "obs-lvl", text: levelLabel(o.level) }), el("span", { text: o.text }))));
  }

  function renderServers() {
    const q = ($("#srv-filter", view).value || "").toLowerCase();
    const rows = env.servers.filter((x) => !q || JSON.stringify(x).toLowerCase().includes(q));
    $("#srv-empty", view).hidden = env.servers.length > 0;
    $("#srv-table", view).parentElement.hidden = env.servers.length === 0;
    table($("#srv-table", view), [
      { label: L("Server", "Server") }, { label: L("IP-adress", "IP address"), mono: true }, { label: "Windows" },
      { label: "Build" }, { label: L("Roller", "Roles") }, { label: L("Extra tjänster", "Extra services"), num: true },
      { label: L("Beskrivning", "Description") }, { label: L("Insamlat", "Collected") },
    ], rows.map((x) => {
      const r = [x.name, x.ip, x.windows, x.build, x.roles.join(", "), x.extra_services, x.description,
        el("span", {}, x.collected, x.elevated === false ? el("span", { class: "tag warn", title: L("Insamlat utan administratörsrätt", "Collected without administrator rights"), text: "!" }) : null)];
      r.name = x.name;
      return r;
    }), (r) => { location.hash = `#/env/${id}/server/${encodeURIComponent(r.name)}`; });
  }

  $("#srv-filter", view).addEventListener("input", renderServers);

  // Import
  const drop = $("#drop", view);
  const input = $("#file-input", view);
  async function upload(files) {
    if (!files || !files.length) return;
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);
    drop.classList.add("busy");
    const out = $("#import-result", view);
    try {
      const r = await api(`api/envs/${id}/import`, { method: "POST", body: fd });
      out.replaceChildren(...r.results.map((x) => el("li", { class: x.ok ? "ok" : "fail" },
        el("span", { class: `dot ${x.ok ? "dot-ok" : "dot-crit"}` }), el("b", { text: x.server || x.file }), el("span", { text: x.message }))));
      out.hidden = false;
      env = await api(`api/envs/${id}`);
      render();
    } catch (e) {
      out.replaceChildren(el("li", { class: "fail" }, el("span", { class: "dot dot-crit" }), el("span", { text: e.message })));
      out.hidden = false;
    } finally {
      drop.classList.remove("busy");
      input.value = "";
    }
  }
  drop.addEventListener("click", () => input.click());
  drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  input.addEventListener("change", () => upload(input.files));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); upload(e.dataTransfer.files); });

  // Export
  for (const b of $$("[data-export]", view)) {
    b.addEventListener("click", async () => {
      const kind = b.dataset.export;
      const lang = $("#doc-lang", view).value;
      b.disabled = true;
      try {
        const res = await fetch(`api/envs/${id}/export/${kind}?lang=${lang}`, { credentials: "same-origin", headers: { "X-Lang": LANG } });
        if (!res.ok) {
          let msg = `HTTP ${res.status}`;
          try { msg = (await res.json()).error || msg; } catch (e) { /* inte JSON */ }
          throw new Error(msg);
        }
        const cd = res.headers.get("Content-Disposition") || "";
        const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
        const name = m ? decodeURIComponent(m[1]) : `atlas-server.${kind}`;
        const url = URL.createObjectURL(await res.blob());
        const a = el("a", { href: url, download: name });
        document.body.append(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
      } catch (e) {
        alertBox(e.message);
      } finally { b.disabled = false; }
    });
  }

  // Inställningar för miljön
  const form = $("#env-form", view);
  const sel = $("#cls-select", view);
  sel.replaceChildren(...CLASSIFICATIONS.map((c) => el("option", { value: c.value, text: c.label })));
  function fill() {
    for (const k of ["customer", "name", "version", "owner", "approver"]) form[k].value = env[k] || "";
    sel.value = env.classification || "internal";
    form.show_software.checked = env.show_software !== false;
    form.show_all_features.checked = env.show_all_features !== false;
    form.hide_services.value = (env.hide_services || []).join("\n");
  }
  fill();
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      await api(`api/envs/${id}`, { method: "PUT", body: {
        customer: form.customer.value, name: form.name.value, version: form.version.value, owner: form.owner.value,
        approver: form.approver.value, classification: sel.value, show_software: form.show_software.checked,
        show_all_features: form.show_all_features.checked, hide_services: form.hide_services.value } });
      env = await api(`api/envs/${id}`);
      render();
      setStatus($("#env-status", view), L("Sparat.", "Saved."), "ok");
    } catch (e) { setStatus($("#env-status", view), e.message, "error"); }
  });
  $("#env-delete", view).addEventListener("click", async () => {
    if (!confirm(L(`Ta bort miljön ${env.name} med alla ${env.servers.length} servrar? Det går inte att ångra.`,
      `Delete the environment ${env.name} with all ${env.servers.length} servers? This cannot be undone.`))) return;
    try { await api(`api/envs/${id}`, { method: "DELETE" }); location.hash = "#/"; }
    catch (e) { setStatus($("#env-status", view), e.message, "error"); }
  });
  logoControl(`api/envs/${id}/logo`, $("#env-logo", view), $("#env-logo-input", view), $("#env-logo-del", view), env.logo, $("#env-status", view));

  render();
}

function alertBox(msg) { window.alert(msg); }

function logoControl(url, img, input, del, exists, status) {
  function show(has) {
    img.hidden = !has;
    del.hidden = !has;
    if (has) img.src = `${url}?t=${Date.now()}`;
  }
  show(exists);
  input.addEventListener("change", async () => {
    const f = input.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f, f.name);
    try { await api(url, { method: "PUT", body: fd }); show(true); setStatus(status, L("Logotypen är sparad.", "The logo is saved."), "ok"); }
    catch (e) { setStatus(status, e.message, "error"); }
    input.value = "";
  });
  del.addEventListener("click", async () => {
    try { await api(url, { method: "DELETE" }); show(false); } catch (e) { setStatus(status, e.message, "error"); }
  });
}

// ---------------------------------------------------------------------------
// En server
// ---------------------------------------------------------------------------

async function showServer(id, name) {
  const view = mount("server");
  const s = await api(`api/envs/${encodeURIComponent(id)}/servers/${encodeURIComponent(name)}`);
  document.title = `${s.name}, Atlas Server`;
  $("#back-link", view).href = `#/env/${id}`;
  $("#srv-eyebrow", view).textContent = [s.fqdn, s.domain_role].filter(Boolean).join(" · ");
  $("#srv-title", view).textContent = s.name;
  const nf = $("#note-form", view);
  nf.description.value = s.description;
  nf.owner.value = s.owner;
  nf.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      await api(`api/envs/${id}/servers/${encodeURIComponent(s.name)}/note`, { method: "PUT", body: { description: nf.description.value, owner: nf.owner.value } });
      setStatus($("#note-status", view), L("Sparat.", "Saved."), "ok");
    } catch (e) { setStatus($("#note-status", view), e.message, "error"); }
  });
  $("#srv-delete", view).addEventListener("click", async () => {
    if (!confirm(L(`Ta bort ${s.name} ur miljön?`, `Remove ${s.name} from the environment?`))) return;
    await api(`api/envs/${id}/servers/${encodeURIComponent(s.name)}`, { method: "DELETE" });
    location.hash = `#/env/${id}`;
  });

  const body = $("#srv-body", view);
  const section = (title, ...content) => el("div", { class: "table-block" }, el("h2", { text: title }), ...content);
  const kv = (pairs) => el("dl", { class: "kv" }, pairs.filter(([, v]) => v !== "" && v !== null && v !== undefined)
    .map(([k, v]) => [el("dt", { text: k }), el("dd", { text: String(v) })]).flat());
  const tbl = (cols, rows, empty) => {
    if (!rows.length) return el("p", { class: "empty", text: empty || L("Inget att redovisa.", "Nothing to report.") });
    const t = el("table", { class: "data" });
    table(t, cols, rows);
    return el("div", { class: "table-scroll" }, t);
  };
  const yn = (v) => (v ? L("Ja", "Yes") : L("Nej", "No"));

  if (s.observations.length) {
    body.append(section(L("Iakttagelser", "Observations"), el("ul", { class: "obs" }, s.observations.map((o) =>
      el("li", {}, el("span", { class: `dot dot-${o.level}` }), el("span", { class: "obs-lvl", text: levelLabel(o.level) }), el("span", { text: o.text }))))));
  }
  body.append(section(L("Grunduppgifter", "General"), kv([
    ["FQDN", s.fqdn], [L("Domän", "Domain"), s.domain], [L("Domänroll", "Domain role"), s.domain_role],
    ["Windows", s.windows], [L("Version och build", "Version and build"), [s.display_version, s.build].filter(Boolean).join(", build ")],
    [L("Installationstyp", "Installation type"), s.install_type], [L("Installerad", "Installed"), s.install_date],
    [L("Senaste omstart", "Last boot"), s.last_boot], [L("Senaste uppdatering", "Latest update"), [s.last_update, s.last_update_id].filter(Boolean).join(", ")],
    [L("Plattform", "Platform"), s.platform], [L("Tillverkare och modell", "Manufacturer and model"), [s.manufacturer, s.model].filter(Boolean).join(", ")],
    [L("Serienummer", "Serial number"), s.serial], ["CPU", [s.cpu, s.cpu_short].filter(Boolean).join(", ")],
    [L("Minne", "Memory"), s.memory_gib ? `${fnum(s.memory_gib)} GiB` : ""], [L("Tidszon", "Time zone"), s.time_zone],
    [L("Fjärrskrivbord", "Remote Desktop"), s.rdp], [L("Windows-brandväggen", "Windows Firewall"), s.firewall],
    [L("Datorbeskrivning i Windows", "Computer description in Windows"), s.os_description],
  ])));
  body.append(section(L("Nätverk och DNS", "Network and DNS"),
    tbl([{ label: L("Nätverkskort", "Adapter") }, { label: L("IP-adress", "IP address"), mono: true }, { label: "Gateway", mono: true },
      { label: L("DNS-servrar", "DNS servers"), mono: true }, { label: L("DNS-suffix", "DNS suffix") }, { label: "DHCP" }, { label: "MAC", mono: true }],
    s.network.map((n) => [n.name, [...n.ipv4, ...n.ipv6].join(", "), n.gateways.join(", "), n.dns_servers.join(", "), n.dns_suffix, yn(n.dhcp), n.mac])),
    kv([[L("Primärt DNS-suffix", "Primary DNS suffix"), s.dns_primary_suffix], [L("Sökordning för DNS-suffix", "DNS suffix search list"), s.dns_search_list.join(", ")]])));
  body.append(section(L("Diskar", "Disks"), tbl([{ label: L("Volym", "Volume") }, { label: L("Etikett", "Label") }, { label: L("Filsystem", "File system") },
    { label: L("Storlek (GiB)", "Size (GiB)"), num: true }, { label: L("Ledigt (GiB)", "Free (GiB)"), num: true }, { label: L("Ledigt", "Free"), num: true }],
  s.disks.map((d) => [d.drive, d.label, d.fs, fnum(d.size_gib), fnum(d.free_gib), d.free_pct === null ? "" : `${fnum(d.free_pct, 0)} %`]))));
  body.append(section(L("Windows-roller och funktioner", "Windows roles and features"), tbl([{ label: L("Namn", "Name") }, { label: L("Typ", "Type") },
    { label: L("Tekniskt namn", "Technical name"), mono: true }, { label: L("Tillagd", "Added") }],
  s.features.map((f) => ["   ".repeat(Math.max(0, f.depth - 1)) + f.display_name, f.type_label, f.name, f.default ? L("Standard", "Default") : L("Ja", "Yes")]),
  L("Roller och funktioner kunde inte läsas.", "Roles and features could not be read."))));
  const svcCols = [{ label: L("Tjänst", "Service") }, { label: L("Namn", "Name"), mono: true }, { label: L("Klass", "Class") }, { label: L("Start", "Startup") },
    { label: L("Status", "Status") }, { label: L("Konto", "Account") }, { label: L("Tillverkare", "Manufacturer") }, { label: L("Sökväg", "Path"), mono: true }];
  const svcRow = (x) => [x.display_name, x.name, x.class_label, x.start, x.state, x.account, x.company, x.path];
  body.append(section(L("Tjänster utöver Windows standard", "Services beyond the Windows defaults"),
    tbl(svcCols, s.services_extra.map(svcRow), L("Inga tjänster utöver Windows standard.", "No services beyond the Windows defaults.")),
    el("details", { class: "disclose" }, el("summary", { text: L(`Visa alla ${s.services.length} tjänster`, `Show all ${s.services.length} services`) }),
      tbl(svcCols, s.services.map(svcRow)))));
  if (s.shares.length) {
    body.append(section(L("Utdelningar", "Shares"), tbl([{ label: L("Namn", "Name") }, { label: L("Sökväg", "Path"), mono: true }, { label: L("Beskrivning", "Description") }],
      s.shares.map((x) => [x.name, x.path, x.description]))));
  }
  body.append(section(L("Installerade program", "Installed software"), tbl([{ label: L("Program", "Software") }, { label: "Version" },
    { label: L("Utgivare", "Publisher") }, { label: L("Installerat", "Installed") }], s.software.map((x) => [x.name, x.version, x.publisher, x.install_date]))));
  const m = s.meta;
  body.append(section(L("Insamling", "Collection"), kv([
    [L("Insamlat", "Collected"), m.collected], [L("Metod", "Method"), m.method === "remote" ? `WinRM ${L("från", "from")} ${m.collected_from}` : L("Lokalt", "Local")],
    [L("Konto", "Account"), m.collected_by], [L("Administratörsrätt", "Administrator rights"), m.elevated === null ? "" : yn(m.elevated)],
    [L("Insamlarens version", "Collector version"), m.collector_version], ["PowerShell", m.ps_version],
  ]), s.errors.length ? tbl([{ label: L("Avsnitt", "Section") }, { label: L("Fel", "Error") }], s.errors.map((e) => [e.section, e.message])) : null));
}

// ---------------------------------------------------------------------------
// Insamlare och inställningar
// ---------------------------------------------------------------------------

function showCollector() { mount("collector"); }

async function showSettings() {
  const view = mount("settings");
  const s = await api("api/settings");
  const f = $("#partner-form", view);
  for (const k of ["company", "consultant", "email", "phone"]) f[k].value = s.partner[k] || "";
  f.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      await api("api/settings", { method: "PUT", body: { partner: { company: f.company.value, consultant: f.consultant.value, email: f.email.value, phone: f.phone.value } } });
      setStatus($("#partner-status", view), L("Sparat.", "Saved."), "ok");
    } catch (e) { setStatus($("#partner-status", view), e.message, "error"); }
  });
  logoControl("api/logo/partner", $("#partner-logo", view), $("#partner-logo-input", view), $("#partner-logo-del", view), s.partner_logo, $("#partner-status", view));
  const pw = $("#pw-form", view);
  pw.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      await api("api/password", { method: "POST", body: { current: pw.current.value, new: pw.new.value, confirm: pw.confirm.value } });
      pw.reset();
      setStatus($("#pw-status", view), L("Lösenordet är bytt.", "The password is changed."), "ok");
    } catch (e) { setStatus($("#pw-status", view), e.message, "error"); }
  });
}

// ---------------------------------------------------------------------------
// Start och navigering
// ---------------------------------------------------------------------------

async function route() {
  const parts = (location.hash.replace(/^#\/?/, "") || "").split("/").map(decodeURIComponent);
  let nav = "envs";
  try {
    if (parts[0] === "env" && parts[1] && parts[2] === "server" && parts[3]) await showServer(parts[1], parts[3]);
    else if (parts[0] === "env" && parts[1]) await showEnv(parts[1]);
    else if (parts[0] === "insamlare") { nav = "collector"; showCollector(); }
    else if (parts[0] === "installningar") { nav = "settings"; await showSettings(); }
    else { document.title = "Atlas Server"; await showEnvs(); }
  } catch (e) {
    if (e.message) $("#view").replaceChildren(el("section", { class: "page" }, el("p", { class: "status error", text: e.message }), el("p", {}, el("a", { href: "#/", text: L("Till miljöerna", "To the environments") }))));
  }
  for (const a of $$(".nav a")) a.setAttribute("aria-current", a.dataset.nav === nav ? "page" : "false");
  $("#view").focus({ preventScroll: true });
}

async function init() {
  localize();
  applyTheme(themeMode() || "system");
  $("#theme-btn").addEventListener("click", () => {
    const order = ["system", "light", "dark"];
    const cur = themeMode() || "system";
    applyTheme(order[(order.indexOf(cur) + 1) % order.length]);
  });
  for (const b of $$("#lang-switch button")) b.addEventListener("click", () => {
    LANG = b.dataset.lang === "en" ? "en" : "sv";
    store.set("lang", LANG);
    localize();
    route();
  });
  $("#logout-btn").addEventListener("click", async () => {
    try { await api("api/logout", { method: "POST" }); } catch (e) { /* ändå ut */ }
    location.replace("login");
  });
  try {
    const me = await api("api/me");
    if (!me.authenticated) { location.replace("login"); return; }
    $("#user-name").textContent = me.user;
    $("#user-avatar").textContent = (me.user || "A").slice(0, 1).toUpperCase();
    const info = await api("api/info");
    const v = $("#brand-version");
    v.textContent = info.version;
    v.hidden = false;
  } catch (e) { /* visas i vyn */ }
  window.addEventListener("hashchange", route);
  route();
}

document.addEventListener("DOMContentLoaded", init);
