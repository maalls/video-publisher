import { Field } from "@/components/app/Field"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

/** Labelled dropdown over a list of {id, name} items. */
export function PickerField<T extends { id: string }>({
  label,
  items,
  value,
  onPick,
  name,
  placeholder = "Choisir…",
  testId,
}: {
  label: string
  items: T[]
  value: string
  onPick: (id: string) => void
  name: (t: T) => string
  placeholder?: string
  testId?: string
}) {
  return (
    <Field label={label}>
      <Select value={value || undefined} onValueChange={onPick}>
        <SelectTrigger className="h-8 w-full min-w-40 text-sm" data-testid={testId}>
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {items.map((t) => (
            <SelectItem key={t.id} value={t.id}>
              {name(t)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  )
}
