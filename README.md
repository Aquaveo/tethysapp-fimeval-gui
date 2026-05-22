# tethysapp-fimeval-gui

Webapp GUI for [FIMeval](https://github.com/sdmlua/fimeval), the Flood Inundation
Mapping Predictions Evaluation Framework.

## Status

Scaffolding only. See `initial_proposal.md` for the design proposal and module
roadmap.

## Quick start

```bash
# Backend (from repo root)
tethys install -d
tethys manage start            # http://localhost:8000

# Frontend (separate terminal)
cd reactapp
npm install
npm run dev                    # http://localhost:5173 (proxies /apps to :8000)

# Production frontend build
cd reactapp
npm run build                  # outputs to ../tethysapp/fimeval_gui/public/frontend/
```

After `tethys install -d` and a frontend build, the app is served at
`http://localhost:8000/apps/fimeval-gui/`.

See `CLAUDE.md` for working-style guidance.
