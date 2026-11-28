// One open maskedit project: document, current frame, debounced save queue (with base_rev), undo/redo, export.
// Same behaviour as the Editor of the current /lab/maskedit page (copied here for the pilot; to be shared later).
import { useEffect, useRef, useState } from "react"
import { validate } from "@maskedit/core"
import type { MaskDoc } from "@maskedit/core"
import { api, post, query } from "@/lib/api"
import type { Ctx } from "@/lib/api"
import type { Status } from "@/components/app/StatusBadge"
import { BOOT, saveSel } from "@/lib/storage"

export function useMaskSession(ctx: Ctx, mp: string | null) {
  const [doc, setDoc] = useState<MaskDoc | null>(null)
  const [frame, setFrame] = useState(() => (BOOT.open === mp && Number.isInteger(BOOT.frame) ? Math.max(0, BOOT.frame) : 0))
  const [status, setStatus] = useState<Status>({ kind: "idle", text: "" })
  const timer = useRef<number | undefined>(undefined)
  const revRef = useRef(0)
  const saving = useRef(false)
  const pending = useRef<MaskDoc | null>(null)
  const undoStack = useRef<MaskDoc[]>([])
  const redoStack = useRef<MaskDoc[]>([])
  const lastPush = useRef(0)
  const docRef = useRef<MaskDoc | null>(null)
  docRef.current = doc

  useEffect(() => {
    if (!mp) return
    const id = window.setTimeout(() => saveSel({ open: mp, frame }), 400)
    return () => window.clearTimeout(id)
  }, [frame, mp])
  useEffect(() => {
    // (re)load when another project is opened; nothing is shown while none is open
    setDoc(null); undoStack.current = []; redoStack.current = []; pending.current = null
    setFrame(mp && BOOT.open === mp && Number.isInteger(BOOT.frame) ? Math.max(0, BOOT.frame) : 0)
    setStatus({ kind: "idle", text: "" })
    if (!mp) return
    let alive = true
    api<{ doc: MaskDoc; rev: number }>("api/doc?" + query({ ...ctx, mp }))
      .then((r) => {
        if (!alive) return
        revRef.current = r.rev
        setDoc(r.doc)
        setFrame((f) => Math.min(f, Math.max(0, r.doc.frames - 1)))
      })
      .catch((e) => alive && setStatus({ kind: "error", text: "erreur: " + e.message }))
    return () => { alive = false }
  }, [mp])

  const flush = async () => {
    if (!mp || saving.current || !pending.current) return
    saving.current = true
    const d = pending.current
    pending.current = null
    try {
      const r = await post("api/doc", { ...ctx, mp, base_rev: revRef.current, doc: d }, "PUT")
      revRef.current = r.rev
      setStatus({ kind: "ok", text: "enregistré" })
    } catch (e) {
      setStatus({ kind: "error", text: "erreur: " + (e as Error).message })
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
    if (cur && cur !== d && now - lastPush.current > 700) { undoStack.current.push(cur); if (undoStack.current.length > 200) undoStack.current.shift() }
    if (cur !== d) { lastPush.current = now; redoStack.current = [] }
    setDoc(d)
    save(d)
  }
  const undo = () => {
    const prev = undoStack.current.pop(), cur = docRef.current
    if (!prev || !cur) return
    redoStack.current.push(cur); lastPush.current = 0; setDoc(prev); save(prev)
  }
  const redo = () => {
    const next = redoStack.current.pop(), cur = docRef.current
    if (!next || !cur) return
    undoStack.current.push(cur); lastPush.current = 0; setDoc(next); save(next)
  }
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return
      const k = e.key.toLowerCase()
      if (k === "z" && !e.shiftKey) { e.preventDefault(); undo() }
      else if ((k === "z" && e.shiftKey) || k === "y") { e.preventDefault(); redo() }
    }
    window.addEventListener("keydown", h)
    return () => window.removeEventListener("keydown", h)
  })

  const exportMask = async () => {
    if (!doc || !mp) return
    const errs = validate(doc)
    if (errs.length) { setStatus({ kind: "error", text: "erreur: " + errs.join(", ") }); return }
    await flushNow()
    setStatus({ kind: "busy", text: "export en cours…" })
    try {
      const r = await post("api/export", { ...ctx, mp })
      setStatus({ kind: "ok", text: "ajouté au projet comme nouvel asset: " + r.name })
    } catch (e) { setStatus({ kind: "error", text: "export refusé: " + (e as Error).message }) }
  }

  return { doc, frame, setFrame, change, undo, redo, status, exportMask, flushNow }
}
