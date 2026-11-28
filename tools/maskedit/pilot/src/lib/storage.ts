// Last state, remembered in this browser (own key: independent from the current /lab/maskedit page).
const KEY = "maskedit.ui.sel"
export const loadSel = (): Record<string, any> => {
  try { return JSON.parse(localStorage.getItem(KEY) || "{}") } catch { return {} }
}
export const saveSel = (patch: Record<string, unknown>) => {
  try { localStorage.setItem(KEY, JSON.stringify({ ...loadSel(), ...patch })) } catch { /* optional */ }
}
export const BOOT = loadSel() // state as it was when the page opened
