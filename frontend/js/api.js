/* MediTrack – API layer (all data lives in the database via FastAPI) */
const API = (location.port === "5500" || location.port === "5173")
  ? "http://127.0.0.1:8000/api"      // separate static server
  : "/api";                          // served by FastAPI

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = Session.token;
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(API + path, {
    ...options,
    headers: { ...headers, ...(options.headers || {}) },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }

  if (res.status === 401) {
    // Token missing / invalid / expired -> clear session and bounce to login,
    // but only if we're not already on a public auth page.
    Session.clear();
    const publicPages = ["login.html", "signup.html", "forgot-password.html", "reset-password.html"];
    const here = location.pathname.split("/").pop() || "index.html";
    if (!publicPages.includes(here)) {
      location.href = "login.html?expired=1";
    }
  }

  if (!res.ok) {
    const msg = data && data.detail
      ? (typeof data.detail === "string" ? data.detail : data.detail[0]?.msg || "Validation error")
      : `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

const api = {
  get: (p) => request(p),
  post: (p, body) => request(p, { method: "POST", body }),
  put: (p, body) => request(p, { method: "PUT", body }),
  del: (p) => request(p, { method: "DELETE" }),
};

/* Authenticated session: JWT + cached patient info (patient data itself is
   always re-fetched from the database — only the token and light display
   fields are cached client-side). */
const Session = {
  get token() { return localStorage.getItem("mt_token"); },
  get id() { return localStorage.getItem("mt_patient_id"); },
  get patientName() { return localStorage.getItem("mt_patient_name") || ""; },
  get patientCode() { return localStorage.getItem("mt_patient_code") || ""; },

  set(token, patient) {
    localStorage.setItem("mt_token", token);
    localStorage.setItem("mt_patient_id", patient.id);
    localStorage.setItem("mt_patient_name", patient.full_name || "");
    localStorage.setItem("mt_patient_code", patient.patient_code || "");
  },
  clear() {
    localStorage.removeItem("mt_token");
    localStorage.removeItem("mt_patient_id");
    localStorage.removeItem("mt_patient_name");
    localStorage.removeItem("mt_patient_code");
  },
  isAuthenticated() { return !!(this.token && this.id); },
  require() {
    if (!this.isAuthenticated()) { location.href = "login.html"; throw new Error("no session"); }
    return this.id;
  },
};
