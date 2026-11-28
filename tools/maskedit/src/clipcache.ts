// Whole-clip low-resolution cache for smooth playback. Frames arrive 16 per request (packs), in order from
// the playhead, and are kept as JPEG blobs in memory and in IndexedDB (so reopening a clip is instant).
export const PACK = 16
const DB = 'maskedit-frames'
const MAX_PACKS = 1500 // ~ 400 MB of low-res packs at most in IndexedDB

function openDb(): Promise<IDBDatabase | null> {
  return new Promise((res) => {
    try {
      const r = indexedDB.open(DB, 1)
      r.onupgradeneeded = () => { const s = r.result.createObjectStore('packs'); s.createIndex('t', 't') }
      r.onsuccess = () => res(r.result)
      r.onerror = () => res(null)
    } catch { res(null) }
  })
}
const dbp = openDb()
const idbGet = async (key: string): Promise<ArrayBuffer | null> => {
  const db = await dbp
  if (!db) return null
  return new Promise((res) => {
    const r = db.transaction('packs').objectStore('packs').get(key)
    r.onsuccess = () => res(r.result ? r.result.buf : null)
    r.onerror = () => res(null)
  })
}
const idbPut = async (key: string, buf: ArrayBuffer) => {
  const db = await dbp
  if (!db) return
  try {
    const tx = db.transaction('packs', 'readwrite')
    const st = tx.objectStore('packs')
    st.put({ buf, t: Date.now() }, key)
    const c = st.count()
    c.onsuccess = () => {
      let extra = c.result - MAX_PACKS
      if (extra <= 0) return
      st.index('t').openCursor().onsuccess = (e) => {
        const cur = (e.target as IDBRequest<IDBCursorWithValue | null>).result
        if (cur && extra-- > 0) { cur.delete(); cur.continue() }
      }
    }
  } catch { /* cache is optional */ }
}

export interface Stats { loaded: number; total: number; bytes: number; ms: number; fromDisk: number; done: boolean }

export class ClipCache {
  blobs = new Map<number, Blob>()
  private urls = new Map<number, string>()
  private packs = new Set<number>()
  private busy = new Set<number>()
  private dead = false
  private t0 = Date.now()
  stats: Stats
  constructor(private key: string, private frames: number, private fetchPack: (k: number) => Promise<ArrayBuffer>, private onChange: () => void) {
    this.stats = { loaded: 0, total: frames, bytes: 0, ms: 0, fromDisk: 0, done: false }
  }
  has(f: number) { return this.blobs.has(f) }
  url(f: number): string | null {
    const b = this.blobs.get(f)
    if (!b) return null
    let u = this.urls.get(f)
    if (!u) {
      u = URL.createObjectURL(b); this.urls.set(f, u)
      if (this.urls.size > 80) { // keep few object URLs alive; blobs stay cached
        for (const [k, v] of this.urls) { if (Math.abs(k - f) > 30) { URL.revokeObjectURL(v); this.urls.delete(k) } }
      }
    }
    return u
  }
  warm(f: number, n: number) { for (let i = 1; i <= n; i++) { const u = this.url((f + i) % this.frames); if (u) { const im = new Image(); im.src = u } } }
  stop() { this.dead = true; for (const v of this.urls.values()) URL.revokeObjectURL(v); this.urls.clear() }
  /** load missing packs, nearest to `from` first (wrapping), 2 requests in flight */
  pump(from: number) {
    if (this.dead) return
    const n = Math.ceil(this.frames / PACK)
    const cur = Math.floor(from / PACK)
    for (let d = 0; d < n && this.busy.size < 2; d++) {
      const k = (cur + d) % n
      if (this.packs.has(k) || this.busy.has(k)) continue
      this.busy.add(k)
      this.load(k).finally(() => { this.busy.delete(k); this.pump(from) })
    }
  }
  private async load(k: number) {
    let buf = await idbGet(`${this.key}|${k}`)
    const disk = !!buf
    try {
      if (!buf) { buf = await this.fetchPack(k); idbPut(`${this.key}|${k}`, buf) }
    } catch { await new Promise((r) => setTimeout(r, 1500)); return }
    if (this.dead) return
    const dv = new DataView(buf)
    const c = dv.getUint32(0, true)
    let off = 4 + 4 * c
    for (let i = 0; i < c; i++) {
      const len = dv.getUint32(4 + 4 * i, true)
      this.blobs.set(k * PACK + i, new Blob([buf.slice(off, off + len)], { type: 'image/jpeg' }))
      off += len
    }
    this.packs.add(k)
    this.stats = { loaded: this.blobs.size, total: this.frames, bytes: this.stats.bytes + buf.byteLength, ms: Date.now() - this.t0,
      fromDisk: this.stats.fromDisk + (disk ? c : 0), done: this.packs.size >= Math.ceil(this.frames / PACK) }
    this.onChange()
  }
}
