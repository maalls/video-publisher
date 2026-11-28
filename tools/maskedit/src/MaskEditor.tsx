// MaskEditor: SVG overlay on a video frame to draw/drag keyframed polygon points.
// UI only: no network, no storage. The host passes the document and a frame URL builder.
import { useEffect, useRef, useState } from 'react'
import { translateKey, addKeyframe, addPoint, clamp01, keyAt, movePoint, nearestEdge, pointsAt, removeKeyframe, removePoint } from './core'
import type { MaskDoc, Pt } from './core'

interface Props {
  doc: MaskDoc
  onChange: (doc: MaskDoc) => void
  frame: number
  onFrame: (frame: number) => void
  frameUrl: (frame: number) => string
}

export function MaskEditor({ doc, onChange, frame, onFrame, frameUrl }: Props) {
  const [W, H] = doc.size
  const svg = useRef<SVGSVGElement>(null)
  const [draft, setDraft] = useState<Pt[]>([])
  const drag = useRef<{ index: number; shape?: { start: Pt; base: Pt[] } } | null>(null)
  const click = useRef<{ x: number; y: number } | null>(null)
  const press = useRef<{ x: number; y: number; timer: number } | null>(null)
  const [playing, setPlaying] = useState(false)
  const [grab, setGrab] = useState(false)
  const [sel, setSel] = useState<number | null>(null)
  const cache = useRef<HTMLImageElement[]>([])
  const frameRef = useRef(frame)
  frameRef.current = frame
  // Preload all frames once so playback is smooth.
  useEffect(() => {
    cache.current = Array.from({ length: doc.frames }, (_, i) => { const im = new Image(); im.src = frameUrl(i); return im })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc.frames, doc.clip])
  // Live preview: play at the clip fps, looping, with the interpolated polygon drawn on each frame.
  useEffect(() => {
    if (!playing) return
    const id = window.setInterval(() => onFrame((frameRef.current + 1) % doc.frames), 1000 / (doc.fps || 16))
    return () => window.clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, doc.frames, doc.fps])
  const pts = pointsAt(doc, frame)
  // Left / Right arrows: previous / next frame. Holding repeats at a steady rhythm (first repeat after
  // 300 ms, then every 70 ms) instead of the OS key-repeat. Ignored while typing; pauses playback.
  const stepRef = useRef<(d: number) => void>(() => {})
  stepRef.current = (d) => {
    setPlaying(false)
    const n = Math.min(doc.frames - 1, Math.max(0, frameRef.current + d))
    frameRef.current = n
    onFrame(n)
  }
  useEffect(() => {
    let delay: number | undefined
    let rep: number | undefined
    let held: string | null = null
    const stop = () => { window.clearTimeout(delay); window.clearInterval(rep); held = null }
    const down = (e: KeyboardEvent) => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
      if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return
      const t = e.target as HTMLElement | null
      const tag = t?.tagName
      const typing = tag === 'TEXTAREA' || tag === 'SELECT' || !!t?.isContentEditable ||
        (tag === 'INPUT' && !['range', 'button', 'checkbox'].includes((t as HTMLInputElement).type))
      if (typing) return
      e.preventDefault() // also stops the focused slider from stepping a second time
      if (e.repeat || held === e.key) return
      stop()
      held = e.key
      const d = e.key === 'ArrowLeft' ? -1 : 1
      stepRef.current(d)
      delay = window.setTimeout(() => { rep = window.setInterval(() => stepRef.current(d), 70) }, 300)
    }
    const up = (e: KeyboardEvent) => { if (e.key === held) stop() }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', stop)
    return () => { stop(); window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); window.removeEventListener('blur', stop) }
  }, [])
  // Delete / Backspace removes the current key frame (never while typing in a text field).
  const delRef = useRef<() => void>(() => {})
  delRef.current = () => {
    if (playing) return
    // A selected point wins: Delete removes it on every key (same as double-click). Otherwise the current key.
    if (sel !== null && sel < pts.length) {
      if (pts.length > 3) { onChange(removePoint(doc, sel)); setSel(null) }
      return
    }
    if (keyAt(doc, frame)) onChange(removeKeyframe(doc, frame))
  }
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key !== 'Delete' && e.key !== 'Backspace') return
      if (e.ctrlKey || e.metaKey || e.altKey) return
      const t = e.target as HTMLElement | null
      const tag = t?.tagName
      const typing = tag === 'TEXTAREA' || tag === 'SELECT' || !!t?.isContentEditable ||
        (tag === 'INPUT' && !['range', 'button', 'checkbox'].includes((t as HTMLInputElement).type))
      if (typing) return
      e.preventDefault()
      delRef.current()
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])
  const isKey = !!keyAt(doc, frame)
  const keys = doc.keyframes.map((k) => k.frame)

  const toNorm = (e: { clientX: number; clientY: number }): Pt => {
    const r = svg.current!.getBoundingClientRect()
    return [clamp01((e.clientX - r.left) / r.width), clamp01((e.clientY - r.top) / r.height)]
  }
  const ensureKey = (d: MaskDoc) => (keyAt(d, frame) ? d : addKeyframe(d, frame))

  const onBackground = (e: React.PointerEvent) => {
    if (drag.current) return
    const p = toNorm(e)
    if (!doc.keyframes.length) { setDraft([...draft, p]); return }
    const { index, dist } = nearestEdge(pts, p)
    if (dist < 0.03) onChange(addPoint(ensureKey(doc), frame, index, p))
  }
  const closeDraft = () => {
    if (draft.length < 3) return
    onChange(addKeyframe(doc, frame, draft))
    setDraft([])
  }
  const startDrag = (index: number) => (e: React.PointerEvent) => {
    e.stopPropagation()
    setSel(index)
    ;(e.target as Element).setPointerCapture(e.pointerId)
    drag.current = { index }
    onChange(ensureKey(doc))
  }
  const cancelPress = () => { if (press.current) { window.clearTimeout(press.current.timer); press.current = null } }
  // Long press (400 ms, without moving) inside the polygon, then drag: moves the whole shape on this key.
  const polyDown = (e: React.PointerEvent) => {
    if (playing || !pts.length) return
    cancelPress()
    const start = toNorm(e)
    const base = pts.map((p): Pt => [p[0], p[1]])
    const target = svg.current!
    const pid = e.pointerId
    press.current = {
      x: e.clientX, y: e.clientY,
      timer: window.setTimeout(() => {
        press.current = null
        click.current = null
        try { target.setPointerCapture(pid) } catch { /* pointer already gone */ }
        drag.current = { index: -1, shape: { start, base } }
        setGrab(true)
        onChange(ensureKey(doc))
      }, 400),
    }
  }
  const moveDrag = (e: React.PointerEvent) => {
    if (press.current && Math.hypot(e.clientX - press.current.x, e.clientY - press.current.y) > 6) cancelPress()
    if (click.current && Math.hypot(e.clientX - click.current.x, e.clientY - click.current.y) > 6) click.current = null
    if (!drag.current) return
    const sh = drag.current.shape
    if (sh) {
      const p = toNorm(e)
      const d = doc.keyframes.some((k) => k.frame === frame) ? doc : ensureKey(doc)
      onChange(translateKey(d, frame, sh.base, p[0] - sh.start[0], p[1] - sh.start[1]))
      return
    }
    onChange(movePoint(doc.keyframes.some((k) => k.frame === frame) ? doc : ensureKey(doc), frame, drag.current.index, toNorm(e)))
  }
  const endDrag = (e: React.PointerEvent) => {
    const c = click.current
    click.current = null
    cancelPress()
    setGrab(false)
    // A short click (no long press, no drag) near an edge adds a point.
    if (c && !drag.current && e.type === 'pointerup') onBackground(e)
    setTimeout(() => { drag.current = null }, 0)
  }

  const prevKey = [...keys].reverse().find((k) => k < frame)
  const nextKey = keys.find((k) => k > frame)
  const btn = 'rounded border border-neutral-500 px-2 py-1 text-sm hover:bg-neutral-700 disabled:opacity-40'

  return (
    <div className="maskedit" style={{ maxWidth: 1000 }}>
      <div style={{ position: 'relative', width: '100%', aspectRatio: `${W} / ${H}`, background: '#000' }}>
        <img src={frameUrl(frame)} alt="" draggable={false} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} />
        <svg ref={svg} viewBox={`0 0 ${W} ${H}`} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', touchAction: 'none', userSelect: 'none', WebkitUserSelect: 'none', WebkitTouchCallout: 'none' } as React.CSSProperties} onContextMenu={(e) => e.preventDefault()}
          onPointerDown={(e) => { setSel(null); if (playing) setPlaying(false); else if (!doc.keyframes.length) onBackground(e); else click.current = { x: e.clientX, y: e.clientY } }} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag}>
          {pts.length > 0 && (
            <polygon onPointerDown={polyDown} style={{ cursor: grab ? 'grabbing' : undefined }} points={pts.map((p) => `${p[0] * W},${p[1] * H}`).join(' ')}
              fill="rgba(255,160,0,0.35)" stroke={isKey ? '#ffd000' : '#ffffff'} strokeWidth={2} strokeDasharray={isKey ? undefined : '6 4'} />
          )}
          {!playing && pts.map((p, i) => (
            <circle key={i} data-selected={sel === i ? '1' : undefined} cx={p[0] * W} cy={p[1] * H} r={4}
              fill={isKey ? '#ffd000' : '#ffffff'} fillOpacity={sel === i ? 0.1 : 0.35}
              stroke={isKey ? '#ffd000' : '#ffffff'} strokeOpacity={sel === i ? 0.85 : 0.6} strokeWidth={sel === i ? 2.5 : 1}
              style={{ cursor: 'grab' }} onPointerDown={startDrag(i)}
              onDoubleClick={(e) => { e.stopPropagation(); if (pts.length > 3) { onChange(removePoint(doc, i)); setSel(null) } }} />
          ))}
          {draft.map((p, i) => <circle key={'d' + i} cx={p[0] * W} cy={p[1] * H} r={5} fill="#00e0ff" />)}
          {draft.length > 1 && <polyline points={draft.map((p) => `${p[0] * W},${p[1] * H}`).join(' ')} fill="none" stroke="#00e0ff" strokeWidth={2} />}
        </svg>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8, alignItems: 'center' }}>
        <button className={btn} title="Aller au début" onClick={() => { setPlaying(false); onFrame(0) }}>|◀</button>
        <button className={btn} title="Image précédente" onClick={() => { setPlaying(false); onFrame(Math.max(0, frame - 1)) }}>◀</button>
        <button className={btn} style={{ minWidth: 80, fontWeight: 600 }} onClick={() => setPlaying(!playing)}>{playing ? '⏸ Pause' : '▶ Lecture'}</button>
        <button className={btn} title="Image suivante" onClick={() => { setPlaying(false); onFrame(Math.min(doc.frames - 1, frame + 1)) }}>▶</button>
        <button className={btn} title="Aller à la fin" onClick={() => { setPlaying(false); onFrame(doc.frames - 1) }}>▶|</button>
        <div style={{ position: 'relative', flex: 1, minWidth: 200, paddingTop: 14 }}>
          {keys.map((k) => (
            <button key={k} title={`clé ${k}`} className="maskedit-key" onClick={() => { setPlaying(false); onFrame(k) }}
              style={{ position: 'absolute', top: 0, width: 9, height: 9, padding: 0, border: '1px solid #ffd000', borderRadius: 2, cursor: 'pointer',
                left: `calc(8px + (100% - 16px) * ${doc.frames > 1 ? k / (doc.frames - 1) : 0} - 4.5px)`,
                background: k === frame ? 'rgba(255,208,0,0.95)' : 'rgba(255,208,0,0.4)' }} />
          ))}
          <input type="range" min={0} max={doc.frames - 1} value={frame} onChange={(e) => onFrame(+e.target.value)} style={{ width: '100%', margin: 0, display: 'block' }} />
        </div>
        <span style={{ width: '13ch', textAlign: 'right', fontSize: 12, fontVariantNumeric: 'tabular-nums', opacity: 0.85 }}>image {frame} / {doc.frames - 1}</span>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
        <button className={btn} disabled={prevKey === undefined} onClick={() => onFrame(prevKey!)}>◀ clé</button>
        <button className={btn} disabled={nextKey === undefined} onClick={() => onFrame(nextKey!)}>clé ▶</button>
        <button className={btn} disabled={isKey || !doc.keyframes.length} onClick={() => onChange(addKeyframe(doc, frame))}>+ clé ici</button>
        {isKey && <button className={btn} title="Supprimer cette image clé (Suppr / Retour arrière)" onClick={() => onChange(removeKeyframe(doc, frame))}>Supprimer</button>}
        {!doc.keyframes.length && <button className={btn} disabled={draft.length < 3} onClick={closeDraft}>Fermer le polygone ({draft.length} pts)</button>}
        {!doc.keyframes.length && draft.length > 0 && <button className={btn} onClick={() => setDraft([])}>Effacer</button>}
      </div>
      <div style={{ marginTop: 6, fontSize: 13 }}>
        Clés: {keys.length ? keys.map((k) => (
          <button key={k} className={btn} style={{ marginRight: 4, background: k === frame ? '#553' : undefined }} onClick={() => onFrame(k)}>{k}</button>
        )) : 'aucune (cliquez sur l’image pour poser les points, puis « Fermer le polygone »)'}
      </div>
      <p style={{ fontSize: 12, opacity: 0.7 }}>Glisser un point pour le déplacer (sur une image sans clé, ça crée la clé). Cliquer sur un bord pour ajouter un point. Double-clic sur un point pour le supprimer (sur toutes les clés).</p>
    </div>
  )
}
