/* Shared UI helpers: navigation shell, toasts, formatting */
const NAV = [
  ["dashboard.html", "🏠", "Dashboard"],
  ["profile.html", "👤", "My Profile"],
  ["doctors.html", "🩺", "Doctors"],
  ["availability.html", "📅", "Doctor Availability"],
  ["book.html", "➕", "Book Appointment"],
  ["appointments.html", "📋", "Appointments"],
  ["consultations.html", "💬", "Consultations"],
  ["prescriptions.html", "💊", "Prescriptions"],
  ["lab-tests.html", "🧪", "Lab Tests"],
  ["billing.html", "🧾", "Billing & Payments"],
  ["history.html", "🧬", "Medical History"],
  ["notifications.html", "🔔", "Notifications"],
  ["patients.html", "🗂️", "Patient Directory"],
  ["settings.html", "⚙️", "Settings"],
  ["emergency.html", "🚨", "Emergency"],
];

function buildShell(activeFile) {
  const bar = document.createElement("div");
  bar.className = "topbar";
  bar.innerHTML = `
    <button class="menu-toggle" id="menuToggle" aria-label="Toggle menu">☰</button>
    <div class="brand"><span class="logo">M+</span> MediTrack</div>
    <div class="nav-search no-print">
      <input id="globalSearch" placeholder="Search doctors, appointments, prescriptions…">
    </div>
    <div class="spacer"></div>
    <a class="icon-btn no-print" href="notifications.html" title="Notifications">
      🔔<span class="badge-dot" id="notifDot" style="display:none"></span>
    </a>
    <div class="who-wrap no-print">
      <button class="who" id="whoami">Loading…</button>
      <div class="who-menu" id="whoMenu">
        <a href="profile.html">👤 My Profile</a>
        <a href="settings.html">⚙️ Settings</a>
        <a href="#" id="logoutBtn">🚪 Logout</a>
      </div>
    </div>`;
  document.body.prepend(bar);

  const side = document.getElementById("sidebar");
  if (side) {
    side.innerHTML = NAV.map(([href, icon, label]) =>
      `<a href="${href}" class="${href === activeFile ? "active" : ""}${label === "Emergency" ? " danger" : ""}">
         <span>${icon}</span>${label}</a>`).join("");
  }

  document.getElementById("menuToggle").onclick = () => side.classList.toggle("open");
  document.getElementById("whoami").onclick = () => document.getElementById("whoMenu").classList.toggle("open");
  document.addEventListener("click", (e) => {
    const wrap = document.querySelector(".who-wrap");
    if (wrap && !wrap.contains(e.target)) document.getElementById("whoMenu").classList.remove("open");
  });

  document.getElementById("logoutBtn").onclick = async (e) => {
    e.preventDefault();
    if (confirm("Logout of MediTrack?")) {
      try { await api.post("/auth/logout"); } catch (err) { /* ignore — token may already be stale */ }
      Session.clear();
      location.href = "login.html";
    }
  };

  const search = document.getElementById("globalSearch");
  if (search) {
    search.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && search.value.trim()) {
        location.href = `doctors.html?q=${encodeURIComponent(search.value.trim())}`;
      }
    });
  }

  if (Session.isAuthenticated()) {
    document.getElementById("whoami").innerHTML =
      `<strong>${esc(Session.patientName || "My Account")}</strong><br>${esc(Session.patientCode)} ▾`;
    api.get(`/patients/${Session.id}/notifications`).then(rows => {
      const unread = rows.filter(n => !n.is_read).length;
      const dot = document.getElementById("notifDot");
      if (dot && unread > 0) { dot.style.display = "inline-block"; dot.textContent = unread > 9 ? "9+" : unread; }
    }).catch(() => {});
  } else {
    document.getElementById("whoami").textContent = "Guest";
  }
}

function toast(msg, type = "ok") {
  let t = document.querySelector(".toast");
  if (!t) { t = document.createElement("div"); t.className = "toast"; document.body.appendChild(t); }
  t.textContent = msg;
  t.className = `toast show ${type}`;
  clearTimeout(t._t);
  t._t = setTimeout(() => (t.className = "toast"), 3200);
}

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const dash = (v) => (v === null || v === undefined || v === "" ? "—" : esc(v));
const fmtDate = (d) => d ? new Date(d + "T00:00:00").toLocaleDateString("en-IN",
  { day: "2-digit", month: "short", year: "numeric" }) : "—";
const statusBadge = (s) => `<span class="badge ${s === "Booked" ? "blue" : s === "Completed" ? "green" : s === "Cancelled" ? "red" : "grey"}">${s}</span>`;

function skeletonRows(n = 3) {
  return Array.from({ length: n }).map(() => `<div class="skel-row"></div>`).join("");
}

function errorState(msg, retryFn) {
  const box = document.createElement("div");
  box.className = "empty error-state";
  box.innerHTML = `<div>${esc(msg || "Unable to load your healthcare data. Please try again.")}</div>`;
  if (retryFn) {
    const btn = document.createElement("button");
    btn.className = "btn sm"; btn.textContent = "Retry"; btn.style.marginTop = "10px";
    btn.onclick = retryFn;
    box.appendChild(btn);
  }
  return box;
}

function guard() { return Session.require(); }

/* -------------------------------------------------------------------- */
/* MediTrack Voice Assistant — floating mic button, Web Speech API      */
/* (native browser API, no external key required) with a typed fallback */
/* -------------------------------------------------------------------- */
const VoiceAssistant = {
  recognition: null,
  listening: false,

  mount() {
    if (!Session.isAuthenticated() || document.getElementById("vaFab")) return;
    const fab = document.createElement("button");
    fab.id = "vaFab";
    fab.className = "va-fab no-print";
    fab.title = "MediTrack Voice Assistant";
    fab.innerHTML = "🎙️";
    fab.onclick = () => this.open();
    document.body.appendChild(fab);

    const panel = document.createElement("div");
    panel.id = "vaPanel";
    panel.className = "va-panel";
    panel.innerHTML = `
      <div class="va-head">
        <div><strong>MediTrack Assistant</strong><div class="va-sub">Ask about appointments, doctors, bills & more</div></div>
        <button class="va-close" id="vaClose">✕</button>
      </div>
      <div class="va-body">
        <div class="va-orb" id="vaOrb"><div class="va-wave"></div><span id="vaOrbIcon">🎙️</span></div>
        <div class="va-status" id="vaStatus">Tap the mic or type a command below</div>
        <div class="va-transcript" id="vaTranscript"></div>
        <div class="va-results" id="vaResults"></div>
      </div>
      <div class="va-input-row">
        <button class="va-mic" id="vaMicBtn">🎙️</button>
        <input id="vaTextInput" placeholder="Type a command… e.g. Show today's appointments">
        <button class="va-send" id="vaSendBtn">➤</button>
      </div>
      <div class="va-hints">Try: "Show appointments" · "Show doctors" · "Show billing" · "Search patient Ravi Kumar"</div>`;
    document.body.appendChild(panel);

    document.getElementById("vaClose").onclick = () => this.close();
    document.getElementById("vaMicBtn").onclick = () => this.toggleListening();
    document.getElementById("vaSendBtn").onclick = () => this.submitText();
    document.getElementById("vaTextInput").addEventListener("keydown", (e) => {
      if (e.key === "Enter") this.submitText();
    });

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SR) {
      this.recognition = new SR();
      this.recognition.continuous = false;
      this.recognition.interimResults = true;
      this.recognition.lang = "en-IN";
      this.recognition.onresult = (e) => {
        const text = Array.from(e.results).map(r => r[0].transcript).join("");
        document.getElementById("vaTranscript").textContent = text;
        if (e.results[0].isFinal) this.handleCommand(text);
      };
      this.recognition.onerror = () => this.setListening(false);
      this.recognition.onend = () => this.setListening(false);
    }
  },

  open() { document.getElementById("vaPanel").classList.add("open"); },
  close() { document.getElementById("vaPanel").classList.remove("open"); this.stopListening(); },

  setListening(on) {
    this.listening = on;
    document.getElementById("vaOrb").classList.toggle("live", on);
    document.getElementById("vaMicBtn").classList.toggle("live", on);
    document.getElementById("vaStatus").textContent = on ? "Listening…" : "Tap the mic or type a command below";
  },

  toggleListening() {
    if (!this.recognition) {
      document.getElementById("vaStatus").textContent = "Microphone not supported in this browser — type a command instead.";
      document.getElementById("vaTextInput").focus();
      return;
    }
    if (this.listening) { this.stopListening(); return; }
    document.getElementById("vaTranscript").textContent = "";
    document.getElementById("vaResults").innerHTML = "";
    try { this.recognition.start(); this.setListening(true); } catch (e) {}
  },
  stopListening() { if (this.recognition && this.listening) { try { this.recognition.stop(); } catch (e) {} } this.setListening(false); },

  submitText() {
    const input = document.getElementById("vaTextInput");
    const text = input.value.trim();
    if (!text) return;
    document.getElementById("vaTranscript").textContent = text;
    input.value = "";
    this.handleCommand(text);
  },

  respond(msg) { document.getElementById("vaStatus").textContent = msg; },

  async handleCommand(raw) {
    const text = raw.toLowerCase().trim();
    const results = document.getElementById("vaResults");
    results.innerHTML = "";
    const go = (label, href) => { this.respond(label); setTimeout(() => location.href = href, 500); };

    if (/appointment/.test(text) && /(today|show|open|upcoming)/.test(text)) return go("Opening your appointments…", "appointments.html");
    if (/doctor/.test(text) && !/patient/.test(text)) return go("Opening the doctors directory…", "doctors.html");
    if (/(bill|billing|payment|invoice)/.test(text)) return go("Opening billing & payments…", "billing.html");
    if (/notification/.test(text)) return go("Opening notifications…", "notifications.html");
    if (/emergency/.test(text)) return go("Opening emergency care…", "emergency.html");
    if (/lab|report/.test(text)) return go("Opening lab tests…", "lab-tests.html");
    if (/prescription/.test(text)) return go("Opening prescriptions…", "prescriptions.html");
    if (/(medical history|records|history)/.test(text)) return go("Opening your medical history…", "history.html");
    if (/(book|schedule).*appointment/.test(text)) return go("Let's book an appointment…", "book.html");
    if (/dashboard|home/.test(text)) return go("Opening your dashboard…", "dashboard.html");

    const searchMatch = text.match(/(?:search|show|find)\s+patient\s+(.+)/) || text.match(/^patient\s+(.+)/);
    if (searchMatch) {
      const name = searchMatch[1].trim();
      this.respond(`Searching for "${name}"…`);
      try {
        const rows = await api.get(`/patients?q=${encodeURIComponent(name)}`);
        if (!rows.length) {
          results.innerHTML = `<div class="empty" style="padding:14px">No matching patients found for "${esc(name)}".</div>`;
          this.respond(`No results for "${name}".`);
        } else {
          this.respond(`Found ${rows.length} match${rows.length > 1 ? "es" : ""}:`);
          results.innerHTML = rows.slice(0, 5).map(p => `
            <div class="va-result-card">
              <div><strong>${esc(p.full_name)}</strong> <span class="muted">${esc(p.patient_code)}</span></div>
              <div class="muted">${p.age} yrs • ${esc(p.gender)} • ${esc(p.blood_group || "—")}</div>
              <div class="muted">📞 ${esc(p.phone)} · ✉️ ${esc(p.email)}</div>
            </div>`).join("");
        }
      } catch (e) { this.respond("Sorry, patient search failed. Please try again."); }
      return;
    }

    this.respond(`I heard "${raw}" — try "show appointments", "show billing", or "search patient <name>".`);
  },
};
document.addEventListener("DOMContentLoaded", () => VoiceAssistant.mount());

/* -------------------------------------------------------------------- */
/* Phone / browser push notifications (real Web Push, works when the    */
/* app is closed, as long as the browser & OS allow notifications)      */
/* -------------------------------------------------------------------- */
const PushNotifications = {
  supported() {
    return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  },
  urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = atob(base64);
    return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
  },
  async status() {
    if (!this.supported()) return "unsupported";
    if (Notification.permission === "denied") return "denied";
    try {
      const reg = await navigator.serviceWorker.getRegistration();
      const sub = reg ? await reg.pushManager.getSubscription() : null;
      return sub ? "enabled" : "disabled";
    } catch (e) { return "disabled"; }
  },
  async enable() {
    if (!this.supported()) throw new Error("Push notifications aren't supported in this browser.");
    const { enabled, public_key } = await api.get("/push/vapid-public-key");
    if (!enabled) throw new Error("Phone notifications aren't configured on the server yet.");
    const permission = await Notification.requestPermission();
    if (permission !== "granted") throw new Error("Notification permission was not granted.");
    const reg = await navigator.serviceWorker.register("sw.js");
    await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: this.urlBase64ToUint8Array(public_key),
    });
    const json = sub.toJSON();
    await api.post("/push/subscribe", { endpoint: json.endpoint, p256dh: json.keys.p256dh, auth: json.keys.auth });
    return true;
  },
  async disable() {
    const reg = await navigator.serviceWorker.getRegistration();
    const sub = reg ? await reg.pushManager.getSubscription() : null;
    if (sub) {
      await api.post("/push/unsubscribe", { endpoint: sub.endpoint });
      await sub.unsubscribe();
    }
  },
};
