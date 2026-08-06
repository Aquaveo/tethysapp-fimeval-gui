# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working Style

**Always check with the user before making any edits to files.** Describe what you plan to change and wait for confirmation before proceeding. Only change exactly what was asked — do not add, remove, or reformat anything beyond the explicit request.

**When staging files for a commit, always use `git add .`** instead of adding files individually.

**Ticket numbering — never invent FIMEVAL-BE*/FE* numbers.** The issue tracker (not this repo) is the sole source of truth for ticket numbers, and Claude has no access to it. Before assigning ANY new ticket number: (1) consult the authoritative registry (Claude's memory `reference_ticket_registry.md`, mirrored in `docs/tickets/backlog.md`), and (2) ask the user for the next free number from the tracker. Guessing sequential numbers has repeatedly collided with real tickets (e.g. FE14, BE19). Numbers assigned without the user confirming them from the tracker are provisional.

## Repository Layout

The repository root contains:
```
├── pyproject.toml
├── install.yml                  # Tethys + conda deps
├── reactapp/                    # React/TypeScript frontend (Vite)
│   └── src/
│       ├── main.tsx             # React entry point
│       └── App.tsx              # Root component, top-level state
└── tethysapp/fimeval_gui/
    ├── app.py                   # TethysAppBase config + custom settings
    ├── controllers.py           # Two endpoints: home (SPA) + tile_proxy
    ├── templates/fimeval_gui/index.html
    ├── public/frontend/         # ← Vite build output goes here
    ├── scripts/                 # Utility scripts (download, tile gen, COG conversion)
    └── tests/tests.py
```

## Commands

All backend commands assume an active Tethys conda environment.

### Backend

```bash
# Install app in development mode
tethys install -d

# Run development server (port 8000)
tethys manage start

# Run all tests
tethys manage test tethysapp/fimeval_gui/tests

# Run a single test method
tethys manage test tethysapp/fimeval_gui/tests.TestCase.test_home_controller
```

### Frontend

```bash
cd reactapp

npm install

# Dev server (port 5173, proxies /apps to localhost:8000)
npm run dev

# Production build → outputs to ../tethysapp/fimeval_gui/public/frontend/
npm run build

# Type check
npx tsc -b

# Lint
npm run lint
```

## Architecture

This is a **Tethys Platform 4** app (Django-based) with a React SPA frontend. There is no database ORM or user authentication—it is a read-only data visualization tool.

### Request Flow

1. Any request to `/apps/fimeval-gui/**` hits the `home()` controller (configured `catch_all=True`)
2. Django renders `index.html`, which loads the Vite-built React bundle from `public/frontend/`
3. React fetches the FIM catalog JSON from MinIO (`http://127.0.0.1:9000/fimbench/FIM_Viz/catalog_core.json`)
4. Map vector tiles are fetched via the `tile_proxy()` controller (`/apps/fimeval-gui/tile-proxy/{z}/{x}/{tile}`), which proxies to MinIO and forwards gzip-compressed MVT tiles
5. The table displays catalog metadata and direct MinIO download links for GeoTIFF and JSON files

### Frontend State (App.tsx)

State lives in `App.tsx` and flows down via props:
- **filters** (tiers, date range, return period) → `FilterSidebar`
- **visibleFeatures** (catalog records passing filters) → `Map` + `FIMTable`
- **selectedFeature** (clicked map feature) → `Map` + `FIMTable`

### Backend Key Points

- **`app.py`**: `TethysAppBase` subclass. Custom settings (`s3_allowed_host`, `s3_bucket_url`, `s3_catalog_key`, `s3_viz_tiles`) are accessed via `App.get_app().get_custom_setting(name)`.
- **`controllers.py`**: Only two controllers. `tile_proxy()` forwards gzip-compressed MVT tiles from MinIO; returns HTTP 204 for upstream 404s (MapLibre-compatible).
- No Django models are defined.

### Dev Environment Ports

| Service | Port |
|---------|------|
| Tethys/Django | 8000 |
| Vite dev server | 5173 |
| MinIO (S3-compatible) | 9000 |

Vite's dev proxy (`vite.config.ts`) forwards `/apps` → `http://127.0.0.1:8000`, so the React dev server can talk to the Tethys backend without CORS issues.

### Map Layer Configuration

Vector tile layers in `Map.tsx` use tier-based colors with zoom-level crossfade (zoom 7–8):
- Tier_1: `#E74C3C` (red), Tier_2: `#F39C12` (orange), Tier_3: `#2ECC71` (green), Tier_4: `#9B59B6` (purple), HWM: `#EC6FA3` (pink)

Basemap options: Street, Topographic, Satellite (ESRI sources).
