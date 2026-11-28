import { Badge } from "@/components/ui/badge"

export type Status = { kind: "idle" | "ok" | "busy" | "error"; text: string }

/** Small status pill: saved / busy / error. */
export function StatusBadge({ status }: { status: Status }) {
  if (!status.text) return null
  const variant = status.kind === "error" ? "destructive" : status.kind === "ok" ? "secondary" : "outline"
  return (
    <Badge variant={variant} className="max-w-96 truncate" title={status.text}>
      {status.text}
    </Badge>
  )
}
