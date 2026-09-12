# Contributing

## Local development

```sh
./dev.sh
```

Starts the backend (`:8100`) and frontend (`:5273`) with hot reload. See the
[README](README.md#local-development) for details, including first-run env
file setup.

## Before opening a PR

Run the checks for whatever you touched — these mirror
[`.github/workflows/ci.yml`](.github/workflows/ci.yml) exactly, so a clean
local run means CI should pass too.

**backend/** (`cd backend`):

```sh
uv sync
uv run ruff check .
uv run mypy
uv run pytest
```

**frontend/** (`cd frontend`):

```sh
npm ci
npm run lint
npm run check
npm run test
npm run build
```

**android/** (`cd android`):

```sh
./check.sh
```

**apple/** (`cd apple`):

```sh
bash scripts/lint.sh
bash scripts/test-kit.sh
bash scripts/test-app.sh ios
bash scripts/test-app.sh tv
```

## Opening a PR

- `main` is protected: PRs require passing status checks before merging.
- PRs are squash-merged, so write a clear PR title/description — it becomes
  the commit message.
- Keep PRs scoped to one component/change where possible; see
  [`ROADMAP.md`](ROADMAP.md) and [`TODO.md`](TODO.md) for planned work if
  you're looking for something to pick up.

## Reporting bugs / requesting features

Use the issue templates. For security issues, see
[`SECURITY.md`](SECURITY.md) instead of opening a public issue.
