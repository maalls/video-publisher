// maskedit core: pure TypeScript, no dependency, no DOM.
// A mask document is a polygon described by ordered points on keyframes.
// Coordinates are normalised (0..1) like YABBE's RotoPrompt, so it can be
// plugged into an editor later. Interpolation is linear, point by point.

export type Pt = [number, number]
export interface Keyframe { frame: number; points: Pt[] }
export interface MaskDoc {
  version: 1
  clip: string
  fps: number
  size: [number, number] // width, height in pixels
  frames: number
  keyframes: Keyframe[] // sorted by frame, all with the same number of points
  mode: 'union' | 'replace'
  base_mask: string | null // optional existing mask (file name) merged in 'union' mode
}

export function newDoc(clip: string, fps: number, size: [number, number], frames: number): MaskDoc {
  return { version: 1, clip, fps, size, frames, keyframes: [], mode: 'union', base_mask: null }
}

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v))
const sorted = (k: Keyframe[]) => [...k].sort((a, b) => a.frame - b.frame)
export const clamp01 = (v: number) => Math.min(1, Math.max(0, v))

export function keyAt(doc: MaskDoc, frame: number): Keyframe | undefined {
  return doc.keyframes.find((k) => k.frame === frame)
}

/** Points of the polygon at a frame (interpolated; held before the first and after the last key). */
export function pointsAt(doc: MaskDoc, frame: number): Pt[] {
  const ks = sorted(doc.keyframes)
  if (!ks.length) return []
  if (frame <= ks[0].frame) return clone(ks[0].points)
  const last = ks[ks.length - 1]
  if (frame >= last.frame) return clone(last.points)
  let a = ks[0]
  let b = ks[1]
  for (let i = 0; i < ks.length - 1; i++) {
    if (frame >= ks[i].frame && frame <= ks[i + 1].frame) { a = ks[i]; b = ks[i + 1]; break }
  }
  const t = (frame - a.frame) / (b.frame - a.frame)
  return a.points.map((p, i): Pt => [p[0] + (b.points[i][0] - p[0]) * t, p[1] + (b.points[i][1] - p[1]) * t])
}

export const polygonAt = pointsAt

/** Add a keyframe at `frame`, starting from the current interpolated shape (or `seed` when the doc is empty). */
export function addKeyframe(doc: MaskDoc, frame: number, seed?: Pt[]): MaskDoc {
  if (keyAt(doc, frame)) return doc
  const pts = doc.keyframes.length ? pointsAt(doc, frame) : clone(seed ?? [])
  return { ...doc, keyframes: sorted([...doc.keyframes, { frame, points: pts }]) }
}

export function removeKeyframe(doc: MaskDoc, frame: number): MaskDoc {
  return { ...doc, keyframes: doc.keyframes.filter((k) => k.frame !== frame) }
}

/** Move one point on the keyframe at `frame` (the key must exist; use addKeyframe first). */
export function movePoint(doc: MaskDoc, frame: number, index: number, p: Pt): MaskDoc {
  return {
    ...doc,
    keyframes: doc.keyframes.map((k) =>
      k.frame !== frame ? k : { ...k, points: k.points.map((q, i): Pt => (i === index ? [clamp01(p[0]), clamp01(p[1])] : q)) }),
  }
}

/** Insert a point at `index` (0..n) on every keyframe: the edited key gets `p`, the others get the same
 *  point projected on the edge it splits, so the shape of other keys does not change. */
export function addPoint(doc: MaskDoc, frame: number, index: number, p: Pt): MaskDoc {
  return {
    ...doc,
    keyframes: doc.keyframes.map((k) => {
      const n = k.points.length
      let q: Pt = p
      if (k.frame !== frame && n >= 2) {
        const a = k.points[(index - 1 + n) % n]
        const b = k.points[index % n]
        q = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
      }
      const pts = [...k.points]
      pts.splice(index, 0, q)
      return { ...k, points: pts }
    }),
  }
}

export function removePoint(doc: MaskDoc, index: number): MaskDoc {
  return { ...doc, keyframes: doc.keyframes.map((k) => ({ ...k, points: k.points.filter((_, i) => i !== index) })) }
}

/** Index of the polygon edge closest to p (edge i goes from point i to point i+1); used to insert a point. */
export function nearestEdge(points: Pt[], p: Pt): { index: number; dist: number } {
  let best = { index: 0, dist: Infinity }
  const n = points.length
  for (let i = 0; i < n; i++) {
    const a = points[i]
    const b = points[(i + 1) % n]
    const dx = b[0] - a[0]
    const dy = b[1] - a[1]
    const L = dx * dx + dy * dy || 1e-12
    const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    const d = Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))
    if (d < best.dist) best = { index: i + 1, dist: d }
  }
  return best
}

export function validate(doc: MaskDoc): string[] {
  const errs: string[] = []
  const ks = doc.keyframes
  if (doc.version !== 1) errs.push('version must be 1')
  const n = ks[0]?.points.length
  ks.forEach((k) => {
    if (k.points.length !== n) errs.push(`keyframe ${k.frame}: ${k.points.length} points, expected ${n}`)
    if (k.frame < 0 || k.frame >= doc.frames) errs.push(`keyframe ${k.frame} out of range`)
  })
  if (new Set(ks.map((k) => k.frame)).size !== ks.length) errs.push('duplicate keyframe')
  return errs
}

/** Move every point of the keyframe at `frame` so the shape starts from `base` shifted by (dx, dy).
 * The shift is limited so that no point leaves the 0..1 frame (the shape keeps its form). */
export function translateKey(doc: MaskDoc, frame: number, base: Pt[], dx: number, dy: number): MaskDoc {
  const lim = (v: number, vals: number[]) => Math.min(Math.max(v, -Math.min(...vals)), 1 - Math.max(...vals))
  const sx = lim(dx, base.map((p) => p[0]))
  const sy = lim(dy, base.map((p) => p[1]))
  return {
    ...doc,
    keyframes: doc.keyframes.map((k) => (k.frame !== frame ? k : { ...k, points: base.map((p): Pt => [p[0] + sx, p[1] + sy]) })),
  }
}

/** How far point i is from the straight line between its two neighbours (closed polygon), in pixels,
 *  and the turning angle at the point in degrees (0 = perfectly straight). */
export function flatness(points: Pt[], i: number, size: [number, number]): { angle: number; dist: number } {
  const n = points.length
  const s = (p: Pt): Pt => [p[0] * size[0], p[1] * size[1]]
  const a = s(points[(i + n - 1) % n]), p = s(points[i]), b = s(points[(i + 1) % n])
  const u: Pt = [p[0] - a[0], p[1] - a[1]], v: Pt = [b[0] - p[0], b[1] - p[1]]
  const lu = Math.hypot(...u), lv = Math.hypot(...v), lab = Math.hypot(b[0] - a[0], b[1] - a[1])
  if (lu < 1e-9 || lv < 1e-9) return { angle: 0, dist: 0 } // duplicate point: useless
  const cos = Math.min(1, Math.max(-1, (u[0] * v[0] + u[1] * v[1]) / (lu * lv)))
  const dist = lab < 1e-9 ? lu : Math.abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1])) / lab
  return { angle: (Math.acos(cos) * 180) / Math.PI, dist }
}

/** Remove points that are useless on EVERY keyframe: turning angle below `angleDeg` and distance to the
 *  neighbours' line below `maxDistPx` on all keys. One point at a time (the flattest first), recomputed
 *  each time so that a gentle curve is not flattened by removing many points in a row. Keeps at least 3. */
export function cleanup(doc: MaskDoc, angleDeg = 3, maxDistPx = 2): { doc: MaskDoc; removed: number } {
  let d = doc
  let removed = 0
  for (;;) {
    const n = d.keyframes[0]?.points.length ?? 0
    if (n <= 3) break
    let best = -1
    let bestScore = Infinity
    for (let i = 0; i < n; i++) {
      let worstA = 0, worstD = 0
      for (const k of d.keyframes) {
        const f = flatness(k.points, i, d.size)
        worstA = Math.max(worstA, f.angle)
        worstD = Math.max(worstD, f.dist)
      }
      if (worstA < angleDeg && worstD < maxDistPx) {
        const score = worstA / angleDeg + worstD / maxDistPx
        if (score < bestScore) { bestScore = score; best = i }
      }
    }
    if (best < 0) break
    d = removePoint(d, best)
    removed++
  }
  return { doc: d, removed }
}
