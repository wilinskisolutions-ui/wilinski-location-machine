// Where a visitor's map lives. Two backends behind one interface:
//
//   LocalStore   this browser only — the wizard's draft, and anyone who has not signed up
//   RemoteStore  Supabase — a signed-in household (one person or a couple), shared live
//
// What is stored: the settings object (weights, cap, climate preset, layer opt-ins), the
// pinned areas, and per-town status and notes. Never a label for a sensitive answer —
// only the weight and direction the visitor chose.
import { lsDel, lsGet, lsSet } from "./util.js";

const KEY = "atlas.v1";

export class LocalStore {
  kind = "local";

  load() {
    const d = lsGet(KEY) || {};
    return {
      settings: d.settings || null,
      pins: Array.isArray(d.pins) ? d.pins : [],
      towns: d.towns && typeof d.towns === "object" ? d.towns : {},
    };
  }
  _write(patch) {
    return lsSet(KEY, { ...this.load(), ...patch });
  }
  async saveSettings(settings) { this._write({ settings }); }
  async savePin(pin) {
    const pins = this.load().pins.filter((p) => p.id !== pin.id).concat([pin]);
    this._write({ pins });
  }
  async removePin(id) { this._write({ pins: this.load().pins.filter((p) => p.id !== id) }); }
  async saveTown(id, rec) {
    const towns = { ...this.load().towns };
    if (!rec.status && !rec.note) delete towns[id];
    else towns[id] = rec;
    this._write({ towns });
  }
  subscribe() { return () => {}; }
  clear() { lsDel(KEY); }
  get label() { return "Saved on this device only"; }
}

export class RemoteStore {
  kind = "remote";

  constructor(sb, householdId) {
    this.sb = sb;
    this.hid = householdId;
  }

  async load() {
    const [s, p, t] = await Promise.all([
      this.sb.from("household_settings").select("settings").eq("household_id", this.hid).maybeSingle(),
      this.sb.from("pins").select("id,label,anchor,radius_mi,sort").eq("household_id", this.hid),
      this.sb.from("town_notes").select("place_geoid,status,note").eq("household_id", this.hid),
    ]);
    for (const r of [s, p, t]) if (r.error) throw r.error;
    return {
      settings: s.data ? s.data.settings : null,
      pins: (p.data || []).map((r) => ({ id: r.id, label: r.label, anchor: r.anchor, radius_mi: r.radius_mi, order: r.sort })),
      towns: Object.fromEntries((t.data || []).map((r) => [r.place_geoid, { status: r.status, note: r.note }])),
    };
  }
  async saveSettings(settings) {
    const { error } = await this.sb.from("household_settings")
      .upsert({ household_id: this.hid, settings }, { onConflict: "household_id" });
    if (error) throw error;
  }
  async savePin(pin) {
    const { error } = await this.sb.from("pins").upsert({
      household_id: this.hid, id: pin.id, label: pin.label, anchor: pin.anchor,
      radius_mi: pin.radius_mi, sort: pin.order ?? 0,
    }, { onConflict: "household_id,id" });
    if (error) throw error;
  }
  async removePin(id) {
    const { error } = await this.sb.from("pins").delete().eq("household_id", this.hid).eq("id", id);
    if (error) throw error;
  }
  async saveTown(id, rec) {
    const q = !rec.status && !rec.note
      ? this.sb.from("town_notes").delete().eq("household_id", this.hid).eq("place_geoid", id)
      : this.sb.from("town_notes").upsert({
        household_id: this.hid, place_geoid: id, status: rec.status || null, note: String(rec.note || "").slice(0, 4000),
      }, { onConflict: "household_id,place_geoid" });
    const { error } = await q;
    if (error) throw error;
  }

  // Live updates for couples on two phones. Needs the tables in the supabase_realtime
  // publication (the migration adds them); without it the map still works, and reloads.
  subscribe(onChange) {
    const ch = this.sb.channel(`household-${this.hid}`);
    for (const table of ["household_settings", "pins", "town_notes"]) {
      ch.on("postgres_changes", { event: "*", schema: "public", table, filter: `household_id=eq.${this.hid}` },
        () => onChange(table));
    }
    ch.subscribe();
    return () => this.sb.removeChannel(ch);
  }

  // Copy a draft made before sign-up into the new household.
  async importDraft(draft) {
    if (draft.settings) await this.saveSettings(draft.settings);
    for (const pin of draft.pins || []) await this.savePin(pin);
    for (const [id, rec] of Object.entries(draft.towns || {})) await this.saveTown(id, rec);
  }

  get label() { return "Saved to your account"; }
}
