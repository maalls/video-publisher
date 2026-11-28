import type { ReactNode } from "react"
import { ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"

/** One row of a tree explorer. Indentation follows `depth`; `expanded` undefined means a leaf (no chevron). */
export function TreeRow({
  depth,
  icon,
  label,
  expanded,
  selected,
  active,
  trailing,
  onClick,
  onToggle,
  testId,
}: {
  depth: number
  icon?: ReactNode
  label: ReactNode
  expanded?: boolean
  selected?: boolean
  active?: boolean
  trailing?: ReactNode
  onClick?: () => void
  onToggle?: () => void
  testId?: string
}) {
  return (
    <div
      role="treeitem"
      aria-expanded={expanded}
      aria-selected={selected}
      tabIndex={0}
      data-testid={testId}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter") onClick?.()
        if (e.key === "ArrowRight" && expanded === false) onToggle?.()
        if (e.key === "ArrowLeft" && expanded) onToggle?.()
      }}
      style={{ paddingLeft: 4 + depth * 14 }}
      className={cn(
        "group flex h-7 cursor-pointer items-center gap-1 rounded-md pr-1 text-sm outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring",
        selected && "bg-accent",
        active && "font-medium text-primary",
      )}
    >
      <span
        className="flex size-5 shrink-0 items-center justify-center text-muted-foreground"
        onClick={(e) => {
          if (expanded !== undefined) {
            e.stopPropagation()
            onToggle?.()
          }
        }}
      >
        {expanded !== undefined && <ChevronRight className={cn("size-4 transition-transform", expanded && "rotate-90")} />}
      </span>
      {icon && <span className="shrink-0 text-muted-foreground [&_svg]:size-4">{icon}</span>}
      <span className="min-w-0 flex-1 truncate">{label}</span>
      <span className="flex shrink-0 items-center gap-1">{trailing}</span>
    </div>
  )
}
