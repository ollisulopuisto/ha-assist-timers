// Extracted verbatim from eyalgal/simple-timer-card, src/simple-timer-card.js
// at commit db92d09b38b1d3bb6fc4d362d440ef895a6f14cc (2026-09-08), to test that
// sensor.assist_timers_alexa parses the way the real card parses it.
/*
MIT License

Copyright (c) 2025 Eyal Gal

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/
class SimpleTimerCardAlexa {
  _toMs(v) {
    if (v == null) return null;
    if (typeof v === "number") {
      if (v < 1000) return v * 1000;
      if (v > 1e12) return Math.max(0, v - Date.now());
      return v;
    }
    if (typeof v === "string") {
      const n = Number(v);
      if (!Number.isNaN(n)) return this._toMs(n);
      const m = /^P(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)$/i.exec(v.trim());
      if (m) {
        const h = parseInt(m[1] || "0", 10);
        const min = parseInt(m[2] || "0", 10);
        const s = parseInt(m[3] || "0", 10);
        return ((h * 3600) + (min * 60) + s) * 1000;
      }
    }
    return null;
  }

  _parseAlexa(entityId, entityState, entityConf) {
    const attrs = entityState.attributes;

    let active = attrs.sorted_active;
    let paused = attrs.sorted_paused;
    let all = attrs.sorted_all;

    if ((active == null && paused == null && all == null) && attrs.timers != null) {
      all = attrs.timers;
    }
    if (active == null && attrs.next_timer != null) {
      active = [attrs.next_timer];
    }

    const safeParse = (x) => {
      if (Array.isArray(x)) return x;
      if (typeof x === "string") { try { return JSON.parse(x); } catch { return []; } }
      return Array.isArray(x) ? x : [];
    };

    active = safeParse(active);
    paused = safeParse(paused);
    all = safeParse(all);

    if (active.length === 0 && paused.length === 0 && attrs.alarms_brief) {
      const brief = attrs.alarms_brief;
      const briefActive = Array.isArray(brief.active) ? brief.active : [];

      let anchorTime = Date.now();
      if (attrs.process_timestamp) {
        anchorTime = new Date(attrs.process_timestamp).getTime();
      } else if (entityState.last_updated) {
        anchorTime = new Date(entityState.last_updated).getTime();
      }

      return briefActive.map(t => {
        const isPaused = (t.status === "PAUSED");
        const remaining = t.remainingTime || 0;

        const validAnchor = (attrs.process_timestamp || entityState.last_updated)
          ? anchorTime
          : (t.lastUpdatedDate || Date.now());

        const end = isPaused ? remaining : (validAnchor + remaining);

        let totalDuration = t.originalDuration;

        if (!totalDuration) {
          if (isPaused) {
             totalDuration = remaining;
          } else {
             const startTime = t.lastUpdatedDate || validAnchor;
             const elapsed = Math.max(0, validAnchor - startTime);
             totalDuration = elapsed + remaining;
          }
        }

        let label;
        if (t.timerLabel) {
          label = this._sanitizeText(t.timerLabel);
        } else {
          const cleanedFriendlyName = this._cleanFriendlyName(attrs.friendly_name);
          const baseName = entityConf?.name || cleanedFriendlyName || (isPaused ? "Alexa Timer (Paused)" : "Alexa Timer");
          label = this._sanitizeText(baseName);
        }

        return {
          id: t.id,
          source: "alexa",
          source_entity: entityId,
          label,
          icon: entityConf?.icon || (isPaused ? "mdi:timer-pause" : "mdi:timer"),
          color: entityConf?.color || (isPaused ? "var(--warning-color)" : "var(--primary-color)"),
          end: end,
          duration: totalDuration,
          paused: isPaused,
        };
      });
    }

    const normDuration = (t) =>
      (typeof t?.originalDurationInMillis === "number" && t.originalDurationInMillis) ||
      (typeof t?.originalDurationInSeconds === "number" && t.originalDurationInSeconds * 1000) ||
      this._toMs(t?.originalDuration) || null;

    const mk = (id, t, pausedFlag) => {
      const remainingMs = pausedFlag ? this._toMs(t?.remainingTime) : null;
      const end = pausedFlag ? (remainingMs ?? 0) : Number(t?.triggerTime || 0);
      let label;
      if (t?.timerLabel) {
        label = this._sanitizeText(t.timerLabel);
      } else {
        const cleanedFriendlyName = this._cleanFriendlyName(entityState.attributes.friendly_name);
        const baseName = entityConf?.name || cleanedFriendlyName || (pausedFlag ? "Alexa Timer (Paused)" : "Alexa Timer");
        const originalDuration = normDuration(t);
        const displayTime = originalDuration > 0 ? this._formatDurationDisplay(originalDuration) : "0m";
        if (baseName && baseName !== "Alexa Timer" && baseName !== "Alexa Timer (Paused)") {
          label = this._sanitizeText(`${baseName} - ${displayTime}`);
        } else {
          label = this._sanitizeText(baseName);
        }
      }
      const hasCustomIcon = !!entityConf?.icon;
      const hasCustomColor = !!entityConf?.color;
      return {
        id,
        source: "alexa",
        source_entity: entityId,
        label,
        icon: hasCustomIcon ? entityConf.icon : (pausedFlag ? "mdi:timer-pause" : "mdi:timer"),
        color: hasCustomColor ? entityConf.color : (pausedFlag ? "var(--warning-color)" : "var(--primary-color)"),
        end,
        duration: normDuration(t),
        paused: !!pausedFlag,
      };
    };

    const mapTimerList = (list, isPaused) => {
      if (!Array.isArray(list)) return [];
      return list.map(item => {
        let id, t;
        if (Array.isArray(item)) { [id, t] = item; }
        else { t = item; id = t.id; }
        return mk(id, t, isPaused);
      });
    };

    const activeTimers = mapTimerList(active, false);
    let pausedTimers = mapTimerList(paused, true);

    if (pausedTimers.length === 0 && all.length > 0) {
      pausedTimers = mapTimerList(all, true).filter(pt => pt && String(pt.status).toUpperCase() === "PAUSED");
    }
    return [...activeTimers, ...pausedTimers];
  }
}
module.exports = { SimpleTimerCardAlexa };
