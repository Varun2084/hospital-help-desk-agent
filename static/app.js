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
    login: "लॉगिन", logout: "लॉगआउट", appts: "मेरी अपॉइंटमेंट", apptsChip: "मेरी अपॉइंटमेंट दिखाइए",
    loginTitle: "मरीज़ लॉगिन", pid: "मरीज़ ID", phone: "रजिस्टर्ड मोबाइल नंबर", code: "6 अंकों का कोड",
    sendCode: "कोड भेजें", verify: "लॉगिन करें", cancel: "रद्द करें", close: "बंद करें", back: "← सूची",
    demoCode: (c) => `डेमो: असली ऐप में यह कोड SMS से आता। आपका कोड: ${c}`,
    loginFail: "मरीज़ ID, फ़ोन या कोड सही नहीं है।", noAppts: "आपकी कोई अपॉइंटमेंट नहीं है।",
    newChatAfterLogin: "लॉगिन बदला है, इसलिए नई बातचीत शुरू की गई।",
    afterLogin: "मैंने लॉगिन कर लिया है। वही स्लॉट बुक कर दीजिए।",
    loginCard: "बुकिंग के लिए लॉगिन करें", loginCardNote: "यह स्लॉट याद रहेगा। लॉगिन के बाद कार्ड पर पक्का करें।",
    loginOnly: "आगे बढ़ने के लिए लॉगिन करें", loginOnlyNote: "आपकी अपॉइंटमेंट सिर्फ़ आपके लॉगिन से दिखती हैं।",
    statusWord: { confirmed: "पक्का", cancelled: "रद्द" },
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
    login: "Log in", logout: "Log out", appts: "My appointments", apptsChip: "Show my appointments",
    loginTitle: "Patient login", pid: "Patient ID", phone: "Registered mobile number", code: "6-digit code",
    sendCode: "Send code", verify: "Log in", cancel: "Cancel", close: "Close", back: "← List",
    demoCode: (c) => `Demo: a real app would send this code by SMS. Your code: ${c}`,
    loginFail: "Patient ID, phone or code is not right.", noAppts: "You have no appointments.",
    newChatAfterLogin: "The login changed, so a new chat was started.",
    afterLogin: "I have logged in. Please book the same slot.",
    loginCard: "Log in to book this slot", loginCardNote: "This slot is kept. After login, confirm it on the card.",
    loginOnly: "Log in to continue", loginOnlyNote: "Your appointments are shown only after you log in.",
    statusWord: { confirmed: "Confirmed", cancelled: "Cancelled" },
  },
};

const $ = (id) => document.getElementById(id);
let HOSPITAL = null;  // config se: hospital ka naam aur disclaimer
const state = { language: null, sessionId: null, busy: false, userId: getUserId(), patient: null, afterLogin: null };

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
  if (who === "me") bubble.textContent = maskPhones(text);   // apne bubble me bhi poora number nahin
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
  renderAuth();
  $("chips").innerHTML = "";
  for (const c of (state.patient ? [t.apptsChip, ...t.chips.slice(1)] : t.chips)) {
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

function maskPhones(text) {   // 9876543210 -> 98XXXXXX10 (server ko poora number jaata hai, screen par nahin)
  return text.replace(/(^|\D)([6-9]\d)\d{6}(\d{2})(?!\d)/g, "$1$2XXXXXX$3");
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
    if (r.status === 403) {          // yeh baat-cheet kisi aur login ki thi: nayi shuru
      await start(state.language);
      addMessage("bot", TEXT[state.language].newChatAfterLogin, "", "error");
      return;
    }
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

// ---------- Login, logout aur My Appointments ----------
// Kaun login hai, yeh server cookie (HttpOnly) se tay karta hai. Browser sirf /api/me se poochhta hai.

function renderAuth() {
  const t = TEXT[state.language || "English"];
  $("loginBtn").textContent = state.patient ? t.logout : t.login;
  $("apptsBtn").textContent = t.appts;
  $("apptsBtn").hidden = !state.patient;
  $("who").hidden = !state.patient;
  $("who").textContent = state.patient ? state.patient.name : "";
}

async function refreshMe() {
  try {
    const r = await fetch("/api/me");
    state.patient = r.ok ? await r.json() : null;
  } catch (e) { state.patient = null; }
  renderAuth();
}

function openLogin(afterLogin) {
  const t = TEXT[state.language || "English"];
  state.afterLogin = afterLogin || null;
  $("loginTitle").textContent = t.loginTitle; $("pidLabel").textContent = t.pid;
  $("phoneLabel").textContent = t.phone; $("codeLabel").textContent = t.code;
  $("loginCancel").textContent = t.cancel; $("loginNext").textContent = t.sendCode;
  $("codeBox").hidden = true; $("loginError").textContent = ""; $("lcode").value = "";
  $("loginDlg").showModal();
  $("pid").focus();
}

async function loginNext() {
  const t = TEXT[state.language || "English"];
  const body = { patient_id: $("pid").value.trim().toUpperCase(), phone: $("lphone").value.trim() };
  $("loginError").textContent = "";
  try {
    if ($("codeBox").hidden) {                       // kadam 1: code maango
      const r = await fetch("/api/login/start", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body) });
      if (!r.ok) throw new Error();
      $("demoCode").textContent = t.demoCode((await r.json()).demo_code);
      $("codeBox").hidden = false; $("loginNext").textContent = t.verify; $("lcode").focus();
      return;
    }
    const r = await fetch("/api/login/verify", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patient_id: body.patient_id, code: $("lcode").value.trim() }) });
    if (!r.ok) throw new Error();
    state.patient = await r.json();
    $("loginDlg").close();
    $("lphone").value = ""; $("lcode").value = "";
    applyLanguage(state.language || "English");
    const next = state.afterLogin; state.afterLogin = null;
    if (next) next();
  } catch (e) {
    $("loginError").textContent = t.loginFail;
  }
}

async function logout() {
  await fetch("/api/logout", { method: "POST" }).catch(() => {});
  state.patient = null;
  if ($("apptsDlg").open) $("apptsDlg").close();
  $("apptsBody").innerHTML = "";                     // private details screen se hatao
  if (state.language) await start(state.language);  // purani baat-cheet bhi screen se hat jaati hai
  else renderAuth();
}

async function openAppointments() {
  const t = TEXT[state.language || "English"];
  $("apptsTitle").textContent = t.appts; $("apptsClose").textContent = t.close;
  $("apptsBody").innerHTML = "";
  $("apptsDlg").showModal();
  const r = await fetch("/api/me/appointments");
  if (r.status === 401) { $("apptsDlg").close(); await refreshMe(); return openLogin(); }
  const list = (await r.json()).appointments || [];
  if (!list.length) { $("apptsBody").textContent = t.noAppts; return; }
  const ul = document.createElement("div");
  ul.className = "appt-list";
  for (const a of list) {
    const b = document.createElement("button");
    b.className = "appt-item";
    b.innerHTML = `<b>${escapeHtml(a.appointment_id)}</b><span>${escapeHtml(a.department)} · ${escapeHtml(fmtDate(a.date))} · ${escapeHtml(fmtTime(a.time))}</span><em class="${a.status}">${escapeHtml(t.statusWord[a.status] || a.status)}</em>`;
    b.onclick = () => openAppointment(a.appointment_id);
    ul.appendChild(b);
  }
  $("apptsBody").appendChild(ul);
}

async function openAppointment(ref) {
  const t = TEXT[state.language || "English"], ct = CARD_TEXT[state.language || "English"];
  const r = await fetch(`/api/me/appointments/${encodeURIComponent(ref)}`);
  if (!r.ok) { $("apptsBody").textContent = r.status === 401 ? t.loginFail : "Appointment not found"; return; }
  const a = await r.json();
  const rows = [[ct.appointment, a.appointment_id], [ct.department, a.department], ["📍", a.location],
                [ct.date, fmtDate(a.date)], [ct.time, fmtTime(a.time)], [ct.status, t.statusWord[a.status] || a.status]];
  $("apptsBody").innerHTML = `<table class="appt-detail">${rows.map(([k, v]) =>
    `<tr><th>${escapeHtml(k)}</th><td>${escapeHtml(String(v))}</td></tr>`).join("")}</table>
    <button type="button" class="ghost" id="apptBack">${escapeHtml(t.back)}</button>`;
  $("apptBack").onclick = openAppointments;
}

$("loginBtn").onclick = () => (state.patient ? logout() : openLogin());
$("loginNext").onclick = loginNext;
$("loginCancel").onclick = () => $("loginDlg").close();
$("lcode").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); loginNext(); } });
$("apptsBtn").onclick = openAppointments;
$("apptsClose").onclick = () => $("apptsDlg").close();
refreshMe();

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
    recovered: "पिछली कोशिश में जवाब नहीं आया था; अस्पताल के सिस्टम में वही बुकिंग मिली, नई नहीं बनी।",
    patient: "मरीज़ ID", pick: "यह समय अब खाली नहीं। नया समय चुनें:", slotMsg: (time) => `मुझे ${time} का स्लॉट चाहिए`,
    pending: "पुष्टि बाकी", confirm: { book: "अपॉइंटमेंट पक्का करें", cancel: "रद्द करना पक्का करें", register: "रजिस्ट्रेशन पक्का करें" },
    discard: "अनुरोध हटाएँ", retry: "स्थिति जाँचें", booked: "पक्का हो गया", cancelled: "रद्द हो गया",
    registered: "रजिस्ट्रेशन हो गया", discarded: "अनुरोध हटा दिया गया", already_registered: "पहले से रजिस्टर्ड",
    in_progress: "बुकिंग की स्थिति जाँची जा रही है। अस्पताल के सिस्टम से जवाब समय पर नहीं आया; दूसरी बुकिंग नहीं बनेगी।",
    note: "बटन दबाने से पहले विवरण जाँच लें। चैट में 'हाँ' लिखने से पुष्टि नहीं होती।",
  },
  English: {
    title: { book: "Confirm your appointment", cancel: "Confirm cancellation", register: "Confirm registration" },
    hospital: "Hospital", department: "Department", date: "Date", time: "Time", status: "Status", name: "Name",
    age: "Age", gender: "Gender", phone: "Phone", city: "Town / village", guardian: "Guardian", appointment: "Appointment ID",
    recovered: "The last attempt got no answer; the hospital system had the same booking, so no new one was made.",
    patient: "Patient ID", pick: "That time is no longer free. Pick a new time:", slotMsg: (time) => `I want the ${time} slot`,
    pending: "Confirmation pending", confirm: { book: "Confirm appointment", cancel: "Confirm cancellation", register: "Confirm registration" },
    discard: "Discard request", retry: "Check status", booked: "Confirmed", cancelled: "Cancelled",
    registered: "Registered", discarded: "Request discarded", already_registered: "Already registered",
    in_progress: "Verifying booking status. The hospital system did not answer in time; no second booking will be made.",
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

function addLoginCard(c) {
  // Bina login booking ki koshish: chuna hua slot dikhao aur Login button. Login ke baad wahi slot dobara maango.
  const t = TEXT[state.language], ct = CARD_TEXT[state.language], s = c.summary || {};
  const row = document.createElement("div");
  row.className = "row bot";
  row.innerHTML = '<img src="/static/logo.svg" class="avatar" alt="">';
  const card = document.createElement("div");
  card.className = "card-confirm";
  const rows = s.time ? [[ct.department, s.department], [ct.date, fmtDate(s.date)], [ct.time, fmtTime(s.time)]] : [];
  card.innerHTML = `<div class="card-title">${escapeHtml(s.time ? t.loginCard : t.loginOnly)}</div>
    <table>${rows.map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td>${escapeHtml(String(v))}</td></tr>`).join("")}</table>
    <div class="card-note">${escapeHtml(s.time ? t.loginCardNote : t.loginOnlyNote)}</div>
    <div class="card-actions"><button class="btn-confirm">${escapeHtml(t.login)}</button></div>`;
  card.querySelector("button").onclick = () => openLogin(() => { card.querySelector(".card-actions")?.remove();
    if (s.time) send(t.afterLogin); });
  row.appendChild(card);
  $("log").appendChild(row);
  $("log").scrollTop = $("log").scrollHeight;
}

function addCard(c) {
  if (c.kind === "login") return addLoginCard(c);
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
    if (res.status === "in_progress") {           // HIS ka jawab nahin aaya: usi request_id se status jaanchein
      status.className = "card-status warn"; status.textContent = t.in_progress;
      const confirmBtn = card.querySelector(".btn-confirm");
      confirmBtn.textContent = t.retry; confirmBtn.disabled = false;
      card.querySelector(".btn-discard")?.remove();  // arzi HIS ko ja chuki; ab hatayi nahin ja sakti
      return;
    }
    const ok = ["booked", "cancelled", "registered", "already_registered", "discarded"].includes(res.status);
    const ref = res.appointment_id || res.patient_id || "";
    status.className = "card-status " + (ok ? (res.status === "discarded" ? "muted" : "ok") : "bad");
    status.textContent = ok ? `${t[res.status]}${ref ? " · " + ref : ""}` : (res.message || "Error");
    card.querySelector(".card-actions").remove();
    if (res.note && res.status === "booked") card.querySelector(".card-note").textContent = t.recovered;
    if (res.free_slots && res.free_slots.length) {  // slot chhin gaya: naye samay, ek click me
      const pick = document.createElement("div");
      pick.className = "card-pick";
      pick.innerHTML = `<div class="card-note">${escapeHtml(t.pick)}</div>`;
      const chips = document.createElement("div");
      chips.className = "card-actions";
      for (const time of res.free_slots) {
        const b = document.createElement("button");
        b.className = "btn-discard"; b.textContent = fmtTime(time);
        b.onclick = () => { pick.remove(); send(t.slotMsg(time)); };
        chips.appendChild(b);
      }
      pick.appendChild(chips); card.appendChild(pick);
    }
  } catch (e) {
    status.className = "card-status bad"; status.textContent = TEXT[state.language].fail;
    buttons.forEach((b) => (b.disabled = false));
  }
}
