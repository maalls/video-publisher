import { useEffect, useLayoutEffect, useRef, useState } from "react"
import type { MaskDoc } from "@maskedit/core"
import type { ClipCache } from "@maskedit/clipcache"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export interface ProxyInfo {
  cache: ClipCache
  pfps: number
  fps: number
  nProxy: number
}

const RULER_H = 24
const VIDEO_H = 56
const MASK_H = 32
const HEAD_W = 96
const PAD = 8 // left/right margin so the first and last keys are fully visible
const MAX_PPF = 14 // px per source frame at maximum zoom

const pad = (n: number, w = 2) => String(n).padStart(w, "0")
export const timecode = (frame: number, fps: number) => {
  const t = frame / fps
  return `${pad(Math.floor(t / 60))}:${pad(Math.floor(t % 60))}.${pad(Math.floor((t % 1) * 100))}`
}

/** Timeline: ruler, playhead, video filmstrip (from the proxy cache) and the mask keyframes track. Frames are SOURCE frames. */
export function Timeline({ doc, frame, onFrame, proxy }: { doc: MaskDoc; frame: number; onFrame: (f: number) => void; proxy: ProxyInfo | null }) {
  const box = useRef<HTMLDivElement>(null)
  const inner = useRef<HTMLDivElement>(null)
  const ruler = useRef<HTMLCanvasElement>(null)
  const film = useRef<HTMLCanvasElement>(null)
  const bitmaps = useRef(new Map<number, ImageBitmap | "pending">())
  const [vw, setVw] = useState(600)
  const [scroll, setScroll] = useState(0)
  const [z, setZ] = useState(0) // 0 = fit the whole clip, 1 = max zoom
  const [tick, setTick] = useState(0)
  const dragging = useRef(false)
  const frames = doc.frames
  const fit = Math.max(0.01, (vw - 2 * PAD) / frames)
  const ppf = Math.max(fit, fit * Math.pow(Math.max(1, MAX_PPF / fit), z))
  const width = Math.max(vw, frames * ppf + 2 * PAD)
  const tw = Math.round((VIDEO_H * doc.size[0]) / doc.size[1])
  const fps = doc.fps || 16

  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(() => setVw(el.clientWidth))
    ro.observe(el)
    setVw(el.clientWidth)
    return () => ro.disconnect()
  }, [])
  // repaint while the proxy is still loading
  useEffect(() => {
    if (!proxy) return
    let last = -1
    const id = window.setInterval(() => {
      const l = proxy.cache.stats.loaded
      if (l !== last) {
        last = l
        setTick((t) => t + 1)
      }
    }, 400)
    return () => window.clearInterval(id)
  }, [proxy])
  useEffect(() => {
    bitmaps.current.forEach((b) => b !== "pending" && b.close())
    bitmaps.current.clear()
  }, [proxy, doc.clip, tw])

  // keep the playhead visible (playback, arrows)
  useEffect(() => {
    const el = box.current
    if (!el || dragging.current) return
    const x = PAD + frame * ppf
    if (x < el.scrollLeft + 8 || x > el.scrollLeft + vw - 24) el.scrollLeft = Math.max(0, x - vw / 2)
  }, [frame, ppf, vw])

  // ruler
  useEffect(() => {
    const c = ruler.current
    if (!c) return
    c.width = vw
    c.height = RULER_H
    const g = c.getContext("2d")!
    g.fillStyle = "#8b93a7"
    g.strokeStyle = "#2b3040"
    g.font = "10px ui-monospace, monospace"
    const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300]
    const pxPerSec = ppf * fps
    const step = steps.find((s) => s * pxPerSec >= 70) ?? 300
    for (let t = Math.max(0, Math.floor((scroll - PAD) / pxPerSec / step) * step); PAD + t * pxPerSec - scroll < vw; t += step) {
      const x = Math.round(PAD + t * pxPerSec - scroll) + 0.5
      g.beginPath()
      g.moveTo(x, 12)
      g.lineTo(x, RULER_H)
      g.stroke()
      g.fillText(step < 1 ? t.toFixed(1) + "s" : `${Math.floor(t / 60)}:${pad(Math.round(t % 60))}`, x + 3, 10)
    }
  }, [vw, ppf, scroll, fps])

  // filmstrip: one tile per `tw` pixels, taken from the nearest proxy image
  useEffect(() => {
    const c = film.current
    if (!c) return
    c.width = vw
    c.height = VIDEO_H
    const g = c.getContext("2d")!
    g.fillStyle = "#12151e"
    g.fillRect(0, 0, vw, VIDEO_H)
    if (!proxy) return
    const { cache, pfps, nProxy } = proxy
    const first = Math.floor(scroll / tw)
    for (let x = first * tw; x - scroll < vw && x < frames * ppf + 2 * PAD; x += tw) {
      const f = Math.min(frames - 1, Math.max(0, Math.floor((x + tw / 2 - PAD) / ppf)))
      const p = Math.min(nProxy - 1, Math.round((f * pfps) / fps))
      const bm = bitmaps.current.get(p)
      if (bm && bm !== "pending") g.drawImage(bm, x - scroll, 0, tw, VIDEO_H)
      else if (!bm) {
        const blob = cache.blobs.get(p)
        if (!blob) continue
        bitmaps.current.set(p, "pending")
        createImageBitmap(blob, { resizeWidth: tw, resizeHeight: VIDEO_H, resizeQuality: "medium" })
          .then((b) => {
            bitmaps.current.set(p, b)
            setTick((t) => t + 1)
          })
          .catch(() => bitmaps.current.delete(p))
      }
    }
    if (bitmaps.current.size > 500) {
      bitmaps.current.forEach((b) => b !== "pending" && b.close())
      bitmaps.current.clear()
    }
  }, [vw, ppf, scroll, proxy, tick, tw, frames, fps])

  const frameAt = (clientX: number) => {
    const r = inner.current!.getBoundingClientRect()
    return Math.min(frames - 1, Math.max(0, Math.round((clientX - r.left - PAD) / ppf)))
  }
  const scrub = {
    onPointerDown: (e: React.PointerEvent) => {
      dragging.current = true
      ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
      onFrame(frameAt(e.clientX))
    },
    onPointerMove: (e: React.PointerEvent) => {
      if (dragging.current) onFrame(frameAt(e.clientX))
    },
    onPointerUp: () => {
      dragging.current = false
    },
  }
  const keys = [...doc.keyframes].sort((a, b) => a.frame - b.frame)
  const total = HEAD_W

  return (
    <section className="flex h-full min-h-0 flex-col bg-card" data-testid="timeline">
      <div className="flex h-9 shrink-0 items-center gap-3 border-b px-3 text-sm">
        <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Timeline</span>
        <span className="font-mono text-primary" data-testid="tl-time">
          {timecode(frame, fps)} · image {frame} / {frames}
        </span>
        <div className="flex-1" />
        <span className="text-xs text-muted-foreground">Zoom</span>
        <input type="range" min={0} max={100} value={Math.round(z * 100)} data-testid="tl-zoom" className="w-32" onChange={(e) => setZ(+e.target.value / 100)} />
        <Button
          variant="outline"
          size="sm"
          data-testid="tl-fit"
          onClick={() => {
            setZ(0)
            if (box.current) box.current.scrollLeft = 0
          }}
        >
          Ajuster
        </Button>
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="shrink-0 border-r text-xs" style={{ width: total }}>
          <div style={{ height: RULER_H }} className="border-b" />
          <div style={{ height: VIDEO_H }} className="flex items-center border-b px-2">
            Vidéo
          </div>
          <div style={{ height: MASK_H }} className="flex items-center border-b px-2">
            Masque
          </div>
        </div>
        <div ref={box} className="min-w-0 flex-1 overflow-x-auto overflow-y-hidden" data-testid="tl-scroll" onScroll={(e) => setScroll(e.currentTarget.scrollLeft)}>
          <div ref={inner} className="relative" style={{ width }}>
            <div className="sticky left-0 z-0" style={{ width: vw }}>
              <canvas ref={ruler} data-testid="tl-ruler" className="block cursor-pointer border-b" style={{ width: vw, height: RULER_H }} {...scrub} />
              <canvas ref={film} data-testid="tl-film" className="block cursor-pointer border-b" style={{ width: vw, height: VIDEO_H }} {...scrub} />
            </div>
            <div className="relative border-b bg-background/40" style={{ height: MASK_H }} data-testid="tl-mask" {...scrub}>
              {keys.length > 1 && (
                <div
                  className="absolute top-[14px] h-1 rounded bg-primary/40"
                  style={{ left: PAD + keys[0].frame * ppf, width: (keys[keys.length - 1].frame - keys[0].frame) * ppf }}
                />
              )}
              {keys.map((k) => (
                <button
                  key={k.frame}
                  title={`clé ${k.frame}`}
                  data-testid={"tl-key-" + k.frame}
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={() => onFrame(k.frame)}
                  className={cn(
                    "absolute top-2 size-4 -translate-x-1/2 rotate-45 border border-black/50 bg-[#ffd000] outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    k.frame === frame && "ring-2 ring-white",
                  )}
                  style={{ left: PAD + k.frame * ppf, transform: "translateX(-50%) rotate(45deg) scale(.75)" }}
                />
              ))}
            </div>
            <div
              className="pointer-events-none absolute top-0 bottom-0 z-10 w-0 border-l-2 border-[#ff4d6d]"
              style={{ left: PAD + frame * ppf }}
              data-testid="tl-playhead"
            >
              <div className="absolute -top-px -left-[7px] border-x-[6px] border-t-[9px] border-x-transparent border-t-[#ff4d6d]" />
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
