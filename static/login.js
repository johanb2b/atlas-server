"use strict";

/* Inloggningssidan: logga in, och byt standardlösenordet innan något annat går att använda. */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const store = {
  get(k, d) {
    try { const v = localStorage.getItem("atlas-server:" + k); return v === null ? d : JSON.parse(v); }
    catch (e) { return d; }
  },
  set(k, v) { try { localStorage.setItem("atlas-server:" + k, JSON.stringify(v)); } catch (e) { /* privat läge */ } },
};

let LANG = store.get("lang", null) === "sv" ? "sv" : "en";  // engelska som standard
const L = (sv, en) => (LANG === "en" ? en : sv);
let me = { min_length: 8 };
let current = "";  // lösenordet som användaren just loggade in med, behövs för bytet

function localize() {
  document.documentElement.lang = LANG;
  document.title = L("Logga in, Atlas Server", "Log in, Atlas Server");
  try { document.cookie = `as_lang=${LANG}; max-age=31536000; SameSite=Strict`; } catch (e) { /* utan kakor */ }
  for (const el of $$("[data-en]")) {
    if (el.dataset.sv === undefined) el.dataset.sv = el.textContent;
    el.textContent = LANG === "en" ? el.dataset.en : el.dataset.sv;
  }
  for (const el of $$("[data-en-aria-label]")) {
    if (!el.hasAttribute("data-sv-aria-label")) el.setAttribute("data-sv-aria-label", el.getAttribute("aria-label") || "");
    el.setAttribute("aria-label", el.getAttribute(LANG === "en" ? "data-en-aria-label" : "data-sv-aria-label"));
  }
  for (const b of $$("#lang-switch button")) b.setAttribute("aria-pressed", String(b.dataset.lang === LANG));
  $("#pw-rule").textContent = L(
    `Minst ${me.min_length} tecken, och inte admin eller användarnamnet.`,
    `At least ${me.min_length} characters, and not admin or the user name.`);
}

function themeMode() { return store.get("theme", "dark"); }  // mörkt som standard
function applyTheme(mode) {
  if (mode === "light" || mode === "dark") document.documentElement.setAttribute("data-theme", mode);
  else document.documentElement.removeAttribute("data-theme");
  try { localStorage.setItem("atlas-server:theme", mode === "system" ? "" : mode); } catch (e) { /* privat läge */ }
  store.set("theme", mode);
  $("#theme-btn").dataset.mode = mode;
}

async function post(path, body) {
  let res;
  try {
    res = await fetch(path, { method: "POST", headers: { "X-Atlas-Server": "1", "X-Lang": LANG, "Content-Type": "application/json" },
      body: JSON.stringify(body), credentials: "same-origin" });
  } catch (e) {
    throw new Error(L("Servern svarar inte. Kontrollera att Atlas Server körs.", "The server does not respond. Check that Atlas Server is running."));
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* inte JSON */ }
  if (!res.ok) throw new Error((data && data.error) || L(`Servern svarade med fel ${res.status}.`, `The server responded with error ${res.status}.`));
  return data;
}

function setStatus(el, text, kind) { el.textContent = text || ""; el.className = `status ${kind || ""}`.trim(); }

function show(which) {
  $("#login-form").hidden = which !== "login";
  $("#change-form").hidden = which !== "change";
  const first = which === "login" ? $("#login-form").elements.user : $("#change-form").elements.new;
  if (which === "login" && first.value) $("#login-form").elements.password.focus();
  else first.focus();
}

function enter() { location.replace("./"); }

async function init() {
  localize();
  applyTheme(themeMode());
  $("#theme-btn").addEventListener("click", () => {
    const order = ["system", "light", "dark"];
    applyTheme(order[(order.indexOf(themeMode()) + 1) % order.length]);
  });
  for (const b of $$("#lang-switch button")) b.addEventListener("click", () => {
    LANG = b.dataset.lang === "en" ? "en" : "sv";
    store.set("lang", LANG);
    localize();
  });

  const lf = $("#login-form");
  lf.addEventListener("submit", async (e) => {
    e.preventDefault();
    const st = $("#login-status");
    const btn = $("button[type=submit]", lf);
    if (!lf.elements.user.value.trim() || !lf.elements.password.value) {
      setStatus(st, L("Ange användarnamn och lösenord.", "Enter the user name and password."), "error");
      return;
    }
    btn.disabled = true;
    setStatus(st, L("Loggar in...", "Logging in..."));
    try {
      me = await post("api/login", { user: lf.elements.user.value.trim(), password: lf.elements.password.value });
      current = lf.elements.password.value;
      lf.elements.password.value = "";
      setStatus(st, "");
      if (me.must_change) {
        $("#change-form").elements.user.value = me.user;
        localize();
        show("change");
      } else enter();
    } catch (err) {
      setStatus(st, err.message, "error");
      lf.elements.password.select();
    } finally { btn.disabled = false; }
  });

  const cf = $("#change-form");
  $("#show-pw").addEventListener("change", (e) => {
    for (const n of ["new", "confirm"]) cf.elements[n].type = e.target.checked ? "text" : "password";
  });
  cf.addEventListener("submit", async (e) => {
    e.preventDefault();
    const st = $("#change-status");
    const btn = $("button[type=submit]", cf);
    const nw = cf.elements.new.value, cfm = cf.elements.confirm.value;
    if (nw.length < me.min_length) { setStatus(st, L(`Lösenordet måste ha minst ${me.min_length} tecken.`, `The password must have at least ${me.min_length} characters.`), "error"); return; }
    if (nw !== cfm) { setStatus(st, L("Lösenorden är inte lika.", "The passwords do not match."), "error"); return; }
    btn.disabled = true;
    setStatus(st, L("Sparar...", "Saving..."));
    try {
      await post("api/password", { current, new: nw, confirm: cfm });
      current = "";
      setStatus(st, L("Lösenordet är bytt.", "The password has been changed."), "ok");
      enter();
    } catch (err) {
      setStatus(st, err.message, "error");
    } finally { btn.disabled = false; }
  });

  // Redan inloggad: gå vidare, eller visa bytet om standardlösenordet fortfarande gäller.
  try {
    const res = await fetch("api/me", { headers: { "X-Lang": LANG }, credentials: "same-origin" });
    const state = res.ok ? await res.json() : null;
    if (state && state.authenticated) {
      me = state;
      if (!me.must_change) { enter(); return; }
      cf.elements.user.value = me.user;
      localize();
      show("login");
      setStatus($("#login-status"), L("Logga in igen för att byta standardlösenordet.", "Log in again to change the default password."));
      return;
    }
  } catch (e) { /* visa inloggningen */ }
  show("login");
}

document.addEventListener("DOMContentLoaded", init);
