import { useState } from "react"
import { Film, FolderClosed, FolderOpen, Layers, Pencil, PanelLeftClose, PanelLeftOpen, Plus, X } from "lucide-react"
import { EmptyState } from "@/components/app/EmptyState"
import { IconButton } from "@/components/app/IconButton"
import { NameDialog } from "@/components/app/NameDialog"
import { Panel } from "@/components/app/Panel"
import { TreeRow } from "@/components/app/TreeRow"
import { Badge } from "@/components/ui/badge"
import type { Clip, MaskProject, Named } from "@/lib/api"
import { cKey, pKey } from "./useCatalog"

type Dlg = null | { kind: "new"; p: string; c: string } | { kind: "rename"; p: string; c: string; mp: MaskProject }

/** Left panel: tree explorer. YABBE project > clips > maskedit projects of the clip. A click on a clip opens it. */
export function ExplorerPanel({
  projects,
  clipsBy,
  mpsBy,
  expanded,
  curProject,
  curClip,
  open,
  onToggle,
  onOpenClip,
  onOpenMp,
  onCloseMp,
  onCreate,
  onRename,
  collapsed,
  onToggleCollapse,
}: {
  projects: Named[]
  clipsBy: Record<string, Clip[]>
  mpsBy: Record<string, MaskProject[]>
  expanded: string[]
  curProject: string
  curClip: string
  open: string | null
  onToggle: (key: string) => void
  onOpenClip: (p: string, c: string) => void
  onOpenMp: (p: string, c: string, id: string) => void
  onCloseMp: (p: string, c: string, id: string) => void
  onCreate: (p: string, c: string, name: string) => void
  onRename: (p: string, c: string, id: string, name: string) => void
  collapsed: boolean
  onToggleCollapse: () => void
}) {
  const [dlg, setDlg] = useState<Dlg>(null)
  if (collapsed)
    return (
      <div className="flex h-full flex-col items-center bg-card pt-1.5">
        <IconButton label="Déplier l'explorateur" onClick={onToggleCollapse} data-testid="explorer-expand">
          <PanelLeftOpen />
        </IconButton>
      </div>
    )
  return (
    <Panel
      title="Explorateur"
      actions={
        <IconButton label="Replier l'explorateur" onClick={onToggleCollapse} data-testid="explorer-collapse">
          <PanelLeftClose />
        </IconButton>
      }
    >
      {projects.length === 0 ? (
        <EmptyState icon={<Film className="size-6" />} title="Aucun projet" hint="Choisis un espace dans la barre du haut." />
      ) : (
        <div role="tree" className="flex flex-col gap-px">
          {projects.map((p) => {
            const pOpen = expanded.includes(pKey(p.id))
            const clips = clipsBy[p.id]
            return (
              <div key={p.id}>
                <TreeRow
                  depth={0}
                  testId={"proj-" + p.id}
                  icon={pOpen ? <FolderOpen /> : <FolderClosed />}
                  label={p.name}
                  expanded={pOpen}
                  onToggle={() => onToggle(pKey(p.id))}
                  onClick={() => onToggle(pKey(p.id))}
                />
                {pOpen && clips && clips.length === 0 && <div className="py-1 pl-10 text-xs text-muted-foreground">Aucun clip</div>}
                {pOpen &&
                  clips?.map((c) => {
                    const cOpen = expanded.includes(cKey(p.id, c.id))
                    const mps = mpsBy[cKey(p.id, c.id)]
                    const isCur = curProject === p.id && curClip === c.id
                    return (
                      <div key={c.id}>
                        <TreeRow
                          depth={1}
                          testId={"clip-" + c.id}
                          icon={<Film />}
                          label={c.name}
                          expanded={cOpen}
                          selected={isCur}
                          onToggle={() => onToggle(cKey(p.id, c.id))}
                          onClick={() => onOpenClip(p.id, c.id)}
                          trailing={
                            <IconButton
                              label="Nouveau projet maskedit"
                              className="size-5 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                              onClick={(e) => {
                                e.stopPropagation()
                                setDlg({ kind: "new", p: p.id, c: c.id })
                              }}
                              data-testid={"new-" + c.id}
                            >
                              <Plus />
                            </IconButton>
                          }
                        />
                        {cOpen && mps && mps.length === 0 && <div className="py-1 pl-16 text-xs text-muted-foreground">Aucun projet maskedit (+)</div>}
                        {cOpen &&
                          mps?.map((m) => (
                            <TreeRow
                              key={m.id}
                              depth={2}
                              testId={"mp-" + m.id}
                              icon={<Layers />}
                              label={m.name}
                              selected={open === m.id}
                              active={open === m.id}
                              onClick={() => onOpenMp(p.id, c.id, m.id)}
                              trailing={
                                <>
                                  <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
                                    {m.keyframes} clé{m.keyframes > 1 ? "s" : ""}
                                  </Badge>
                                  <IconButton
                                    label="Renommer"
                                    className="size-5 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      setDlg({ kind: "rename", p: p.id, c: c.id, mp: m })
                                    }}
                                  >
                                    <Pencil />
                                  </IconButton>
                                  {open === m.id && (
                                    <IconButton
                                      label="Fermer ce projet"
                                      className="size-5"
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        onCloseMp(p.id, c.id, m.id)
                                      }}
                                    >
                                      <X />
                                    </IconButton>
                                  )}
                                </>
                              }
                            />
                          ))}
                      </div>
                    )
                  })}
              </div>
            )
          })}
        </div>
      )}
      <NameDialog
        open={dlg?.kind === "new"}
        title="Nouveau projet maskedit"
        confirmLabel="Créer"
        onClose={() => setDlg(null)}
        onSubmit={(n) => {
          const d = dlg
          setDlg(null)
          if (d?.kind === "new") onCreate(d.p, d.c, n)
        }}
      />
      <NameDialog
        open={dlg?.kind === "rename"}
        title="Renommer le projet"
        initial={dlg?.kind === "rename" ? dlg.mp.name : ""}
        confirmLabel="Renommer"
        onClose={() => setDlg(null)}
        onSubmit={(n) => {
          const d = dlg
          setDlg(null)
          if (d?.kind === "rename") onRename(d.p, d.c, d.mp.id, n)
        }}
      />
    </Panel>
  )
}
