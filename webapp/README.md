# ComfySprites webapp

FastAPI app for designing sprites and running Make Lab generation via ComfyUI.

## Layout

```
webapp/
├── main.py              # App entry, static mounts, route registration
├── config.py            # Paths (dataset, uploads, outputs) and repo URLs
├── env_settings.py      # ComfyUI base URL from .env / settings page
├── revision.py          # Asset cache-bust revision for static files
├── asyncio_compat.py    # Client-disconnect noise suppression
│
├── make/                # Make Lab product constants
│   ├── limits.py        # Image count, upscale/refine defaults
│   └── preview.py       # Preview dimension helpers
│
├── api/                 # JSON REST under /api/*
├── routes/pages/        # HTML page handlers
├── db/                  # SQLAlchemy models, session, JSON seed defaults
├── services/
│   ├── sdxl/            # Prompt composition, segments, tag enforcement
│   ├── catalog/         # Dataset-backed catalogs (styles, controlnets, …)
│   ├── design/          # Characters, inline outfit tags, forms, animation fields
│   ├── generations.py   # Photo output persistence + gallery metadata
│   └── validate.py      # Pre-flight validation helpers
│
├── comfyui/
│   ├── make_lab/        # Make Lab pipeline stages (detailers, controlnet, …)
│   ├── workflow.py      # Build + patch ComfyUI API workflows
│   ├── workflow_builder.py
│   ├── generate.py      # Queue jobs, asset preflight
│   ├── client.py        # ComfyUI HTTP/WS client
│   ├── jobs.py          # In-memory job store
│   └── workflows/       # Node JSON, registry, recipes (see workflows/README.md)
│
├── static/make/         # Make Lab CSS + JS modules
└── templates/           # Jinja2 HTML
```

## Conventions

- **Make Lab** — user-facing generation UI (`/make`); ComfyUI workflow code lives under `comfyui/make_lab/`.
- **Dataset JSON** — shipped defaults in `dataset/` at repo root; copied into workspace on first run.
- **Tests** — `test/` at repo root; pytest boots an isolated DB via `test/conftest.py`.
