// Space > YABBE project > clip > maskedit projects, plus which maskedit project is open.
// Same data flow as the current /lab/maskedit page; the last state is remembered (see lib/storage).
import { useEffect, useRef, useState } from "react"
import { api, post, query } from "@/lib/api"
import type { Clip, Ctx, MaskProject, Named } from "@/lib/api"
import { BOOT, saveSel } from "@/lib/storage"

export function useCatalog() {
  const [spaces, setSpaces] = useState<Named[]>([])
  const [projects, setProjects] = useState<Named[]>([])
  const [clips, setClips] = useState<Clip[]>([])
  const [mps, setMps] = useState<MaskProject[]>([])
  const [space, setSpace] = useState<string>(BOOT.space || "")
  const [project, setProject] = useState<string>(BOOT.project || "")
  const [clip, setClip] = useState<string>(BOOT.clip || "")
  const [mpSel, setMpSel] = useState("")
  const [open, setOpen] = useState<string | null>(null)
  const [error, setError] = useState("")
  const restore = useRef<string>(String(BOOT.open || ""))
  const fail = (e: unknown) => setError((e as Error).message)
  const ctx: Ctx = { space, project, clip }

  useEffect(() => { saveSel({ space, project, clip }) }, [space, project, clip])
  useEffect(() => { saveSel({ open: open || "", mp: mpSel }) }, [open, mpSel])
  useEffect(() => {
    api<Named[]>("api/spaces").then((s) => { setSpaces(s); if (s.length === 1 && !space) setSpace(s[0].id) }).catch(fail)
  }, [])
  useEffect(() => {
    setProjects([]); setOpen(null)
    if (!space) return
    api<Named[]>("api/projects?" + query({ space })).then((p) => {
      setProjects(p)
      if (!p.some((x) => x.id === project)) { setProject(""); setClip("") }
    }).catch(fail)
  }, [space])
  useEffect(() => {
    setClips([]); setOpen(null)
    if (!space || !project) return
    api<Clip[]>("api/clips?" + query({ space, project })).then((c) => {
      setClips(c)
      if (!c.some((x) => x.id === clip)) setClip("")
    }).catch(fail)
  }, [space, project])

  const openMp = async (id: string) => {
    setError("")
    try { await post("api/mproject-state", { ...ctx, mp: id, status: "open" }); setOpen(id) } catch (e) { fail(e) }
  }
  const reload = (keep?: string) => {
    if (!space || !project || !clip) { setMps([]); return }
    api<MaskProject[]>("api/mprojects?" + query(ctx)).then((m) => {
      setMps(m)
      const saved = BOOT.mp
      setMpSel(keep && m.some((x) => x.id === keep) ? keep : !keep && m.some((x) => x.id === saved) ? saved : m[0]?.id || "")
      if (!keep && restore.current && m.some((x) => x.id === restore.current)) {
        const id = restore.current
        restore.current = ""
        setMpSel(id)
        openMp(id)
      }
    }).catch(fail)
  }
  useEffect(() => { setOpen(null); reload() }, [space, project, clip])

  return {
    ctx, spaces, projects, clips, mps, mpSel, open, error,
    pickSpace: (v: string) => { setSpace(v); setProject(""); setClip("") },
    pickProject: (v: string) => { setProject(v); setClip("") },
    pickClip: setClip,
    selectMp: setMpSel,
    openMp,
    closeMp: async (id: string) => {
      try { await post("api/mproject-state", { ...ctx, mp: id, status: "closed" }) } catch (e) { fail(e) }
      setOpen(null); reload(id)
    },
    createMp: async (name: string) => {
      setError("")
      try { const r = await post("api/mprojects", { ...ctx, name }); reload(r.id); setOpen(r.id) } catch (e) { fail(e) }
    },
    renameMp: async (id: string, name: string) => {
      setError("")
      try { await post("api/mproject-state", { ...ctx, mp: id, name }); reload(id) } catch (e) { fail(e) }
    },
    reload,
  }
}
