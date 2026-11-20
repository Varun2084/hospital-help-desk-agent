// OPD Sahayak v0.14.0: browser wala chat. Server ke /api/start aur /api/chat se baat karta hai.

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
    login: "लॉगिन", logout: "लॉगआउट", appts: "मेरा डैशबोर्ड", apptsChip: "मेरी अपॉइंटमेंट दिखाइए",
    loginTitle: "मरीज़ लॉगिन", pid: "मरीज़ ID", phone: "रजिस्टर्ड मोबाइल नंबर", code: "6 अंकों का कोड",
    sendCode: "कोड भेजें", verify: "लॉगिन करें", cancel: "रद्द करें", close: "बंद करें", back: "← सूची",
    demoCode: (c) => `डेमो: असली ऐप में यह कोड SMS से आता। आपका कोड: ${c}`,
    loginFail: "मरीज़ ID, फ़ोन या कोड सही नहीं है।", noAppts: "आपकी कोई अपॉइंटमेंट नहीं है।",
    newChatAfterLogin: "लॉगिन बदला है, इसलिए नई बातचीत शुरू की गई।",
    afterLogin: "मैंने लॉगिन कर लिया है। वही स्लॉट बुक कर दीजिए।",
    loginCard: "बुकिंग के लिए लॉगिन करें", loginCardNote: "यह स्लॉट याद रहेगा। लॉगिन के बाद कार्ड पर पक्का करें।",
    loginOnly: "आगे बढ़ने के लिए लॉगिन करें", loginOnlyNote: "आपकी अपॉइंटमेंट सिर्फ़ आपके लॉगिन से दिखती हैं।",
    statusWord: { confirmed: "पक्का", cancelled: "रद्द" },
    dash: "मेरा डैशबोर्ड", backToChat: "← चैट", nextAppt: "अगली अपॉइंटमेंट", noNext: "कोई आने वाली अपॉइंटमेंट नहीं।",
    tabs: { appointments: "अपॉइंटमेंट", prescriptions: "प्रिस्क्रिप्शन", lab_tests: "लैब टेस्ट" },
    requests: "रिसेप्शन को भेजी गई रिक्वेस्ट", reqStatus: { pending: "समीक्षा बाकी", in_review: "रिसेप्शन देख रहा है", resolved: "पूरी हुई" },
    reqKind: { reschedule: "समय बदलने की रिक्वेस्ट", verify_booking: "बुकिंग की जाँच", verify_reschedule: "बदलाव की जाँच" },
    upcoming: "आने वाली", past: "पिछली अपॉइंटमेंट", view: "देखें", hide: "छिपाएँ", reschedule: "रीशेड्यूल",
    parts: { any: "कोई भी समय", morning: "सुबह", afternoon: "दोपहर", evening: "शाम" }, noAlt: "इस पसंद में कोई खाली स्लॉट नहीं।",
    viewRx: "प्रिस्क्रिप्शन देखें", viewReport: "रिपोर्ट देखें", doctor: "डॉक्टर", visit: "विज़िट",
    orderedOn: "ऑर्डर", noReport: "रिपोर्ट अभी जारी नहीं हुई। तैयार होने पर यहीं दिखेगी।",
    noRx: "अभी कोई प्रिस्क्रिप्शन नहीं।", noLab: "अभी कोई लैब टेस्ट नहीं।",
    labSteps: ["ऑर्डर हुआ", "सैंपल लिया गया", "जाँच चल रही है", "रिपोर्ट उपलब्ध"],
    openTab: { lab_tests: "लैब टेस्ट खोलें", prescriptions: "प्रिस्क्रिप्शन खोलें", appointments: "अपॉइंटमेंट खोलें" },
    docNote: "दस्तावेज़ अस्पताल का मूल रिकॉर्ड है; इसे AI ने नहीं लिखा। समझने के लिए डॉक्टर से पूछें।",
    notifs: "सूचनाएँ", noNotifs: "अभी कोई सूचना नहीं।", notFound: "यह रिकॉर्ड आपके खाते में नहीं मिला।",
    opened: "सूचना से खोला गया रिकॉर्ड नीचे हाइलाइट है।",
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
    login: "Log in", logout: "Log out", appts: "My Dashboard", apptsChip: "Show my appointments",
    loginTitle: "Patient login", pid: "Patient ID", phone: "Registered mobile number", code: "6-digit code",
    sendCode: "Send code", verify: "Log in", cancel: "Cancel", close: "Close", back: "← List",
    demoCode: (c) => `Demo: a real app would send this code by SMS. Your code: ${c}`,
    loginFail: "Patient ID, phone or code is not right.", noAppts: "You have no appointments.",
    newChatAfterLogin: "The login changed, so a new chat was started.",
    afterLogin: "I have logged in. Please book the same slot.",
    loginCard: "Log in to book this slot", loginCardNote: "This slot is kept. After login, confirm it on the card.",
    loginOnly: "Log in to continue", loginOnlyNote: "Your appointments are shown only after you log in.",
    statusWord: { confirmed: "Confirmed", cancelled: "Cancelled" },
    dash: "My Dashboard", backToChat: "← Chat", nextAppt: "Next appointment", noNext: "No upcoming appointment.",
    tabs: { appointments: "Appointments", prescriptions: "Prescriptions", lab_tests: "Lab Tests" },
    requests: "Requests sent to reception", reqStatus: { pending: "Review pending", in_review: "Reception reviewing", resolved: "Resolved" },
    reqKind: { reschedule: "Reschedule request", verify_booking: "Booking check", verify_reschedule: "Change check" },
    upcoming: "Upcoming", past: "Past appointments", view: "View", hide: "Hide", reschedule: "Reschedule",
    parts: { any: "Any time", morning: "Morning", afternoon: "Afternoon", evening: "Evening" }, noAlt: "No free slot for this choice.",
    viewRx: "View prescription", viewReport: "View report", doctor: "Doctor", visit: "Visit",
    orderedOn: "Ordered", noReport: "Report not released yet. It will appear here when ready.",
    noRx: "No prescriptions yet.", noLab: "No lab tests yet.",
    labSteps: ["Ordered", "Sample collected", "Processing", "Report available"],
    openTab: { lab_tests: "Open Lab Tests", prescriptions: "Open Prescriptions", appointments: "Open Appointments" },
    docNote: "Documents are the hospital's original records, not written by AI. Ask your doctor to explain them.",
    notifs: "Notifications", noNotifs: "No notifications yet.", notFound: "This record was not found in your account.",
    opened: "The record from your notification is highlighted below.",
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
  show("chat");
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
  $("bellBtn").hidden = !state.patient;
  $("bellBtn").setAttribute("aria-label", t.notifs);
  if (!state.patient) { $("inbox").hidden = true; $("bellCount").hidden = true; }
  $("who").hidden = !state.patient;
  $("who").textContent = state.patient ? state.patient.name : "";
}

async function refreshMe() {
  try {
    const r = await fetch("/api/me");
    state.patient = r.ok ? await r.json() : null;
  } catch (e) { state.patient = null; }
  renderAuth();
  refreshInbox();
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
    refreshInbox();
    const next = state.afterLogin; state.afterLogin = null;
    if (next) next();
  } catch (e) {
    $("loginError").textContent = t.loginFail;
  }
}

async function logout() {
  await fetch("/api/logout", { method: "POST" }).catch(() => {});
  state.patient = null;
  dash.data = null;
  inbox.items = []; $("inboxList").innerHTML = ""; clearTimeout(inbox.timer);
  $("nextAppt").innerHTML = ""; $("tabPanel").innerHTML = "";   // private details screen se hatao
  if (state.language) await start(state.language);  // purani baat-cheet bhi screen se hat jaati hai
  else { show("welcome"); renderAuth(); }
}

// ---------- Mera Dashboard (Lesson 5) ----------
// Teen tabs. Har list aur har document server se, login kiye patient tak simit. Documents protected
// endpoint se khulte hain (link save karke baad me kholein to bhi wahi jaanch).
const dash = { tab: "appointments", data: null };

function show(view) {   // "chat" | "dash" | "welcome"
  $("dash").hidden = view !== "dash";
  $("chat").hidden = view !== "chat";
  $("welcome").hidden = view !== "welcome";
}

async function openDashboard(tab) {
  if (!state.patient) return openLogin(() => openDashboard(tab));
  dash.tab = tab || dash.tab;
  const t = TEXT[state.language || "English"];
  $("dashTitle").textContent = `${t.dash} · ${state.patient.name}`;
  $("backToChat").textContent = t.backToChat;
  document.querySelectorAll(".tab").forEach((b) => (b.textContent = t.tabs[b.dataset.tab]));
  show("dash");
  const get = (u) => fetch(u).then((r) => (r.status === 401 ? Promise.reject(401) : r.json()));
  try {
    const [a, p, l, q] = await Promise.all([get("/api/me/appointments"), get("/api/me/prescriptions"),
      get("/api/me/lab-tests"), get("/api/me/requests")]);
    dash.data = { appointments: a.appointments || [], prescriptions: p.prescriptions || [], lab_tests: l.lab_tests || [],
                  requests: q.requests || [] };
  } catch (e) {   // session khatam: dobara login
    await refreshMe();
    return openLogin(() => openDashboard(tab));
  }
  renderNext(); renderTab();
}

function today() { return new Date().toLocaleDateString("en-CA"); }   // YYYY-MM-DD (browser ka din)

function renderNext() {
  const t = TEXT[state.language || "English"];
  const next = dash.data.appointments.filter((a) => a.status === "confirmed" && a.date >= today())
    .sort((x, y) => (x.date + x.time).localeCompare(y.date + y.time))[0];
  $("nextAppt").innerHTML = `<div class="next-label">${escapeHtml(t.nextAppt)}</div>` + (next
    ? `<div class="next-main">${escapeHtml(fmtDate(next.date))} · ${escapeHtml(fmtTime(next.time))}</div>
       <div class="next-sub">${escapeHtml(next.department)} · ${escapeHtml(next.location)} · <b>${escapeHtml(next.appointment_id)}</b></div>`
    : `<div class="next-sub">${escapeHtml(t.noNext)}</div>`);
}

function renderTab() {
  const t = TEXT[state.language || "English"], ct = CARD_TEXT[state.language || "English"];
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === dash.tab));
  const panel = $("tabPanel");
  panel.innerHTML = "";
  const item = (html) => { const d = document.createElement("div"); d.className = "rec"; d.innerHTML = html; panel.appendChild(d); return d; };
  const heading = (text) => { const h = document.createElement("h3"); h.textContent = text; panel.appendChild(h); };
  if (dash.tab === "appointments") {
    const now = today(), list = dash.data.appointments;
    for (const [label, rows] of [[t.upcoming, list.filter((a) => a.date >= now)], [t.past, list.filter((a) => a.date < now).reverse()]]) {
      if (!rows.length) continue;
      heading(label);
      for (const a of rows) {
        const d = item(`<div class="rec-main"><b>${escapeHtml(a.department)}</b><span>${escapeHtml(fmtDate(a.date))} · ${escapeHtml(fmtTime(a.time))}</span></div>
          <em class="pill ${a.status}">${escapeHtml(t.statusWord[a.status] || a.status)}</em>
          <button type="button" class="ghost small view-btn">${escapeHtml(t.view)}</button>
          ${a.date >= now && a.status === "confirmed" ? `<button type="button" class="btn-confirm small resched-btn">${escapeHtml(t.reschedule)}</button>` : ""}
          <div class="rec-more" hidden>${escapeHtml(ct.appointment)}: <b>${escapeHtml(a.appointment_id)}</b> · 📍 ${escapeHtml(a.location)}</div>
          <div class="resched" hidden></div>`);
        d.dataset.ref = a.appointment_id;
        const btn = d.querySelector(".view-btn"), more = d.querySelector(".rec-more");
        btn.onclick = () => { more.hidden = !more.hidden; btn.textContent = more.hidden ? t.view : t.hide; };
        const rb = d.querySelector(".resched-btn");
        if (rb) rb.onclick = () => openReschedule(a, d.querySelector(".resched"), "any");
      }
    }
    if (!list.length) panel.textContent = t.noNext;
    if (dash.data.requests.length) {   // reception ke paas gayi requests ki sthiti
      heading(t.requests);
      for (const q of dash.data.requests) {
        item(`<div class="rec-main"><b>${escapeHtml(t.reqKind[q.kind] || q.kind)} · ${escapeHtml(q.booking_ref || "")}</b>
          <span>${escapeHtml(q.requested || "")} · ${escapeHtml(q.message || "")}</span></div>
          <em class="pill ${q.status}">${escapeHtml(t.reqStatus[q.status] || q.status)}</em>`).dataset.ref = q.id;
      }
    }
  } else if (dash.tab === "prescriptions") {
    if (!dash.data.prescriptions.length) { panel.textContent = t.noRx; return; }
    for (const p of dash.data.prescriptions) {
      item(`<div class="rec-main"><b>${escapeHtml(p.department)}</b><span>${escapeHtml(t.visit)} ${escapeHtml(fmtDate(p.visit_date))} · ${escapeHtml(t.doctor)}: ${escapeHtml(p.doctor)}</span></div>
        <a class="btn-confirm small" target="_blank" rel="noopener" href="/api/me/prescriptions/${encodeURIComponent(p.prescription_id)}/document">${escapeHtml(t.viewRx)}</a>`);
    }
    panel.insertAdjacentHTML("beforeend", `<p class="doc-note">${escapeHtml(t.docNote)}</p>`);
  } else {
    if (!dash.data.lab_tests.length) { panel.textContent = t.noLab; return; }
    for (const l of dash.data.lab_tests) {
      const steps = t.labSteps.map((s, i) => `<li class="${i < l.step ? "done" : ""}${i === l.step - 1 ? " now" : ""}">${escapeHtml(s)}</li>`).join("");
      const li = item(`<div class="rec-main"><b>${escapeHtml(l.test_name)}</b><span>${escapeHtml(t.orderedOn)}: ${escapeHtml(fmtDate(l.ordered_on))} · ${escapeHtml(l.department)}</span>
          <ol class="steps">${steps}</ol></div>` + (l.report_available
        ? `<a class="btn-confirm small" target="_blank" rel="noopener" href="/api/me/lab-tests/${encodeURIComponent(l.test_id)}/report">${escapeHtml(t.viewReport)}</a>`
        : `<span class="no-report">${escapeHtml(t.noReport)}</span>`));
      li.dataset.ref = l.test_id;
    }
    panel.insertAdjacentHTML("beforeend", `<p class="doc-note">${escapeHtml(t.docNote)}</p>`);
  }
}

// Reschedule (Lesson 6): vikalp scheduler se, preview card (Current vs New), badlaav sirf "Confirm change" par.
async function openReschedule(a, panel, part) {
  const t = TEXT[state.language || "English"];
  panel.hidden = false;
  panel.innerHTML = `<div class="parts">${Object.entries(t.parts).map(([k, v]) =>
    `<button type="button" class="chip${k === part ? " on" : ""}" data-part="${k}">${escapeHtml(v)}</button>`).join("")}</div>
    <div class="alts"></div><div class="preview"></div>`;
  panel.querySelectorAll(".parts .chip").forEach((b) => (b.onclick = () => openReschedule(a, panel, b.dataset.part)));
  const r = await fetch(`/api/me/appointments/${encodeURIComponent(a.appointment_id)}/alternatives?part=${part}`);
  if (r.status === 401) { await refreshMe(); return openLogin(() => openDashboard("appointments")); }
  const data = await r.json();
  const alts = panel.querySelector(".alts");
  if (!r.ok || data.status !== "ok") { alts.textContent = data.message || data.detail || "Error"; return; }
  if (!data.alternatives.length) { alts.textContent = t.noAlt; return; }
  const byDate = {};
  for (const o of data.alternatives) (byDate[o.date] = byDate[o.date] || []).push(o);
  for (const [date, list] of Object.entries(byDate)) {
    const group = document.createElement("div");
    group.className = "alt-day";
    group.innerHTML = `<div class="alt-date">${escapeHtml(fmtDate(date))}</div>`;
    for (const o of list) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "chip"; b.textContent = fmtTime(o.time);
      b.onclick = () => previewReschedule(a.appointment_id, o.slot_id, panel.querySelector(".preview"));
      group.appendChild(b);
    }
    alts.appendChild(group);
  }
}

async function previewReschedule(ref, slotId, target) {
  target.innerHTML = "";
  const r = await fetch(`/api/me/appointments/${encodeURIComponent(ref)}/reschedule-preview`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ slot_id: slotId }) });
  const data = await r.json();
  if (!r.ok) { target.textContent = data.detail || "Error"; return; }
  addCard({ ...data, dashboard: true }, target);
}

// ---------- Notifications (Lesson 8) ----------
// Bell me sirf hospital ke approved generic sandesh. Tap: dashboard ka wahi record, jo server login aur
// maalik jaanch kar hi deta hai. Doosre patient ka link khule to "nahin mila" (kuch disclose nahin).
const inbox = { items: [], timer: null };
const TAB_FOR = { appointment: "appointments", request: "appointments", lab_test: "lab_tests" };

async function refreshInbox() {
  clearTimeout(inbox.timer);
  if (!state.patient) return;
  try {
    const r = await fetch("/api/me/notifications");
    if (r.ok) {
      const data = await r.json();
      inbox.items = data.notifications;
      $("bellCount").hidden = !data.unread;
      $("bellCount").textContent = data.unread > 9 ? "9+" : String(data.unread);
      if (!$("inbox").hidden) renderInbox();
    }
  } catch (e) { /* agli baar */ }
  inbox.timer = setTimeout(refreshInbox, 15000);
}

function renderInbox() {
  const t = TEXT[state.language || "English"], lang = state.language === "Hindi" ? "hi" : "en";
  $("inboxTitle").textContent = t.notifs; $("inboxClose").textContent = t.close;
  const list = $("inboxList");
  list.innerHTML = inbox.items.length ? "" : `<div class="inbox-empty">${escapeHtml(t.noNotifs)}</div>`;
  for (const n of inbox.items) {
    const b = document.createElement("button");
    b.type = "button"; b.className = "ntf" + (n.read ? "" : " unread");
    const when = new Intl.DateTimeFormat(lang === "hi" ? "hi-IN" : "en-GB", { day: "numeric", month: "short",
      hour: "2-digit", minute: "2-digit" }).format(new Date(n.created_at));
    b.innerHTML = `<span class="ntf-dot"></span><span class="ntf-body"><span class="ntf-title">${escapeHtml(n.title[lang])}</span>
      <span>${escapeHtml(n.body[lang])}</span><small>${escapeHtml(when)}</small></span>`;
    b.onclick = async () => {
      await fetch(`/api/me/notifications/${encodeURIComponent(n.id)}/read`, { method: "POST" }).catch(() => {});
      $("inbox").hidden = true; $("bellBtn").setAttribute("aria-expanded", "false");
      refreshInbox();
      openTarget(n.destination.view, n.destination.id);
    };
    list.appendChild(b);
  }
}

function toggleInbox() {
  const open = $("inbox").hidden;
  const top = document.querySelector(".top");   // header phone par do line ka ho sakta hai: uske neeche kholo
  $("inbox").style.top = `${top.offsetTop + top.offsetHeight + 6}px`;
  $("inbox").hidden = !open; $("bellBtn").setAttribute("aria-expanded", String(open));
  if (open) renderInbox();
}

async function openTarget(view, id) {   // notification ya saved link: "/?open=appointment:HIS-APT-001"
  if (!TAB_FOR[view]) return;
  await openDashboard(TAB_FOR[view]);
  const t = TEXT[state.language || "English"];
  const row = $("tabPanel").querySelector(`.rec[data-ref="${CSS.escape(id)}"]`);
  const note = document.createElement("p");
  note.className = "dash-note" + (row ? "" : " bad");
  note.textContent = row ? t.opened : t.notFound;
  $("tabPanel").prepend(note);
  if (!row) return;
  row.classList.add("flash");
  const more = row.querySelector(".rec-more"), btn = row.querySelector(".view-btn");
  if (more && more.hidden) { more.hidden = false; if (btn) btn.textContent = t.hide; }
  row.scrollIntoView({ block: "center", behavior: "smooth" });
}

$("bellBtn").onclick = toggleInbox;
$("inboxClose").onclick = toggleInbox;

function leaveDashboard() {
  show(state.language ? "chat" : "welcome");
}

document.querySelectorAll(".tab").forEach((b) => (b.onclick = () => { dash.tab = b.dataset.tab; renderTab(); }));
$("backToChat").onclick = leaveDashboard;

$("loginBtn").onclick = () => (state.patient ? logout() : openLogin());
$("loginNext").onclick = loginNext;
$("loginCancel").onclick = () => $("loginDlg").close();
$("lcode").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); loginNext(); } });
$("apptsBtn").onclick = () => openDashboard("appointments");
refreshMe().then(() => {   // saved document link par login ke liye wapas aaye: login, phir dashboard
  const params = new URLSearchParams(location.search);
  if (params.get("login") === "1" && !state.patient) {
    history.replaceState(null, "", "/");
    openLogin(() => openDashboard("prescriptions"));
  }
  const open = params.get("open");   // notification ka link: pehle login (agar nahin), phir wahi record
  if (open && open.includes(":")) {
    history.replaceState(null, "", "/");
    const [view, ...rest] = open.split(":"), id = rest.join(":");
    if (state.patient) openTarget(view, id); else openLogin(() => openTarget(view, id));
  }
});

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
    title: { book: "अपॉइंटमेंट की पुष्टि करें", cancel: "अपॉइंटमेंट रद्द करने की पुष्टि करें", register: "रजिस्ट्रेशन की पुष्टि करें",
             reschedule: "अपॉइंटमेंट बदलने की पुष्टि करें" },
    current: "मौजूदा अपॉइंटमेंट", newAppt: "नई अपॉइंटमेंट", location: "जगह", keep: "मौजूदा अपॉइंटमेंट रखें",
    rescheduled: "बदल गई", reception_review: "रिसेप्शन समीक्षा बाकी", kept: "मौजूदा अपॉइंटमेंट ही रखी गई",
    changing: "बदलाव की पुष्टि हो रही है। अस्पताल के सिस्टम से जवाब समय पर नहीं आया; दूसरा बदलाव नहीं होगा।",
    recoveredChange: "पिछली कोशिश में जवाब नहीं आया था; सिस्टम में वही बदलाव मिला।",
    pickChange: "आपकी पुरानी अपॉइंटमेंट चालू है। नया समय चुनें:",
    hospital: "अस्पताल", department: "विभाग", date: "तारीख़", time: "समय", status: "स्थिति", name: "नाम",
    age: "उम्र", gender: "लिंग", phone: "फ़ोन", city: "शहर / गाँव", guardian: "अभिभावक", appointment: "अपॉइंटमेंट ID",
    recovered: "पिछली कोशिश में जवाब नहीं आया था; अस्पताल के सिस्टम में वही बुकिंग मिली, नई नहीं बनी।",
    patient: "मरीज़ ID", pick: "यह समय अब खाली नहीं। नया समय चुनें:", slotMsg: (time) => `मुझे ${time} का स्लॉट चाहिए`,
    pending: "पुष्टि बाकी", confirm: { book: "अपॉइंटमेंट पक्का करें", cancel: "रद्द करना पक्का करें", register: "रजिस्ट्रेशन पक्का करें", reschedule: "बदलाव पक्का करें" },
    discard: "अनुरोध हटाएँ", retry: "स्थिति जाँचें", booked: "पक्का हो गया", cancelled: "रद्द हो गया",
    registered: "रजिस्ट्रेशन हो गया", discarded: "अनुरोध हटा दिया गया", already_registered: "पहले से रजिस्टर्ड",
    in_progress: "बुकिंग की स्थिति जाँची जा रही है। अस्पताल के सिस्टम से जवाब समय पर नहीं आया; दूसरी बुकिंग नहीं बनेगी।",
    note: "बटन दबाने से पहले विवरण जाँच लें। चैट में 'हाँ' लिखने से पुष्टि नहीं होती।",
  },
  English: {
    title: { book: "Confirm your appointment", cancel: "Confirm cancellation", register: "Confirm registration",
             reschedule: "Confirm appointment change" },
    current: "Current appointment", newAppt: "New appointment", location: "Location", keep: "Keep current appointment",
    rescheduled: "Changed", reception_review: "Reception review pending", kept: "Current appointment kept",
    changing: "Verifying the change. The hospital system did not answer in time; no second change will be made.",
    recoveredChange: "The last attempt got no answer; the hospital system had the same change.",
    pickChange: "Your original appointment is still active. Pick a new time:",
    hospital: "Hospital", department: "Department", date: "Date", time: "Time", status: "Status", name: "Name",
    age: "Age", gender: "Gender", phone: "Phone", city: "Town / village", guardian: "Guardian", appointment: "Appointment ID",
    recovered: "The last attempt got no answer; the hospital system had the same booking, so no new one was made.",
    patient: "Patient ID", pick: "That time is no longer free. Pick a new time:", slotMsg: (time) => `I want the ${time} slot`,
    pending: "Confirmation pending", confirm: { book: "Confirm appointment", cancel: "Confirm cancellation", register: "Confirm registration", reschedule: "Confirm change" },
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
  } else if (c.kind === "reschedule") {   // Current vs New, saath-saath
    rows.push([t.appointment, s.appointment_id], [t.department, s.department],
              [t.current, `${fmtDate(s.current_date)} · ${fmtTime(s.current_time)}`],
              [t.newAppt, `${fmtDate(s.new_date)} · ${fmtTime(s.new_time)}`], [t.location, s.location]);
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

function addOpenTabCard(c) {
  // Chat records nahin dikhata: sirf dashboard ka sahi tab kholne ka button.
  const t = TEXT[state.language], section = (c.summary || {}).section || "lab_tests";
  const row = document.createElement("div");
  row.className = "row bot";
  row.innerHTML = '<img src="/static/logo.svg" class="avatar" alt="">';
  const b = document.createElement("button");
  b.className = "btn-confirm open-tab"; b.textContent = t.openTab[section] || t.dash;
  b.onclick = () => openDashboard(section);
  row.appendChild(b);
  $("log").appendChild(row);
  $("log").scrollTop = $("log").scrollHeight;
}

function addCard(c, target) {
  if (c.kind === "login") return addLoginCard(c);
  if (c.kind === "open_dashboard") return addOpenTabCard(c);
  const t = CARD_TEXT[state.language || "English"];
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
    <button class="btn-discard">${escapeHtml(c.kind === "reschedule" ? t.keep : t.discard)}</button></div>`;
  if (target) {                 // dashboard ke andar (Reschedule picker ke neeche)
    target.appendChild(card);
  } else {
    row.appendChild(av); row.appendChild(card);
    $("log").appendChild(row);
    $("log").scrollTop = $("log").scrollHeight;
  }
  card.querySelector(".btn-confirm").onclick = () => act(c, card, "confirm");
  card.querySelector(".btn-discard").onclick = () => act(c, card, "discard");
}

async function act(c, card, which) {
  const t = CARD_TEXT[state.language || "English"];
  const buttons = card.querySelectorAll("button");
  buttons.forEach((b) => (b.disabled = true));
  const status = card.querySelector(".card-status");
  try {
    const r = c.dashboard   // dashboard ki arzi: login wala patient; chat ki arzi: is baat-cheet ki
      ? await fetch(`/api/me/reschedule-actions/${encodeURIComponent(c.action_id)}/${which}`, { method: "POST",
          headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fingerprint: c.fingerprint }) })
      : await fetch(`/api/actions/${which}`, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: state.userId, session_id: state.sessionId, action_id: c.action_id, fingerprint: c.fingerprint }) });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || r.status);
    const res = data.result;
    if (res.status === "in_progress") {           // HIS ka jawab nahin aaya: usi request_id se status jaanchein
      status.className = "card-status warn"; status.textContent = c.kind === "reschedule" ? t.changing : t.in_progress;
      const confirmBtn = card.querySelector(".btn-confirm");
      confirmBtn.textContent = t.retry; confirmBtn.disabled = false;
      card.querySelector(".btn-discard")?.remove();  // arzi HIS ko ja chuki; ab hatayi nahin ja sakti
      return;
    }
    const ok = ["booked", "cancelled", "registered", "already_registered", "discarded", "rescheduled",
                "reception_review"].includes(res.status);
    const ref = res.appointment_id || res.patient_id || "";
    const word = res.status === "discarded" && c.kind === "reschedule" ? t.kept : t[res.status];
    status.className = "card-status " + (ok ? (res.status === "discarded" ? "muted" : res.status === "reception_review" ? "warn" : "ok") : "bad");
    status.textContent = ok ? `${word}${ref ? " · " + ref : ""}` : (res.message || "Error");
    card.querySelector(".card-actions").remove();
    if (res.note && res.status === "booked") card.querySelector(".card-note").textContent = t.recovered;
    if (res.note && res.status === "rescheduled") card.querySelector(".card-note").textContent = t.recoveredChange;
    if (res.status === "rescheduled") card.querySelector(".card-note").insertAdjacentHTML("beforeend",
      ` <b>${escapeHtml(t.newAppt)}: ${escapeHtml(fmtDate(res.date))} · ${escapeHtml(fmtTime(res.time))}</b>`);
    if (res.stale && res.current) card.querySelector(".card-note").textContent =
      `${t.current}: ${fmtDate(res.current.date)} · ${fmtTime(res.current.time)}`;
    if (c.dashboard && ["rescheduled", "reception_review"].includes(res.status)) setTimeout(() => openDashboard("appointments"), 1500);
    if (res.alternatives && res.alternatives.length) {   // naya slot chhin gaya: purani chalu, naye vikalp
      const pick = document.createElement("div");
      pick.className = "card-pick";
      pick.innerHTML = `<div class="card-note">${escapeHtml(t.pickChange)}</div>`;
      const chips = document.createElement("div");
      chips.className = "card-actions";
      for (const o of res.alternatives.slice(0, 6)) {
        const b = document.createElement("button");
        b.className = "btn-discard"; b.textContent = `${o.weekday.slice(0, 3)} ${fmtTime(o.time)}`;
        b.onclick = () => { pick.remove();
          if (c.dashboard) previewReschedule(c.summary.appointment_id, o.slot_id, card.parentElement);
          else send(t.slotMsg(`${o.date} ${o.time}`)); };
        chips.appendChild(b);
      }
      pick.appendChild(chips); card.appendChild(pick);
    }
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
