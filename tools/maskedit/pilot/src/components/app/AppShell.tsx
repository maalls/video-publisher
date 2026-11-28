import type { ReactNode } from "react"
import { TooltipProvider } from "@/components/ui/tooltip"

/** Full-height application frame: header on top, resizable content below. */
export function AppShell({ header, children }: { header: ReactNode; children: ReactNode }) {
  return (
    <TooltipProvider delayDuration={300}>
      <div className="flex h-screen flex-col bg-background text-foreground">
        <header className="flex shrink-0 items-center gap-3 border-b bg-card px-3 py-2">{header}</header>
        <main className="min-h-0 flex-1">{children}</main>
      </div>
    </TooltipProvider>
  )
}
