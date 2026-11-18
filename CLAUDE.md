# CLAUDE.md

Notes for Claude (and anyone else) working in this repo. See `README.md` for the folder map and
`STATUS.md` for where the project stands.

## Project

D.I.R.T.T. (Digital Instrument for Remote Terrain Testing), "Dirty Dawgs", Mississippi State
University ECE senior capstone, 2026. An autonomous, mostly solar-powered rover that drives to
GPS grid points, pushes a 4-in-1 soil probe into the ground, and radios pH / EC / temperature /
moisture back to a base station over LoRa. Budget: $1,000.

| Person | Role |
|---|---|
| Nolan Brechtel | Project Manager, Navigation lead (repo owner, `ndbre`) |
| George Utz | Chief Scientist, Power and Charging lead |
| Cara Belew | Data Backup and Control lead |
| Zachary Morrow | Soil Sensing lead |
| Rebecca Ueltschey | Drivetrain and Chassis lead |
| Dr. Christopher Hudson | Faculty advisor |

Nolan prefers direct, colleague-to-colleague feedback: if something is wrong, say so.

## The website (`website/`)

- Live at https://dirtt.ndbre.com (Cloudflare Pages, production branch `master`, output
  directory `website`). Every push to another branch gets a preview deployment.
- Plain static HTML/CSS/JS, no framework, no build step, plus one small Pages Function for
  `docs/`. Keep it that way unless asked.
- Content is data in `website/content/*.js` (`devlogEntries`, `deliverableGroups`,
  `teamMembers`), rendered by `website/assets/script.js`. Home and About text is in `index.html`.
- Deliverables: every file (any size) goes in `docs/<TYPE>/<YYYY-MM-DD>_<TYPE>.<ext>` at the
  repo root, then one line in `website/content/deliverables.js`. The href (`docs/...`) is built
  from folder + date + format.
- Devlog attachments go in `website/devlog/<YYYY-MM-DD>/`. Avoid spaces in filenames.
- `docs/` isn't part of the deploy. `functions/docs/[[path]].js` (a Pages Function) serves
  `/docs/<path>` by fetching it from raw.githubusercontent.com and setting the Content-Type, so
  there's no 25 MiB limit and PDFs still embed. A file only appears on the live site once it is
  on `master` (branch previews read their own branch).
- `website/_redirects` keeps the old top-level URLs (`/FDR/...`, `/Team/...`, `/Site/...`)
  working after the November 2026 cleanup. If you move a published file, add a redirect.
- Deliverable PDFs are graded submissions. Don't edit, rename or delete them without asking.
- Check changes locally (`python3 -m http.server` in `website/` + Playwright) and on the PR's
  Cloudflare preview before merging.

## Rest of the repo

- `cad/` CAD by subsystem, `code/` software (navigation sim etc.), `datasheets/` by subsystem.
  None of it is published. Only `docs/` is reachable through the site.
- Generated files (PDF drawings, STEP/GLB exports, renders) come from scripts; regenerate them
  rather than hand-editing.

## Git

- Work on a branch and open a PR to `master`; Nolan merges. Don't push to `master` directly.
- The website is due for graded reviews at times; don't change it right before a deadline
  unless asked.
