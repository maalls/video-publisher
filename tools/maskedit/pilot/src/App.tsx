import { useState } from "react"
import { AppShell } from "@/components/app/AppShell"
import { PickerField } from "@/components/app/PickerField"
import { StatusBadge } from "@/components/app/StatusBadge"
import type { Status } from "@/components/app/StatusBadge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { useCatalog } from "@/features/maskedit/useCatalog"
import { Workspace } from "@/features/maskedit/Workspace"

export default function App() {
  const c = useCatalog()
  const [status, setStatus] = useState<Status>({ kind: "idle", text: "" })
  return (
    <AppShell
      header={
        <>
          <h1 className="mr-2 text-base font-semibold">maskedit</h1>
          <div className="grid flex-1 grid-cols-3 gap-3">
            <PickerField label="Espace" items={c.spaces} value={c.ctx.space} onPick={c.pickSpace} name={(s) => s.name} testId="sel-Espace" />
            <PickerField label="Projet" items={c.projects} value={c.ctx.project} onPick={c.pickProject} name={(p) => p.name} testId="sel-Projet" />
            <PickerField label="Clip" items={c.clips} value={c.ctx.clip} onPick={c.pickClip} name={(k) => `${k.name} (${k.duration.toFixed(1)} s, ${k.width}x${k.height})`} testId="sel-Clip" />
          </div>
          <StatusBadge status={status} />
        </>
      }
    >
      {c.error && <Alert variant="destructive" className="m-2"><AlertDescription>{c.error}</AlertDescription></Alert>}
      <Workspace
        ctx={c.ctx} mps={c.mps} mpSel={c.mpSel} open={c.open}
        onSelect={c.selectMp} onOpen={c.openMp} onClose={c.closeMp} onCreate={c.createMp} onRename={c.renameMp}
        onStatus={setStatus}
      />
    </AppShell>
  )
}
