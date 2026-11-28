import { useEffect } from "react"
import { PersistentGroup } from "@/components/app/PersistentGroup"
import type { Status } from "@/components/app/StatusBadge"
import { ResizableHandle, ResizablePanel } from "@/components/ui/resizable"
import type { Ctx, MaskProject } from "@/lib/api"
import { Inspector } from "./Inspector"
import { ProjectsPanel } from "./ProjectsPanel"
import { Shortcuts } from "./Shortcuts"
import { Stage } from "./Stage"
import { useMaskSession } from "./useMaskSession"

/** Three-column workspace: projects | stage + shortcuts | inspector. Panel sizes are remembered per group id. */
export function Workspace({
  ctx, mps, mpSel, open, onSelect, onOpen, onClose, onCreate, onRename, onStatus,
}: {
  ctx: Ctx
  mps: MaskProject[]
  mpSel: string
  open: string | null
  onSelect: (id: string) => void
  onOpen: (id: string) => void
  onClose: (id: string) => void
  onCreate: (name: string) => void
  onRename: (id: string, name: string) => void
  onStatus: (s: Status) => void
}) {
  const s = useMaskSession(ctx, open)
  useEffect(() => { onStatus(s.status) }, [s.status.kind, s.status.text])
  return (
    <PersistentGroup id="maskedit-ui-main" orientation="horizontal">
      <ResizablePanel id="left" defaultSize="20%" minSize="14%" maxSize="35%">
        <ProjectsPanel hasClip={!!ctx.clip} mps={mps} selected={mpSel} open={open} onSelect={onSelect} onOpen={onOpen} onClose={onClose} onCreate={onCreate} onRename={onRename} />
      </ResizablePanel>
      <ResizableHandle withHandle />
      <ResizablePanel id="center" minSize="30%">
        <PersistentGroup id="maskedit-ui-center" orientation="vertical">
          <ResizablePanel id="stage" defaultSize="78%" minSize="40%">
            <Stage ctx={ctx} doc={s.doc} frame={s.frame} onChange={s.change} onFrame={s.setFrame} />
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel id="help" defaultSize="22%" minSize="8%" collapsible collapsedSize="0%">
            <Shortcuts />
          </ResizablePanel>
        </PersistentGroup>
      </ResizablePanel>
      <ResizableHandle withHandle />
      <ResizablePanel id="right" defaultSize="24%" minSize="16%" maxSize="40%">
        <Inspector doc={s.doc} frame={s.frame} status={s.status} onChange={s.change} onFrame={s.setFrame} onUndo={s.undo} onRedo={s.redo} onExport={s.exportMask} />
      </ResizablePanel>
    </PersistentGroup>
  )
}
