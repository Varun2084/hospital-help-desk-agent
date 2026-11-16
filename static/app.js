// OPD Sahayak: browser wala chat. Server ke /api/start aur /api/chat se baat karta hai.

const TEXT = {
  Hindi: {
    sub: "AI हेल्प डेस्क",
    sos: "इमरजेंसी? अभी <b>112</b> पर कॉल करें।",
    new: "नई बातचीत", lang: "English",
    placeholder: "अपना सवाल लिखें…",
    hello: "नमस्ते! मैं OPD सहायक हूँ। मैं सही विभाग बताने, OPD अपॉइंटमेंट बुक करने और अस्पताल की जानकारी देने में मदद कर सकता हूँ। आपको क्या चाहिए?",
    foot: "यह डॉक्टर नहीं है और बीमारी या दवा नहीं बताता।",
    chips: ["नया रजिस्ट्रेशन करना है", "कार्डियोलॉजी में अगले सोमवार का स्लॉट चाहिए", "OPD का समय क्या है?", "कौन-कौन से विभाग हैं?"],
    me: "आप", fail: "सर्वर से जुड़ नहीं पा रहा। इमरजेंसी में 112 पर कॉल करें।",
  },
  English: {
    sub: "AI Help Desk",
    sos: "Emergency? Call <b>112</b> now.",
    new: "New chat", lang: "हिंदी",
    placeholder: "Type your question…",
    hello: "Hello! I am OPD Sahayak. I can help you find the right department, book an OPD appointment and answer hospital questions. How can I help?",
    foot: "This is not a doctor and does not diagnose or suggest medicines.",
    chips: ["I want to register as a new patient", "I need a cardiology slot next Monday", "What are the OPD timings?", "Which departments are there?"],
    me: "You", fail: "Cannot reach the server. In an emergency, call 112.",
  },
};

const $ = (id) => document.getElementById(id);
let HOSPITAL = null;  // config se: hospital ka naam aur disclaimer
const state = { language: null, sessionId: null, busy: false, userId: getUserId() };

function getUserId() {
  // Har browser ki ek pehchaan, taaki patient ki baat-cheet alag rahe.
  let id = null;
  try { id = localStorage.getItem("opd_user_id"); } catch (e) { /* private mode */ }
  if (!id) {
    id = "web_" + (crypto.randomUUID ? crypto.randomUUID().replace(/-/g, "").slice(0, 16)
                                      : Math.random().toString(36).slice(2, 18));
    try { localStorage.setItem("opd_user_id", id); } catch (e) { /* ignore */ }
  }
  return id;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Model ke jawab me aane wala chhota markdown: **bold**, *italic*, "- " list, nayi line.
function renderMarkdown(text) {
  const lines = escapeHtml(text).split("\n");
  let html = "", inList = false;
  for (const raw of lines) {
    const line = raw.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|\s)\*(\S.*?)\*(?=\s|$)/g, "$1<i>$2</i>");
    const item = line.match(/^\s*[-*•]\s+(.*)$/);
    if (item) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${item[1]}</li>`; continue; }
    if (inList) { html += "</ul>"; inList = false; }
    if (line.trim()) html += `<p>${line}</p>`;
  }
  return html + (inList ? "</ul>" : "");
}

function addMessage(who, text, desk = "", kind = "agent") {
  const row = document.createElement("div");
  row.className = "row " + (who === "me" ? "me" : "bot");
  const bubble = document.createElement("div");
  bubble.className = "bubble " + kind;
  if (who === "me") bubble.textContent = text;
  else bubble.innerHTML = (desk ? `<div class="desk">${escapeHtml(desk)}</div>` : "") + renderMarkdown(text);
  if (who !== "me") {
    const av = document.createElement("img");
    av.src = "/static/logo.svg"; av.className = "avatar"; av.alt = "";
    row.appendChild(av);
  }
  row.appendChild(bubble);
  $("log").appendChild(row);
  $("log").scrollTop = $("log").scrollHeight;
  return row;
}

function showTyping() {
  const row = addMessage("bot", "");
  row.querySelector(".bubble").innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
  return row;
}

function applyLanguage(lang) {
  const t = TEXT[lang];
  document.documentElement.lang = lang === "Hindi" ? "hi" : "en";
  document.querySelector('[data-t="sub"]').textContent = HOSPITAL ? HOSPITAL.hospital_name : t.sub;
  document.querySelector('[data-t="sos"]').innerHTML = t.sos;
  document.querySelector('[data-t="foot"]').textContent = t.foot + (HOSPITAL ? " " + HOSPITAL.disclaimer : "");
  $("newBtn").textContent = t.new;
  $("langBtn").textContent = t.lang;
  $("input").placeholder = t.placeholder;
  $("chips").innerHTML = "";
  for (const c of t.chips) {
    const b = document.createElement("button");
    b.className = "chip"; b.type = "button"; b.textContent = c;
    b.onclick = () => send(c);
    $("chips").appendChild(b);
  }
}

async function start(lang) {
  state.language = lang;
  applyLanguage(lang);
  $("welcome").hidden = true; $("chat").hidden = false;
  $("newBtn").hidden = false; $("langBtn").hidden = false;
  $("log").innerHTML = "";
  try {
    const r = await fetch("/api/start", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language: lang, user_id: state.userId }) });
    if (!r.ok) throw new Error(r.status);
    state.sessionId = (await r.json()).session_id;
    addMessage("bot", TEXT[lang].hello);
  } catch (e) {
    addMessage("bot", TEXT[lang].fail, "", "error");
  }
  $("input").focus();
}

async function send(text) {
  text = text.trim();
  if (!text || state.busy || !state.sessionId) return;
  state.busy = true; $("send").disabled = true;
  addMessage("me", text);
  $("input").value = ""; autoGrow();
  const typing = showTyping();
  try {
    const r = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: state.userId, session_id: state.sessionId, message: text }) });
    const data = await r.json();
    typing.remove();
    if (!r.ok) throw new Error(data.detail || r.status);
    for (const m of data.replies) addMessage("bot", m.text, m.desk, m.kind);
    for (const c of data.cards || []) addCard(c);
  } catch (e) {
    typing.remove();
    addMessage("bot", TEXT[state.language].fail, "", "error");
  } finally {
    state.busy = false; $("send").disabled = false; $("input").focus();
  }
}

function autoGrow() {
  const el = $("input");
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 140) + "px";
}

fetch("/api/info").then((r) => r.json()).then((h) => {
  HOSPITAL = h;
  document.querySelector('[data-t="sub"]').textContent = h.hospital_name;
  document.title = "OPD Sahayak · " + h.hospital_name;
}).catch(() => {});

document.querySelectorAll(".lang").forEach((b) => (b.onclick = () => start(b.dataset.lang)));
$("newBtn").onclick = () => start(state.language);
$("langBtn").onclick = () => start(state.language === "Hindi" ? "English" : "Hindi");
$("form").onsubmit = (e) => { e.preventDefault(); send($("input").value); };
$("input").addEventListener("input", autoGrow);
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send($("input").value); }
});


// ---------- Confirm card: model sirf arzi banata hai; patient yahan button dabata hai ----------

const CARD_TEXT = {
  Hindi: {
    title: { book: "अपॉइंटमेंट की पुष्टि करें", cancel: "अपॉइंटमेंट रद्द करने की पुष्टि करें", register: "रजिस्ट्रेशन की पुष्टि करें" },
    hospital: "अस्पताल", department: "विभाग", date: "तारीख़", time: "समय", status: "स्थिति", name: "नाम",
    age: "उम्र", gender: "लिंग", phone: "फ़ोन", city: "शहर / गाँव", guardian: "अभिभावक", appointment: "अपॉइंटमेंट ID",
    pending: "पुष्टि बाकी", confirm: { book: "अपॉइंटमेंट पक्का करें", cancel: "रद्द करना पक्का करें", register: "रजिस्ट्रेशन पक्का करें" },
    discard: "अनुरोध हटाएँ", retry: "फिर से पक्का करें", booked: "पक्का हो गया", cancelled: "रद्द हो गया",
    registered: "रजिस्ट्रेशन हो गया", discarded: "अनुरोध हटा दिया गया", already_registered: "पहले से रजिस्टर्ड",
    in_progress: "अस्पताल के सिस्टम से जवाब नहीं आया। कुछ भी खोया नहीं; फिर से दबाएँ, दूसरी बुकिंग नहीं बनेगी।",
    note: "बटन दबाने से पहले विवरण जाँच लें। चैट में 'हाँ' लिखने से पुष्टि नहीं होती।",
  },
  English: {
    title: { book: "Confirm your appointment", cancel: "Confirm cancellation", register: "Confirm registration" },
    hospital: "Hospital", department: "Department", date: "Date", time: "Time", status: "Status", name: "Name",
    age: "Age", gender: "Gender", phone: "Phone", city: "Town / village", guardian: "Guardian", appointment: "Appointment ID",
    pending: "Confirmation pending", confirm: { book: "Confirm appointment", cancel: "Confirm cancellation", register: "Confirm registration" },
    discard: "Discard request", retry: "Try again", booked: "Confirmed", cancelled: "Cancelled",
    registered: "Registered", discarded: "Request discarded", already_registered: "Already registered",
    in_progress: "The hospital system did not answer. Nothing is lost; press again and no second booking is made.",
    note: "Check the details before you press a button. Typing 'yes' in the chat does not confirm.",
  },
};

function fmtDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat(state.language === "Hindi" ? "hi-IN" : "en-GB",
    { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, d)));
}

function fmtTime(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  return `${String(((h + 11) % 12) + 1).padStart(2, "0")}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}

function cardRows(c, t) {
  const s = c.summary || {}, rows = [];
  if (c.kind === "register") {
    rows.push([t.hospital, HOSPITAL ? HOSPITAL.hospital_name : ""], [t.name, s.full_name], [t.age, s.age],
              [t.gender, s.gender], [t.phone, s.phone], [t.city, s.city]);
    if (s.guardian_name) rows.push([t.guardian, s.guardian_name]);
  } else {
    rows.push([t.hospital, HOSPITAL ? HOSPITAL.hospital_name : ""]);
    if (c.kind === "cancel") rows.push([t.appointment, s.appointment_id]);
    else rows.push([t.department, s.department], [t.name, s.patient_name], [t.phone, s.phone]);
    rows.push([t.date, s.date ? fmtDate(s.date) : ""], [t.time, s.time ? fmtTime(s.time) : ""]);
  }
  return rows;
}

function addCard(c) {
  const t = CARD_TEXT[state.language];
  const row = document.createElement("div");
  row.className = "row bot";
  const av = document.createElement("img");
  av.src = "/static/logo.svg"; av.className = "avatar"; av.alt = "";
  const card = document.createElement("div");
  card.className = "card-confirm";
  const rows = cardRows(c, t).map(([k, v]) =>
    `<tr><th>${escapeHtml(String(k))}</th><td>${escapeHtml(String(v ?? ""))}</td></tr>`).join("");
  card.innerHTML = `<div class="card-title">${escapeHtml(t.title[c.kind] || t.title.book)}</div>
    <table>${rows}<tr><th>${escapeHtml(t.status)}</th><td class="card-status pending">${escapeHtml(t.pending)}</td></tr></table>
    <div class="card-note">${escapeHtml(t.note)}</div>
    <div class="card-actions"><button class="btn-confirm">${escapeHtml(t.confirm[c.kind] || t.confirm.book)}</button>
    <button class="btn-discard">${escapeHtml(t.discard)}</button></div>`;
  row.appendChild(av); row.appendChild(card);
  $("log").appendChild(row);
  $("log").scrollTop = $("log").scrollHeight;
  card.querySelector(".btn-confirm").onclick = () => act(c, card, "confirm");
  card.querySelector(".btn-discard").onclick = () => act(c, card, "discard");
}

async function act(c, card, which) {
  const t = CARD_TEXT[state.language];
  const buttons = card.querySelectorAll("button");
  buttons.forEach((b) => (b.disabled = true));
  const status = card.querySelector(".card-status");
  try {
    const r = await fetch(`/api/actions/${which}`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: state.userId, session_id: state.sessionId, action_id: c.action_id, fingerprint: c.fingerprint }) });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || r.status);
    const res = data.result;
    if (res.status === "in_progress") {           // HIS ka jawab nahin aaya: dobara dabane do
      status.className = "card-status warn"; status.textContent = t.in_progress;
      const confirmBtn = card.querySelector(".btn-confirm");
      confirmBtn.textContent = t.retry; confirmBtn.disabled = false;
      return;
    }
    const ok = ["booked", "cancelled", "registered", "already_registered", "discarded"].includes(res.status);
    const ref = res.appointment_id || res.patient_id || "";
    status.className = "card-status " + (ok ? (res.status === "discarded" ? "muted" : "ok") : "bad");
    status.textContent = ok ? `${t[res.status]}${ref ? " · " + ref : ""}` : (res.message || "Error");
    card.querySelector(".card-actions").remove();
  } catch (e) {
    status.className = "card-status bad"; status.textContent = TEXT[state.language].fail;
    buttons.forEach((b) => (b.disabled = false));
  }
}
