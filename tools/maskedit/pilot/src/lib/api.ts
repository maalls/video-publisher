// Backend access. The page lives at <prefix>/ui/, the API at <prefix>/api/, hence the "../".
const BASE = "../"
const JSON_H = { "Content-Type": "application/json" }

export async function api<T = any>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + url, init)
  const t = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(t.detail || r.statusText)
  return t as T
}
export const post = (url: string, body: unknown, method = "POST") =>
  api(url, { method, headers: JSON_H, body: JSON.stringify(body) })
export const query = (o: Record<string, string>) => new URLSearchParams(o).toString()

export interface Ctx { space: string; project: string; clip: string }
export interface Named { id: string; name: string }
export interface Clip extends Named { duration: number; fps: number; width: number; height: number }
export interface MaskProject extends Named { status: string; keyframes: number; updated: number | null }

export const frameUrl = (c: Ctx, f: number) => BASE + `api/frame/${c.space}/${c.project}/${c.clip}/${f}.jpg`
export const packFetch = (c: Ctx, k: number, w: number, pfps: number) =>
  fetch(BASE + `api/pack/${c.space}/${c.project}/${c.clip}/${k}.bin?w=${w}&pfps=${pfps}`).then((r) => {
    if (!r.ok) throw new Error(String(r.status))
    return r.arrayBuffer()
  })
