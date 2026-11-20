// Reception desk: atke hue kaam (scheduler me reschedule ka API nahin, ya nateeja saaf nahin) staff yahan hal karta hai.
// Staff ki pehchaan server tay karta hai (HttpOnly cookie, role 'staff'); yeh page sirf dikhata aur bhejta hai.

const $ = (id) => document.getElementById(id);
const desk = { staff: null, status: "pending" };
const KIND = { reschedule: "Reschedule request", verify_booking: "Verify booking", verify_reschedule: "Verify reschedule" };
const RESOLUTION = { changed: "Changed in scheduler", changed_manually: "Changed manually in HIS", declined: "Declined",
                     verified_done: "Verified: done", verified_not_done: "Verified: not done" };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(url, body) {
  const r = await fetch(url, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (r.status === 401) { showLogin(); throw new Error("login"); }
  if (!r.ok) throw new Error(data.detail || r.status);
  return data;
}

function showLogin() {
  desk.staff = null;
  $("login").hidden = false; $("desk").hidden = true;
  $("who").hidden = $("logout").hidden = $("refresh").hidden = true;
}

function showDesk() {
  $("login").hidden = true; $("desk").hidden = false;
  $("who").hidden = $("logout").hidden = $("refresh").hidden = false;
  $("who").textContent = `${desk.staff.name} · ${desk.staff.staff_id}`;
  load();
}

async function loginNext() {
  $("serr").textContent = "";
  try {
    if ($("scodeBox").hidden) {
      const r = await api("/api/staff/login/start", { staff_id: $("sid").value.trim().toUpperCase(), phone: $("sphone").value.trim() });
      $("sdemo").textContent = `Demo: SMS ki jagah code yahan. Code: ${r.demo_code}`;
      $("scodeBox").hidden = false; $("snext").textContent = "Log in"; $("scode").focus();
      return;
    }
    desk.staff = await api("/api/staff/login/verify", { staff_id: $("sid").value.trim().toUpperCase(), code: $("scode").value.trim() });
    $("scodeBox").hidden = true; $("snext").textContent = "Send code"; $("scode").value = "";
    showDesk();
  } catch (e) { $("serr").textContent = "Staff ID, phone ya code sahi nahin."; }
}

function itemHtml(i) {
  const d = i.details || {}, cur = i.current;
  const mine = i.claimed_by === desk.staff.staff_id;
  let actions = "";
  if (i.status === "pending") actions = `<button class="btn-confirm small" data-do="claim">Claim</button>`;
  else if (i.status === "in_review" && mine && i.kind === "reschedule") actions = `
      <input class="note" placeholder="Patient ke liye note (decline par zaroori)" maxlength="300">
      <button class="btn-confirm small" data-do="apply">Apply change</button>
      <button class="ghost small" data-do="done_manually">Done in HIS</button>
      <button class="ghost small danger" data-do="decline">Decline</button>`;
  else if (i.status === "in_review" && mine) actions = `<button class="btn-confirm small" data-do="check">Check scheduler</button>`;
  else if (i.status === "in_review") actions = `<span class="doc-note">Claimed by ${esc(i.claimed_by)}</span>`;
  return `<div class="rec-main">
      <b>${esc(KIND[i.kind] || i.kind)} · ${esc(i.id)}</b>
      <span>Patient: ${esc(i.patient.name)} (${esc(i.patient.id)}) · ${esc(i.patient.phone)}</span>
      <span>Booking: ${esc(i.booking_ref || "(new booking)")} · Abhi: ${cur ? esc(`${cur.date} ${cur.time} · ${cur.status}`) : "-"}</span>
      <span>Maanga: ${esc(d.requested || "")} · Request: ${esc(d.action_id || "")}</span>
      <span>Bana: ${esc(i.created_at)}${i.claimed_by ? ` · Claimed: ${esc(i.claimed_by)} ${esc(i.claimed_at)}` : ""}</span>
      ${i.status === "resolved" ? `<span><b>${esc(RESOLUTION[i.resolution] || i.resolution)}</b> by ${esc(i.resolved_by)} · ${esc(i.resolved_at)}${i.patient_update ? ` · Patient update: ${esc(i.patient_update)}` : ""}</span>
        <span>Patient ko: ${esc(i.patient_message)}</span>` : ""}
    </div>
    <em class="pill ${i.status}">${esc(i.status)}</em>
    <div class="staff-actions">${actions}</div>
    <div class="staff-result"></div>`;
}

async function load() {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.status === desk.status));
  const panel = $("items");
  try {
    const { items } = await api(`/api/staff/queue?status=${desk.status}`);
    panel.innerHTML = items.length ? "" : '<p class="doc-note">Koi kaam nahin.</p>';
    for (const i of items.reverse()) {
      const el = document.createElement("div");
      el.className = "rec"; el.innerHTML = itemHtml(i);
      el.querySelectorAll("[data-do]").forEach((b) => (b.onclick = () => act(i, b.dataset.do, el)));
      panel.appendChild(el);
    }
  } catch (e) { /* login maanga */ }
}

async function act(i, what, el) {
  const out = el.querySelector(".staff-result");
  el.querySelectorAll("button").forEach((b) => (b.disabled = true));
  try {
    if (what === "claim") { await api(`/api/staff/queue/${i.id}/claim`, {}); desk.status = "in_review"; return load(); }
    const note = el.querySelector(".note") ? el.querySelector(".note").value : "";
    const r = await api(`/api/staff/queue/${i.id}/resolve`, { decision: what, note });
    if (r.status === "resolved") { desk.status = "resolved"; return load(); }
    out.innerHTML = `<span class="bad">${esc(r.message)}</span>` + (r.alternatives && r.alternatives.length
      ? `<span class="doc-note"> Khaali: ${r.alternatives.slice(0, 6).map((o) => esc(`${o.date} ${o.time}`)).join(", ")}</span>` : "");
  } catch (e) {
    out.innerHTML = `<span class="bad">${esc(e.message)}</span>`;
  }
  el.querySelectorAll("button").forEach((b) => (b.disabled = false));
}

document.querySelectorAll(".tab").forEach((b) => (b.onclick = () => { desk.status = b.dataset.status; load(); }));
$("snext").onclick = loginNext;
$("scode").addEventListener("keydown", (e) => { if (e.key === "Enter") loginNext(); });
$("refresh").onclick = load;
$("logout").onclick = async () => { await fetch("/api/staff/logout", { method: "POST" }); $("items").innerHTML = ""; showLogin(); };
fetch("/api/info").then((r) => r.json()).then((h) => ($("hospital").textContent = `${h.hospital_name} · staff`)).catch(() => {});
fetch("/api/staff/me").then(async (r) => { if (r.ok) { desk.staff = await r.json(); showDesk(); } else showLogin(); });
