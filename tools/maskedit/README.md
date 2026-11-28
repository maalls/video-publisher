# maskedit (prototype)

Keyframed polygon mask editor. You place a polygon on a few keyframes, drag its points, and the
points are interpolated linearly between keyframes. The mask is exported as a black/white mp4
(white = inside), optionally merged (union) with an existing mask.

- `src/core.ts`: pure TypeScript, no dependency, no DOM (keyframes, point interpolation, validation). Tests: `npm test`.
- `src/MaskEditor.tsx`: React component, an SVG overlay on a video frame. No network.
- `src/main.tsx` + `web/index.html`: page glue (load/save the document, export button).
- `server.py`: tiny local backend (frames, document, mask export). Listens on 127.0.0.1 only.

## Document format (JSON, version 1)

    {"version":1,"clip":"name.mp4","fps":16,"size":[832,480],"frames":64,
     "keyframes":[{"frame":0,"points":[[x,y],...]},{"frame":21,"points":[[x,y],...]}],
     "mode":"union","base_mask":"base.mp4"}

Coordinates are normalised 0..1. All keyframes have the same number of points, in the same order.

## Run

    MASKEDIT_SOURCE=/path/video.mp4 MASKEDIT_BASE=/path/base-mask.mp4 python3 server.py
    # build the page: npm run build (needs react, vite, @vitejs/plugin-react)

## Integrating in an editor later

Import `core.ts` and `MaskEditor.tsx` in the editor, keep the document next to the clip, and replace
`server.py` export by the editor's own asset route. The server has no login: always put it behind
a reverse proxy that checks the user's session.
