import { useState } from "react"
import { AppShell } from "@/components/app/AppShell"
import { PickerField } from "@/components/app/PickerField"
import { StatusBadge } from "@/components/app/StatusBadge"
import type { Status } from "@/components/app/StatusBadge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { ExplorerPanel } from "@/features/maskedit/ExplorerPanel"
import { useCatalog } from "@/features/maskedit/useCatalog"
import { Workspace } from "@/features/maskedit/Workspace"

export default function App() {
  const c = useCatalog()
  const [status, setStatus] = useState<Status>({ kind: "idle", text: "" })
  return (
    <AppShell
      header={
        <>
          <h1 className="mr-2 text-base font-semibold">Majo Gazo</h1>
          <div className="w-72">
            <PickerField label="Espace" items={c.spaces} value={c.ctx.space} onPick={c.pickSpace} name={(s) => s.name} testId="sel-Espace" />
          </div>
          <div className="flex-1" />
          <StatusBadge status={status} />
        </>
      }
    >
      {c.error && (
        <Alert variant="destructive" className="m-2">
          <AlertDescription>{c.error}</AlertDescription>
        </Alert>
      )}
      <Workspace
        ctx={c.ctx}
        open={c.open}
        onStatus={setStatus}
        left={({ collapsed, toggle }) => (
          <ExplorerPanel
            collapsed={collapsed}
            onToggleCollapse={toggle}
            projects={c.projects}
            clipsBy={c.clipsBy}
            mpsBy={c.mpsBy}
            expanded={c.expanded}
            curProject={c.ctx.project}
            curClip={c.ctx.clip}
            open={c.open}
            onToggle={c.toggle}
            onOpenClip={(p, k) => c.openClip(p, k)}
            onOpenMp={c.openMp}
            onCloseMp={c.closeMp}
            onCreate={c.createMp}
            onRename={c.renameMp}
          />
        )}
      />
    </AppShell>
  )
}
