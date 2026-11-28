// MaskEditor: SVG overlay on a video frame to draw/drag keyframed polygon points.
// UI only: no network, no storage. The host passes the document and a frame URL builder.
import { useEffect, useRef, useState } from 'react'
import { addKeyframe, addPoint, clamp01, keyAt, movePoint, nearestEdge, pointsAt, removeKeyframe, removePoint } from './core'
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
  const drag = useRef<{ index: number } | null>(null)
  const [playing, setPlaying] = useState(false)
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
    ;(e.target as Element).setPointerCapture(e.pointerId)
    drag.current = { index }
    onChange(ensureKey(doc))
  }
  const moveDrag = (e: React.PointerEvent) => {
    if (!drag.current) return
    onChange(movePoint(doc.keyframes.some((k) => k.frame === frame) ? doc : ensureKey(doc), frame, drag.current.index, toNorm(e)))
  }
  const endDrag = () => { setTimeout(() => { drag.current = null }, 0) }

  const prevKey = [...keys].reverse().find((k) => k < frame)
  const nextKey = keys.find((k) => k > frame)
  const btn = 'rounded border border-neutral-500 px-2 py-1 text-sm hover:bg-neutral-700 disabled:opacity-40'

  return (
    <div className="maskedit" style={{ maxWidth: 1000 }}>
      <div style={{ position: 'relative', width: '100%', aspectRatio: `${W} / ${H}`, background: '#000' }}>
        <img src={frameUrl(frame)} alt="" draggable={false} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} />
        <svg ref={svg} viewBox={`0 0 ${W} ${H}`} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', touchAction: 'none' }}
          onPointerDown={(e) => { if (playing) setPlaying(false); else onBackground(e) }} onPointerMove={moveDrag} onPointerUp={endDrag}>
          {pts.length > 0 && (
            <polygon points={pts.map((p) => `${p[0] * W},${p[1] * H}`).join(' ')}
              fill="rgba(255,160,0,0.35)" stroke={isKey ? '#ffd000' : '#ffffff'} strokeWidth={2} strokeDasharray={isKey ? undefined : '6 4'} />
          )}
          {!playing && pts.map((p, i) => (
            <circle key={i} cx={p[0] * W} cy={p[1] * H} r={4} fill={isKey ? '#ffd000' : '#ffffff'} fillOpacity={0.35} stroke={isKey ? '#ffd000' : '#ffffff'} strokeOpacity={0.6} strokeWidth={1}
              style={{ cursor: 'grab' }} onPointerDown={startDrag(i)}
              onDoubleClick={(e) => { e.stopPropagation(); if (pts.length > 3) onChange(removePoint(doc, i)) }} />
          ))}
          {draft.map((p, i) => <circle key={'d' + i} cx={p[0] * W} cy={p[1] * H} r={5} fill="#00e0ff" />)}
          {draft.length > 1 && <polyline points={draft.map((p) => `${p[0] * W},${p[1] * H}`).join(' ')} fill="none" stroke="#00e0ff" strokeWidth={2} />}
        </svg>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8, alignItems: 'center' }}>
        <button className={btn} style={{ minWidth: 80, fontWeight: 600 }} onClick={() => setPlaying(!playing)}>{playing ? '⏸ Pause' : '▶ Lecture'}</button>
        <button className={btn} onClick={() => { setPlaying(false); onFrame(Math.max(0, frame - 1)) }}>◀</button>
        <input type="range" min={0} max={doc.frames - 1} value={frame} onChange={(e) => onFrame(+e.target.value)} style={{ flex: 1, minWidth: 200 }} />
        <button className={btn} onClick={() => { setPlaying(false); onFrame(Math.min(doc.frames - 1, frame + 1)) }}>▶</button>
        <span style={{ minWidth: 90 }}>image {frame} / {doc.frames - 1}</span>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
        <button className={btn} disabled={prevKey === undefined} onClick={() => onFrame(prevKey!)}>◀ clé</button>
        <button className={btn} disabled={nextKey === undefined} onClick={() => onFrame(nextKey!)}>clé ▶</button>
        <button className={btn} disabled={isKey || !doc.keyframes.length} onClick={() => onChange(addKeyframe(doc, frame))}>+ clé ici</button>
        <button className={btn} disabled={!isKey} onClick={() => onChange(removeKeyframe(doc, frame))}>− clé</button>
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
