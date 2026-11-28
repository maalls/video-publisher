// Explorer data: space (top) > YABBE project > clips > maskedit projects, loaded lazily as nodes expand.
// Same API as the current /lab/maskedit page. The last state (space, expanded nodes, open project) is remembered.
import { useEffect, useRef, useState } from "react"
import { api, post, query } from "@/lib/api"
import type { Clip, Ctx, MaskProject, Named } from "@/lib/api"
import { BOOT, saveSel } from "@/lib/storage"

export const pKey = (p: string) => "p:" + p
export const cKey = (p: string, c: string) => "c:" + p + "/" + c

export function useCatalog() {
  const [spaces, setSpaces] = useState<Named[]>([])
  const [projects, setProjects] = useState<Named[]>([])
  const [clipsBy, setClipsBy] = useState<Record<string, Clip[]>>({})
  const [mpsBy, setMpsBy] = useState<Record<string, MaskProject[]>>({})
  const [space, setSpace] = useState<string>(BOOT.space || "")
  const [project, setProject] = useState<string>("")
  const [clip, setClip] = useState<string>("")
  const [open, setOpen] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string[]>(Array.isArray(BOOT.exp) ? BOOT.exp : [])
  const [error, setError] = useState("")
  const boot = useRef(true)
  const fail = (e: unknown) => setError((e as Error).message)
  const ctx: Ctx = { space, project, clip }
  const ctxOf = (p: string, c: string): Ctx => ({ space, project: p, clip: c })

  useEffect(() => {
    saveSel({ space })
  }, [space])
  useEffect(() => {
    saveSel({ exp: expanded })
  }, [expanded])
  useEffect(() => {
    saveSel({ project, clip, open: open || "" })
  }, [project, clip, open])
  useEffect(() => {
    api<Named[]>("api/spaces")
      .then((s) => {
        setSpaces(s)
        if (s.length === 1 && !space) setSpace(s[0].id)
      })
      .catch(fail)
  }, [])

  const loadClips = (p: string) =>
    api<Clip[]>("api/clips?" + query({ space, project: p }))
      .then((c) => setClipsBy((m) => ({ ...m, [p]: c })))
      .catch(fail)
  const loadMps = (p: string, c: string) =>
    api<MaskProject[]>("api/mprojects?" + query(ctxOf(p, c)))
      .then((m) => {
        setMpsBy((x) => ({ ...x, [cKey(p, c)]: m }))
        return m
      })
      .catch((e) => {
        fail(e)
        return [] as MaskProject[]
      })

  const openMp = async (p: string, c: string, id: string) => {
    setError("")
    setOpen(null)
    setProject(p)
    setClip(c)
    try {
      await post("api/mproject-state", { ...ctxOf(p, c), mp: id, status: "open" })
      setOpen(id)
    } catch (e) {
      fail(e)
    }
  }
  const expand = (key: string) => setExpanded((e) => (e.includes(key) ? e : [...e, key]))
  // A click on a clip opens it: expands it and opens its remembered (else first) maskedit project.
  const openClip = async (p: string, c: string, prefer?: string) => {
    setOpen(null)
    setProject(p)
    setClip(c)
    expand(pKey(p))
    expand(cKey(p, c))
    const m = await loadMps(p, c)
    const id = m.find((x) => x.id === prefer)?.id || m[0]?.id
    if (id) openMp(p, c, id)
  }

  useEffect(() => {
    setProjects([])
    setClipsBy({})
    setMpsBy({})
    setOpen(null)
    setProject("")
    setClip("")
    if (!space) return
    api<Named[]>("api/projects?" + query({ space }))
      .then((ps) => {
        setProjects(ps)
        expanded.forEach((k) => {
          if (k.startsWith("p:") && ps.some((x) => pKey(x.id) === k)) loadClips(k.slice(2))
          if (k.startsWith("c:")) {
            const [p, c] = k.slice(2).split("/")
            if (ps.some((x) => x.id === p)) loadMps(p, c)
          }
        })
        if (boot.current && BOOT.space === space && BOOT.project && BOOT.clip && ps.some((x) => x.id === BOOT.project))
          openClip(BOOT.project, BOOT.clip, BOOT.open)
        boot.current = false
      })
      .catch(fail)
  }, [space])

  const reloadClip = (p: string, c: string) => loadMps(p, c)
  return {
    ctx,
    spaces,
    projects,
    clipsBy,
    mpsBy,
    expanded,
    open,
    error,
    pickSpace: setSpace,
    toggle: (key: string) => {
      const on = expanded.includes(key)
      setExpanded((e) => (on ? e.filter((x) => x !== key) : [...e, key]))
      if (!on && key.startsWith("p:") && !clipsBy[key.slice(2)]) loadClips(key.slice(2))
      if (!on && key.startsWith("c:")) {
        const [p, c] = key.slice(2).split("/")
        loadMps(p, c)
      }
    },
    openClip,
    openMp,
    closeMp: async (p: string, c: string, id: string) => {
      try {
        await post("api/mproject-state", { ...ctxOf(p, c), mp: id, status: "closed" })
      } catch (e) {
        fail(e)
      }
      setOpen(null)
      reloadClip(p, c)
    },
    createMp: async (p: string, c: string, name: string) => {
      setError("")
      try {
        const r = await post("api/mprojects", { ...ctxOf(p, c), name })
        expand(pKey(p))
        expand(cKey(p, c))
        await reloadClip(p, c)
        openMp(p, c, r.id)
      } catch (e) {
        fail(e)
      }
    },
    renameMp: async (p: string, c: string, id: string, name: string) => {
      setError("")
      try {
        await post("api/mproject-state", { ...ctxOf(p, c), mp: id, name })
        reloadClip(p, c)
      } catch (e) {
        fail(e)
      }
    },
  }
}
