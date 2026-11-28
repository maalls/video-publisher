import type { ComponentProps } from "react"
import { useDefaultLayout } from "react-resizable-panels"
import { ResizablePanelGroup } from "@/components/ui/resizable"

/** Resizable panel group whose layout (sizes) is remembered in localStorage under `id`.
 *  Every panel inside must have a stable `id`. */
export function PersistentGroup({ id, ...props }: { id: string } & ComponentProps<typeof ResizablePanelGroup>) {
  const { defaultLayout, onLayoutChanged } = useDefaultLayout({ id, storage: localStorage })
  return <ResizablePanelGroup id={id} defaultLayout={defaultLayout} onLayoutChanged={onLayoutChanged} {...props} />
}
