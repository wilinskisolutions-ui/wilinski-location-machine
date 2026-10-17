// Small helpers shared by every module. No DOM state lives here.

export const MI_PER_DEG = 69.05;

export const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Census names carry their legal class ("Franklin city", "Lake Ridge CDP"); people don't.
export const cleanName = (n) =>
  String(n)
    .replace(/ (metropolitan|metro|consolidated|unified) government \(balance\)$/i, "")
    .replace(/ \(balance\)$/, "")
    .replace(/ (city|town|village|borough|CDP|municipality|plantation)$/, "");

export function miles(lat1, lon1, lat2, lon2) {
  const r = Math.PI / 180, dLat = (lat2 - lat1) * r, dLon = (lon2 - lon1) * r;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dLon / 2) ** 2;
  return 2 * 3958.76 * Math.asin(Math.sqrt(a));
}

export function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

export const money = (v) => (v == null ? "—" : "$" + Math.round(v).toLocaleString("en-US"));
export const fitNum = (s) => (s ? Math.round(s.score * 100) : null);

// Browser storage can throw (private windows, blocked site data); a missing value is null.
export const lsGet = (k) => { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } };
export const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch { return false; } };
export const lsDel = (k) => { try { localStorage.removeItem(k); } catch { /* nothing to do */ } };
