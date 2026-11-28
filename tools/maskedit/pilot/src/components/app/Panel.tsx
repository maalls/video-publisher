import type { ReactNode } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"

/** A docked panel: title bar (+ optional actions) and a scrollable body. */
export function Panel({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="flex h-full min-h-0 flex-col bg-card">
      <div className="flex h-9 shrink-0 items-center justify-between gap-2 border-b px-3">
        <h2 className="truncate text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title}</h2>
        <div className="flex items-center gap-1">{actions}</div>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="p-3">{children}</div>
      </ScrollArea>
    </section>
  )
}
