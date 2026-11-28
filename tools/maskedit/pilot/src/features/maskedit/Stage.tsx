import { MousePointerClick } from "lucide-react"
import { MaskEditor } from "@maskedit/MaskEditor"
import type { MaskDoc } from "@maskedit/core"
import { EmptyState } from "@/components/app/EmptyState"
import { frameUrl, packFetch } from "@/lib/api"
import type { Ctx } from "@/lib/api"
import type { ProxyInfo } from "@/features/timeline/Timeline"

/** Center: the video frame with the editable polygon (the existing MaskEditor component, unchanged). */
export function Stage({
  ctx,
  doc,
  frame,
  onChange,
  onFrame,
  onCache,
}: {
  ctx: Ctx
  doc: MaskDoc | null
  frame: number
  onChange: (d: MaskDoc) => void
  onFrame: (f: number) => void
  onCache?: (c: ProxyInfo | null) => void
}) {
  if (!doc)
    return (
      <div className="h-full bg-background">
        <EmptyState icon={<MousePointerClick className="size-6" />} title="Aucun projet ouvert" hint="Ouvre un projet maskedit dans le panneau de gauche." />
      </div>
    )
  return (
    <div className="h-full overflow-auto bg-background p-3">
      <MaskEditor
        key={ctx.clip + doc.clip}
        doc={doc}
        onChange={onChange}
        frame={frame}
        onFrame={onFrame}
        onCache={onCache}
        frameUrl={(f) => frameUrl(ctx, f)}
        packFetch={(k, w, pf) => packFetch(ctx, k, w, pf)}
      />
    </div>
  )
}
