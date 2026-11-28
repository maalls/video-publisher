// Page glue: loads/saves the document through the small backend and wires MaskEditor to it.
import { createRoot } from 'react-dom/client'
import { useEffect, useRef, useState } from 'react'
import { MaskEditor } from './MaskEditor'
import { validate } from './core'
import type { MaskDoc } from './core'

function App() {
  const [doc, setDoc] = useState<MaskDoc | null>(null)
  const [frame, setFrame] = useState(0)
  const [msg, setMsg] = useState('')
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => { fetch('api/doc').then((r) => r.json()).then(setDoc) }, [])
  const change = (d: MaskDoc) => {
    setDoc(d)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      fetch('api/doc', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) }).then(() => setMsg('enregistré'))
    }, 400)
  }
  if (!doc) return <p>Chargement…</p>
  const exportMask = async () => {
    const errs = validate(doc)
    if (errs.length) { setMsg('erreur: ' + errs.join(', ')); return }
    setMsg('export en cours…')
    const r = await fetch('api/export', { method: 'POST' })
    setMsg(r.ok ? 'exporté: ' + (await r.json()).file : 'export refusé')
  }
  return (
    <div style={{ fontFamily: 'system-ui', padding: 12, color: '#eee', background: '#111', minHeight: '100vh' }}>
      <h2 style={{ margin: '0 0 8px' }}>maskedit <small style={{ opacity: 0.6 }}>prototype — {doc.clip}</small></h2>
      <MaskEditor doc={doc} onChange={change} frame={frame} onFrame={setFrame} frameUrl={(f) => `frame/${f}.jpg`} />
      <div style={{ marginTop: 10, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <label>mode <select value={doc.mode} onChange={(e) => change({ ...doc, mode: e.target.value as MaskDoc['mode'] })}>
          <option value="union">union avec le masque de base</option><option value="replace">polygone seul</option></select></label>
        <button onClick={exportMask} style={{ padding: '6px 12px' }}>Exporter le masque (mp4 noir/blanc)</button>
        <span>{msg}</span>
      </div>
    </div>
  )
}
createRoot(document.getElementById('root')!).render(<App />)
