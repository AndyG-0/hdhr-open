# HDHR Open — frontend

SvelteKit (Svelte 5) frontend for HDHR Open — the guide, player, DVR/recording
management, and settings UI. Talks to the [backend](../backend/README.md)
over a REST API.

See the [root README](../README.md) for what this project is and how to run
it via Docker. This file covers frontend-specific local development.

## Requirements

- Node.js 22+
- npm

## Setup

```sh
cp .env.example .env   # edit as needed — see below
npm ci
npm run dev
```

The dev server listens on `:5173` by default and talks directly to the
backend at `PUBLIC_API_BASE_URL` (the backend's `CORS_ORIGIN` must allow it —
see `backend/.env.example`).

### Environment variables

- `PUBLIC_API_BASE_URL` — base URL of the backend API (e.g.
  `http://localhost:8000` for local dev). See `.env.example`.

## Building

```sh
npm run build
npm run preview   # preview the production build locally
```

## Checks

```sh
npm run lint          # eslint
npm run check         # svelte-check (types)
npm run format:check  # prettier
npm run test          # vitest, single run
npm run test:watch    # vitest, watch mode
```

`npm run format` applies Prettier fixes in place.

## Layout

- `src/lib/api.ts` — typed client for the backend REST API; almost every
  component goes through this rather than calling `fetch` directly.
- `src/lib/components/` — UI components, including `HDHomeRunPlayer.svelte`
  (the video player) and the `details/`, `player/`, and `settings/`
  subdirectories for their respective feature areas.
- `src/lib/stores/` — Svelte stores for shared client-side state.
- `src/lib/i18n/` — `svelte-i18n` setup and translation strings.
- `src/lib/*-controller.ts` — feature-specific browser integrations (AirPlay,
  captions, SyncPlay) kept separate from their components for testability.
- `src/routes/` — SvelteKit pages.
