import { useState } from "react"
import { Film, FolderOpen, Pencil, Plus, X } from "lucide-react"
import { NameDialog } from "@/components/app/NameDialog"
import { IconButton } from "@/components/app/IconButton"
import { Panel } from "@/components/app/Panel"
import { EmptyState } from "@/components/app/EmptyState"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { MaskProject } from "@/lib/api"

/** Left panel: the maskedit projects of the selected clip (several per clip). */
export function ProjectsPanel({
  hasClip, mps, selected, open, onSelect, onOpen, onClose, onCreate, onRename,
}: {
  hasClip: boolean
  mps: MaskProject[]
  selected: string
  open: string | null
  onSelect: (id: string) => void
  onOpen: (id: string) => void
  onClose: (id: string) => void
  onCreate: (name: string) => void
  onRename: (id: string, name: string) => void
}) {
  const [dialog, setDialog] = useState<null | "new" | "rename">(null)
  const cur = mps.find((m) => m.id === selected)
  return (
    <Panel
      title="Projets maskedit"
      actions={
        <>
          <IconButton label="Renommer" disabled={!cur} onClick={() => setDialog("rename")}><Pencil /></IconButton>
          <IconButton label="Nouveau projet maskedit" disabled={!hasClip} onClick={() => setDialog("new")} data-testid="btn-new"><Plus /></IconButton>
        </>
      }
    >
      {!hasClip ? (
        <EmptyState icon={<Film className="size-6" />} title="Aucun clip choisi" hint="Choisis un espace, un projet et un clip dans la barre du haut." />
      ) : mps.length === 0 ? (
        <EmptyState title="Aucun projet maskedit" hint="Crée-en un avec le bouton +. Un clip peut en avoir plusieurs." />
      ) : (
        <ul className="flex flex-col gap-1">
          {mps.map((m) => (
            <li key={m.id}>
              <div
                role="button"
                tabIndex={0}
                onClick={() => onSelect(m.id)}
                onDoubleClick={() => onOpen(m.id)}
                onKeyDown={(e) => e.key === "Enter" && onOpen(m.id)}
                className={cn(
                  "flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5 text-sm outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring",
                  selected === m.id ? "border-primary bg-accent" : "border-transparent",
                )}
              >
                <span className="min-w-0 flex-1 truncate">{m.name}</span>
                <Badge variant="outline" className="shrink-0">{m.keyframes} clé{m.keyframes > 1 ? "s" : ""}</Badge>
                {open === m.id ? (
                  <IconButton label="Fermer ce projet" className="size-6" onClick={(e) => { e.stopPropagation(); onClose(m.id) }}><X /></IconButton>
                ) : (
                  <IconButton label="Ouvrir" className="size-6" onClick={(e) => { e.stopPropagation(); onOpen(m.id) }} data-testid={"open-" + m.id}><FolderOpen /></IconButton>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      <NameDialog open={dialog === "new"} title="Nouveau projet maskedit" confirmLabel="Créer" onClose={() => setDialog(null)} onSubmit={(n) => { setDialog(null); onCreate(n) }} />
      <NameDialog open={dialog === "rename"} title="Renommer le projet" initial={cur?.name} confirmLabel="Renommer" onClose={() => setDialog(null)} onSubmit={(n) => { setDialog(null); cur && onRename(cur.id, n) }} />
    </Panel>
  )
}
