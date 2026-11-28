// Page glue: Espace > Projet > Clip pickers, the list of maskedit projects of the clip, and the editor.
// All data goes through the backend (relative URLs, so it works under any path prefix).
import { createRoot } from 'react-dom/client'
import { useEffect, useRef, useState } from 'react'
import { MaskEditor } from './MaskEditor'
import { validate } from './core'
import type { MaskDoc } from './core'

interface Sp { id: string; name: string }
interface Pj { id: string; name: string }
interface Clip { id: string; name: string; duration: number; fps: number; width: number; height: number }
interface Mp { id: string; name: string; status: string; keyframes: number; updated: number | null }
interface Ctx { space: string; project: string; clip: string }

const JSON_H = { 'Content-Type': 'application/json' }
async function api<T = any>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init)
  const t = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(t.detail || r.statusText)
  return t as T
}
const post = (url: string, body: unknown, method = 'POST') => api(url, { method, headers: JSON_H, body: JSON.stringify(body) })
const q = (o: Record<string, string>) => new URLSearchParams(o).toString()
const loadSel = (): Record<string, any> => { try { return JSON.parse(localStorage.getItem('maskedit.sel') || '{}') } catch { return {} } }
// Last state is remembered in this browser (localStorage): space / project / clip / open maskedit project / current frame.
const BOOT = loadSel() // state as it was when the page opened
const saveSel = (patch: Record<string, unknown>) => { try { localStorage.setItem('maskedit.sel', JSON.stringify({ ...loadSel(), ...patch })) } catch { /* optional */ } }

function Editor({ ctx, mp, name, onClose }: { ctx: Ctx; mp: string; name: string; onClose: () => void }) {
  const [doc, setDoc] = useState<MaskDoc | null>(null)
  const [frame, setFrame] = useState(() => { return BOOT.open === mp && Number.isInteger(BOOT.frame) ? Math.max(0, BOOT.frame) : 0 })
  const [msg, setMsg] = useState('')
  const timer = useRef<number | undefined>(undefined)
  const revRef = useRef(0)
  const saving = useRef(false)
  const pending = useRef<MaskDoc | null>(null)
  const undo = useRef<MaskDoc[]>([])
  const redo = useRef<MaskDoc[]>([])
  const lastPush = useRef(0)
  const docRef = useRef<MaskDoc | null>(null)
  docRef.current = doc
  useEffect(() => { const id = window.setTimeout(() => saveSel({ open: mp, frame }), 400); return () => window.clearTimeout(id) }, [frame, mp])

  useEffect(() => {
    api<{ doc: MaskDoc; rev: number }>('api/doc?' + q({ ...ctx, mp })).then((r) => { revRef.current = r.rev; setDoc(r.doc); setFrame((f) => Math.min(f, Math.max(0, r.doc.frames - 1))) }).catch((e) => setMsg('erreur: ' + e.message))
  }, [])

  const flush = async () => {
    if (saving.current || !pending.current) return
    saving.current = true
    const d = pending.current
    pending.current = null
    try {
      const r = await post('api/doc', { ...ctx, mp, base_rev: revRef.current, doc: d }, 'PUT')
      revRef.current = r.rev
      setMsg('enregistré')
    } catch (e) {
      setMsg('erreur: ' + (e as Error).message)
    } finally {
      saving.current = false
      if (pending.current) flush()
    }
  }
  const save = (d: MaskDoc) => { pending.current = d; window.clearTimeout(timer.current); timer.current = window.setTimeout(flush, 400) }
  const flushNow = async () => {
    window.clearTimeout(timer.current)
    for (let i = 0; i < 100 && (pending.current || saving.current); i++) { await flush(); await new Promise((r) => setTimeout(r, 50)) }
  }

  // History: changes less than 700 ms apart (a drag) count as one undo step.
  const change = (d: MaskDoc) => {
    const cur = docRef.current
    const now = Date.now()
    if (cur && cur !== d && now - lastPush.current > 700) { undo.current.push(cur); if (undo.current.length > 200) undo.current.shift() }
    if (cur !== d) { lastPush.current = now; redo.current = [] }
    setDoc(d)
    save(d)
  }
  const goUndo = () => {
    const prev = undo.current.pop(), cur = docRef.current
    if (!prev || !cur) return
    redo.current.push(cur); lastPush.current = 0; setDoc(prev); save(prev)
  }
  const goRedo = () => {
    const next = redo.current.pop(), cur = docRef.current
    if (!next || !cur) return
    undo.current.push(cur); lastPush.current = 0; setDoc(next); save(next)
  }
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey
      if (!mod) return
      const k = e.key.toLowerCase()
      if (k === 'z' && !e.shiftKey) { e.preventDefault(); goUndo() }
      else if ((k === 'z' && e.shiftKey) || k === 'y') { e.preventDefault(); goRedo() }
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  })

  if (!doc) return <p>{msg || 'Chargement…'}</p>
  const exportMask = async () => {
    const errs = validate(doc)
    if (errs.length) { setMsg('erreur: ' + errs.join(', ')); return }
    await flushNow()
    setMsg('export en cours…')
    try {
      const r = await post('api/export', { ...ctx, mp })
      setMsg('ajouté au projet comme nouvel asset: ' + r.name)
    } catch (e) { setMsg('export refusé: ' + (e as Error).message) }
  }
  const frameUrl = (f: number) => `api/frame/${ctx.space}/${ctx.project}/${ctx.clip}/${f}.jpg`
  const packFetch = (k: number, w: number, pfps: number) => fetch(`api/pack/${ctx.space}/${ctx.project}/${ctx.clip}/${k}.bin?w=${w}&pfps=${pfps}`).then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.arrayBuffer() })
  return (
    <div>
      <div style={{ margin: '6px 0 8px', display: 'flex', gap: 10, alignItems: 'center' }}>
        <b>{name}</b>
        <button onClick={async () => { await flushNow(); await post('api/mproject-state', { ...ctx, mp, status: 'closed' }); onClose() }} style={{ padding: '4px 10px' }}>Fermer ce projet</button>
        <span style={{ fontSize: 12, opacity: 0.8 }}>{msg}</span>
      </div>
      <MaskEditor key={mp} doc={doc} onChange={change} frame={frame} onFrame={setFrame} frameUrl={frameUrl} packFetch={packFetch} />
      <div style={{ marginTop: 10, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        {doc.base_mask && (
          <label>mode <select value={doc.mode} onChange={(e) => { change({ ...doc, mode: e.target.value as MaskDoc['mode'] }); e.target.blur() }}>
            <option value="union">union avec le masque de base</option><option value="replace">polygone seul</option></select></label>
        )}
        <button onClick={goUndo} title="Annuler (Ctrl/Cmd+Z)" style={{ padding: '6px 12px' }}>↶ Annuler</button>
        <button onClick={goRedo} title="Rétablir (Ctrl/Cmd+Maj+Z)" style={{ padding: '6px 12px' }}>↷ Rétablir</button>
        <button onClick={exportMask} style={{ padding: '6px 12px' }}>Exporter le masque (nouvel asset du projet)</button>
      </div>
    </div>
  )
}

function Pick<T extends { id: string }>({ label, items, value, onPick, name }: { label: string; items: T[]; value: string; onPick: (id: string) => void; name: (t: T) => string }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', fontSize: 12, gap: 2, minWidth: 160, flex: 1 }}>{label}
      <select data-testid={'sel-' + label} value={value} onChange={(e) => { onPick(e.target.value); e.target.blur() }} style={{ padding: 4, fontSize: 14 }}>
        <option value="">—</option>
        {items.map((t) => <option key={t.id} value={t.id}>{name(t)}</option>)}
      </select>
    </label>
  )
}

function App() {
  const saved = useRef(loadSel())
  const [spaces, setSpaces] = useState<Sp[]>([])
  const [projects, setProjects] = useState<Pj[]>([])
  const [clips, setClips] = useState<Clip[]>([])
  const [mps, setMps] = useState<Mp[]>([])
  const [space, setSpace] = useState(saved.current.space || '')
  const [project, setProject] = useState(saved.current.project || '')
  const [clip, setClip] = useState(saved.current.clip || '')
  const [mpSel, setMpSel] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const [nameMode, setNameMode] = useState<null | 'new' | 'rename'>(null)
  const [nameVal, setNameVal] = useState('')
  const [err, setErr] = useState('')
  const fail = (e: unknown) => setErr((e as Error).message)

  useEffect(() => { saveSel({ space, project, clip }) }, [space, project, clip])
  useEffect(() => { saveSel({ open: open || '', mp: mpSel }) }, [open, mpSel])
  const restore = useRef<string>(String(saved.current.open || ''))
  useEffect(() => { api<Sp[]>('api/spaces').then((s) => { setSpaces(s); if (s.length === 1 && !space) setSpace(s[0].id) }).catch(fail) }, [])
  useEffect(() => {
    setProjects([]); setOpen(null)
    if (!space) return
    api<Pj[]>('api/projects?' + q({ space })).then((p) => { setProjects(p); if (!p.some((x) => x.id === project)) { setProject(''); setClip('') } }).catch(fail)
  }, [space])
  useEffect(() => {
    setClips([]); setOpen(null)
    if (!space || !project) return
    api<Clip[]>('api/clips?' + q({ space, project })).then((c) => { setClips(c); if (!c.some((x) => x.id === clip)) setClip('') }).catch(fail)
  }, [space, project])
  const reload = (keep?: string) => {
    if (!space || !project || !clip) { setMps([]); return }
    api<Mp[]>('api/mprojects?' + q({ space, project, clip })).then((m) => { setMps(m); setMpSel(keep && m.some((x) => x.id === keep) ? keep : m.some((x) => x.id === saved.current.mp) && !keep ? saved.current.mp : m[0]?.id || ''); if (!keep && restore.current && m.some((x) => x.id === restore.current)) { const id = restore.current; restore.current = ''; setMpSel(id); openMp(id) } }).catch(fail)
  }
  useEffect(() => { setOpen(null); reload() }, [space, project, clip])

  const ctx = { space, project, clip }
  const cur = mps.find((m) => m.id === mpSel)
  const openMp = async (id: string) => {
    setErr('')
    try { await post('api/mproject-state', { ...ctx, mp: id, status: 'open' }); setOpen(id) } catch (e) { fail(e) }
  }
  const submitName = async () => {
    const n = nameVal.trim()
    if (!n) return
    setErr('')
    try {
      if (nameMode === 'new') { const r = await post('api/mprojects', { ...ctx, name: n }); setNameMode(null); setNameVal(''); reload(r.id); setOpen(r.id) }
      else if (nameMode === 'rename' && cur) { await post('api/mproject-state', { ...ctx, mp: cur.id, name: n }); setNameMode(null); setNameVal(''); reload(cur.id) }
    } catch (e) { fail(e) }
  }
  const btn = { padding: '6px 12px' }
  return (
    <div style={{ fontFamily: 'system-ui', padding: 12, color: '#eee', background: '#111', minHeight: '100vh' }}>
      <h2 style={{ margin: '0 0 8px' }}>maskedit</h2>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', maxWidth: 1000 }}>
        <Pick label="Espace" items={spaces} value={space} onPick={(v) => { setSpace(v); setProject(''); setClip('') }} name={(s) => s.name} />
        <Pick label="Projet" items={projects} value={project} onPick={(v) => { setProject(v); setClip('') }} name={(p) => p.name} />
        <Pick label="Clip" items={clips} value={clip} onPick={setClip} name={(c) => `${c.name} (${c.duration.toFixed(1)} s, ${c.width}x${c.height})`} />
      </div>
      {err && <p style={{ color: '#f88' }}>{err}</p>}
      {clip && (
        <div style={{ margin: '10px 0', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', maxWidth: 1000 }}>
          <Pick label="Projets maskedit de ce clip" items={mps} value={mpSel} onPick={(v) => { setMpSel(v); setNameMode(null) }} name={(m) => `${m.name}${m.status === 'closed' ? ' (fermé)' : ''} — ${m.keyframes} clé${m.keyframes > 1 ? 's' : ''}`} />
          <button style={btn} disabled={!cur || open === cur.id} onClick={() => cur && openMp(cur.id)}>Ouvrir</button>
          <button style={btn} disabled={!cur} onClick={() => { setNameMode('rename'); setNameVal(cur?.name || '') }}>Renommer</button>
          <button style={btn} onClick={() => { setNameMode('new'); setNameVal('') }}>Nouveau</button>
          {nameMode && (
            <span style={{ display: 'flex', gap: 6 }}>
              <input autoFocus data-testid="name-input" value={nameVal} onChange={(e) => setNameVal(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') submitName(); if (e.key === 'Escape') setNameMode(null) }}
                placeholder={nameMode === 'new' ? 'Nom du nouveau projet' : 'Nouveau nom'} maxLength={80} style={{ padding: 5 }} />
              <button style={btn} onClick={submitName}>{nameMode === 'new' ? 'Créer' : 'OK'}</button>
              <button style={btn} onClick={() => setNameMode(null)}>Annuler</button>
            </span>
          )}
        </div>
      )}
      {open && <Editor key={open} ctx={ctx} mp={open} name={mps.find((m) => m.id === open)?.name || ''} onClose={() => { setOpen(null); reload(open) }} />}
      {!open && !clip && <p style={{ opacity: 0.7 }}>Choisis un espace, un projet et un clip.</p>}
    </div>
  )
}
createRoot(document.getElementById('root')!).render(<App />)
