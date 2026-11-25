"use strict";

const ws = Blockly.inject("workspace", {
  toolbox: TOOLBOX,
  renderer: "zelos",
  media: "vendor/blockly/media/",
  trashcan: true,
  zoom: { controls: true, startScale: 0.95, wheel: true },
  grid: { spacing: 24, length: 2, colour: "#d6e2f5", snap: true },
});

const $ = (id) => document.getElementById(id);
let loading = false;
let dirty = false;
let localMsg = "", localMsgUntil = 0, localMsgIsInfo = false;

function setDirty(v) { dirty = v; $("dirty").hidden = !v; }
function say(text, info) { localMsg = text; localMsgIsInfo = !!info; localMsgUntil = Date.now() + 5000; renderMessage(text, info); }
function renderMessage(text, info) {
  const el = $("message");
  el.textContent = text;
  el.className = info ? "info" : "";
}

async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const res = await fetch(path, opt);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || ("エラー " + res.status));
  return data;
}

function loadWorkspace(state, markDirty) {
  loading = true;
  try {
    ws.clear();
    if (state) Blockly.serialization.workspaces.load(state, ws);
  } finally {
    loading = false;
  }
  sentSnapshot = markDirty ? null : snapshot();
  setDirty(!!markDirty);
}

// 「おくった」ときのブロックの中身と比べて、変わっていたら「未送信」を出す
let sentSnapshot = null;
function snapshot() { return JSON.stringify(workspaceToProgram(ws)); }
ws.addChangeListener((e) => {
  if (e.isUiEvent) return;
  setDirty(sentSnapshot === null || snapshot() !== sentSnapshot);
});

async function sendProgram() {
  try {
    const program = workspaceToProgram(ws);
    await api("/api/program", {
      workspace: Blockly.serialization.workspaces.save(ws),
      program,
    });
    sentSnapshot = JSON.stringify(program);
    setDirty(false);
    say("おくったよ！ ボタンを おしてみよう", true);
  } catch (err) {
    say("おくれませんでした: " + err.message);
  }
}

async function emergencyStop() {
  try { await api("/api/stop", {}); say("とまったよ（ちゃくりく）", true); }
  catch (err) { say("とめられません: " + err.message); }
}

$("send").onclick = sendProgram;
$("stop").onclick = emergencyStop;
document.addEventListener("keydown", (e) => {
  const t = e.target;
  const typing = t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable);
  if (e.key === "Escape" || (e.code === "Space" && !typing)) {
    e.preventDefault();
    emergencyStop();
  }
});

$("reset").onclick = async () => {
  if (!confirm("いまの ブロックを けして、はじめの ブロックに もどすよ。いい？")) return;
  try {
    const data = await api("/api/default", {});
    loadWorkspace(data.workspace);
    say("もどしたよ", true);
  } catch (err) { say("もどせません: " + err.message); }
};

$("save-file").onclick = () => {
  const blob = new Blob([JSON.stringify({ workspace: Blockly.serialization.workspaces.save(ws) })],
                        { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "drone-blocks.json";
  a.click();
  URL.revokeObjectURL(a.href);
};
$("load-file").onclick = () => $("file-input").click();
$("file-input").onchange = async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    loadWorkspace(data.workspace, true);
    say("ひらいたよ。「おくる」を おしてね", true);
  } catch (err) { say("ひらけませんでした"); }
};

// ---- 画面のコントローラー (micro:bit が無いとき) ----
const vin = { p1: 512, p2: 512, red: 0, green: 0, blue: 0 };
function pushInput() { api("/api/input", vin).catch(() => {}); }
document.querySelectorAll(".vbtn").forEach((b) => {
  const k = b.dataset.k;
  const set = (v) => { vin[k] = v; b.classList.toggle("on", !!v); pushInput(); };
  b.onpointerdown = () => set(1);
  ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => b.addEventListener(ev, () => { if (vin[k]) set(0); }));
});
const STICK = { fwd: ["p1", 0], back: ["p1", 1023], right: ["p2", 0], left: ["p2", 1023] };
document.querySelectorAll(".vstick").forEach((b) => {
  const [axis, val] = STICK[b.dataset.s];
  const set = (on) => { vin[axis] = on ? val : 512; b.classList.toggle("on", on); pushInput(); };
  b.onpointerdown = () => set(true);
  ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => b.addEventListener(ev, () => { if (vin[axis] !== 512) set(false); }));
});

// ---- 状態表示 ----
let lastHighlight = null;
function highlight(id) {
  if (id === lastHighlight) return;
  try {
    if (lastHighlight) ws.highlightBlock(lastHighlight, false);
    if (id) ws.highlightBlock(id, true);
  } catch (e) { /* 表示だけなので失敗しても無視 */ }
  lastHighlight = id;
}

function render(s) {
  const conn = $("chip-conn");
  conn.textContent = s.connected ? "つながった" : "ドローンを まっています…";
  conn.className = "chip " + (s.connected ? "ok" : "warn");
  const fly = $("chip-fly");
  fly.textContent = s.flying ? "とんでいる" : "ちじょう";
  fly.className = "chip" + (s.flying ? " warn" : "");
  $("chip-bat").textContent = "バッテリー " + (s.battery == null ? "--" : s.battery + "%");
  $("chip-dry").hidden = !s.dry_run;
  $("virtual").hidden = s.microbit;

  const names = [];
  if (s.input[2]) names.push("あかボタン");
  s.active.forEach((a) => names.push(INPUT_LABEL[a] || a));
  $("pressed").innerHTML = names.length ? names.map((n) => "<span>" + n + "</span>").join("") : "<em>なし</em>";

  highlight(s.busy ? s.current_id : null);
  if (Date.now() > localMsgUntil) renderMessage(s.message || "", false);
}

async function poll() {
  try { render(await api("/api/status")); }
  catch (e) { $("chip-conn").textContent = "サーバーと つながっていません"; $("chip-conn").className = "chip warn"; }
  setTimeout(poll, 250);
}

(async function init() {
  try {
    const data = await api("/api/program");
    loadWorkspace(data.workspace);
  } catch (e) { say("プログラムを よみこめませんでした"); }
  poll();
})();
