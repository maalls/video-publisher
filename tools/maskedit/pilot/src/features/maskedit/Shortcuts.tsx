import { Panel } from "@/components/app/Panel"

const KEYS: [string, string][] = [
  ["← / →", "image précédente / suivante (maintenir : répétition régulière)"],
  ["Suppr", "supprime le point sélectionné, sinon la clé courante"],
  ["Appui long dans le polygone", "déplace toute la forme"],
  ["H", "masquer / afficher le tracé"],
  ["Ctrl/Cmd + Z, Maj + Z", "annuler, rétablir"],
]

/** Bottom panel: keyboard help. */
export function Shortcuts() {
  return (
    <Panel title="Raccourcis">
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
        {KEYS.map(([k, d]) => (
          <div key={k} className="contents">
            <dt>
              <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-xs">{k}</kbd>
            </dt>
            <dd className="text-muted-foreground">{d}</dd>
          </div>
        ))}
      </dl>
    </Panel>
  )
}
