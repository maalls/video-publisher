import { Download, Redo2, Undo2 } from "lucide-react"
import type { MaskDoc } from "@maskedit/core"
import { Field } from "@/components/app/Field"
import { Panel } from "@/components/app/Panel"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import type { Status } from "@/components/app/StatusBadge"

const PROXY_FPS = [8, 12, 16, 24]
const PROXY_WIDTH = [480, 640, 960, 1280]

/** Right panel: preview (proxy) settings, mask options, keyframes list, export. */
export function Inspector({
  doc,
  frame,
  status,
  onChange,
  onFrame,
  onUndo,
  onRedo,
  onExport,
}: {
  doc: MaskDoc | null
  frame: number
  status: Status
  onChange: (d: MaskDoc) => void
  onFrame: (f: number) => void
  onUndo: () => void
  onRedo: () => void
  onExport: () => void
}) {
  if (!doc)
    return (
      <Panel title="Inspecteur">
        <p className="text-sm text-muted-foreground">Ouvre un projet maskedit pour régler l'aperçu, voir les clés et exporter.</p>
      </Panel>
    )
  const fps = doc.proxy?.fps ?? 12
  const width = doc.proxy?.width ?? 960
  const keys = [...doc.keyframes].sort((a, b) => a.frame - b.frame)
  return (
    <Panel
      title="Inspecteur"
      actions={
        <>
          <Button variant="ghost" size="sm" onClick={onUndo} title="Annuler (Ctrl/Cmd+Z)">
            <Undo2 />
          </Button>
          <Button variant="ghost" size="sm" onClick={onRedo} title="Rétablir (Ctrl/Cmd+Maj+Z)">
            <Redo2 />
          </Button>
        </>
      }
    >
      <Tabs defaultValue="preview">
        <TabsList className="w-full">
          <TabsTrigger value="preview">Aperçu</TabsTrigger>
          <TabsTrigger value="keys">Clés ({keys.length})</TabsTrigger>
          <TabsTrigger value="export">Export</TabsTrigger>
        </TabsList>

        <TabsContent value="preview" className="mt-3 flex flex-col gap-4">
          <Field label="Images par seconde du proxy">
            <ToggleGroup type="single" variant="outline" size="sm" value={String(fps)} onValueChange={(v) => v && onChange({ ...doc, proxy: { fps: +v, width } })}>
              {PROXY_FPS.map((v) => (
                <ToggleGroupItem key={v} value={String(v)}>
                  {v}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </Field>
          <Field label="Largeur du proxy (px)">
            <ToggleGroup type="single" variant="outline" size="sm" value={String(width)} onValueChange={(v) => v && onChange({ ...doc, proxy: { fps, width: +v } })}>
              {PROXY_WIDTH.map((v) => (
                <ToggleGroupItem key={v} value={String(v)}>
                  {v}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </Field>
          <p className="text-xs text-muted-foreground">
            Réglage enregistré dans ce projet maskedit. Les clés et l'export restent sur le clip source ({doc.frames} images, {doc.fps} i/s).
          </p>
        </TabsContent>

        <TabsContent value="keys" className="mt-3">
          {keys.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucune clé. Clique dans l'image pour tracer un polygone.</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {keys.map((k) => (
                <li key={k.frame}>
                  <Button variant={k.frame === frame ? "secondary" : "ghost"} size="sm" className="w-full justify-between" onClick={() => onFrame(k.frame)}>
                    <span>image {k.frame}</span>
                    <span className="text-xs text-muted-foreground">{k.points.length} points</span>
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </TabsContent>

        <TabsContent value="export" className="mt-3 flex flex-col gap-3">
          {doc.base_mask && (
            <Field label="Mode">
              <Select value={doc.mode} onValueChange={(v) => onChange({ ...doc, mode: v as MaskDoc["mode"] })}>
                <SelectTrigger className="h-8 w-full text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="union">union avec le masque de base</SelectItem>
                  <SelectItem value="replace">polygone seul</SelectItem>
                </SelectContent>
              </Select>
            </Field>
          )}
          <Separator />
          <Button onClick={onExport} data-testid="btn-export">
            <Download /> Exporter le masque
          </Button>
          <p className="text-xs text-muted-foreground">Le masque est ajouté au projet YABBE comme nouvel asset (jamais sur la timeline).</p>
          {status.text && (
            <Alert variant={status.kind === "error" ? "destructive" : "default"}>
              <AlertTitle>{status.kind === "error" ? "Erreur" : "État"}</AlertTitle>
              <AlertDescription>{status.text}</AlertDescription>
            </Alert>
          )}
        </TabsContent>
      </Tabs>
    </Panel>
  )
}
