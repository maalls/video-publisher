import { useEffect, useState, type ReactNode } from "react"
import { usePanelRef } from "react-resizable-panels"
import { PersistentGroup } from "@/components/app/PersistentGroup"
import type { Status } from "@/components/app/StatusBadge"
import { ResizableHandle, ResizablePanel } from "@/components/ui/resizable"
import type { Ctx } from "@/lib/api"
import { Inspector } from "./Inspector"
import { Shortcuts } from "./Shortcuts"
import { Stage } from "./Stage"
import { Timeline, type ProxyInfo } from "@/features/timeline/Timeline"
import { useMaskSession } from "./useMaskSession"

/** Three-column workspace: explorer | stage + shortcuts | inspector. Panel sizes are remembered per group id. */
export function Workspace({
  ctx,
  open,
  left,
  onStatus,
}: {
  ctx: Ctx
  open: string | null
  left: (c: { collapsed: boolean; toggle: () => void }) => ReactNode
  onStatus: (s: Status) => void
}) {
  const s = useMaskSession(ctx, open)
  const [proxy, setProxy] = useState<ProxyInfo | null>(null)
  const leftRef = usePanelRef()
  const [collapsed, setCollapsed] = useState(false)
  const toggle = () => (leftRef.current?.isCollapsed() ? leftRef.current.expand() : leftRef.current?.collapse())
  useEffect(() => {
    onStatus(s.status)
  }, [s.status.kind, s.status.text])
  return (
    <PersistentGroup id="maskedit-ui-main" orientation="horizontal">
      <ResizablePanel
        id="left"
        panelRef={leftRef}
        defaultSize="20%"
        minSize="14%"
        maxSize="35%"
        collapsible
        collapsedSize="40px"
        onResize={() => setCollapsed(!!leftRef.current?.isCollapsed())}
      >
        {left({ collapsed, toggle })}
      </ResizablePanel>
      <ResizableHandle withHandle />
      <ResizablePanel id="center" minSize="30%">
        <PersistentGroup id="maskedit-ui-center2" orientation="vertical">
          <ResizablePanel id="stage" defaultSize="52%" minSize="40%">
            <Stage ctx={ctx} doc={s.doc} frame={s.frame} onChange={s.change} onFrame={s.setFrame} onCache={setProxy} />
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel id="timeline" defaultSize="26%" minSize="14%">
            {s.doc ? <Timeline doc={s.doc} frame={s.frame} onFrame={s.setFrame} proxy={proxy} /> : <div className="h-full bg-card" />}
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel id="help" defaultSize="14%" minSize="8%" collapsible collapsedSize="0%">
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
