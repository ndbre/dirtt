# D.I.R.T.T.

Digital Instrument for Remote Terrain Testing: an autonomous, mostly solar-powered soil-screening rover.
Mississippi State University capstone, 2026.

Team site: https://dirtt.ndbre.com

## Layout

| Folder | What's in it | Published on the site? |
|---|---|---|
| `website/` | The team website (HTML/CSS/JS, deliverables, devlog, team) | **Yes**: Cloudflare Pages publishes only this folder |
| `cad/` | CAD files: drivetrain and chassis, soil sensing, jigs, mounts | No |
| `code/` | Rover and base-station code | No |
| `datasheets/` | Component data and spec sheets, by subsystem | No |
| `docs/` | Every deliverable, `docs/<TYPE>/<YYYY-MM-DD>_<TYPE>.<ext>`, any size | Served at `/docs/...` from GitHub by `functions/` |
| `functions/` | Cloudflare Pages Function that serves `docs/` on the site | Runs on Cloudflare |

### Inside `website/`

| Path | What it is | Who edits it |
|---|---|---|
| `index.html` | Page layout and the Home / About text | Occasionally |
| `content/devlog.js` | Devlog entries | Often |
| `content/deliverables.js` | Deliverables cards (instructions at the top) | Every deliverable |
| `content/team.js` | Team members | Rarely |
| `devlog/<YYYY-MM-DD>/` | Images, models and files used by a devlog entry | With devlog entries |
| `assets/` | Stylesheet, script, logo/site images, team photos | Rarely |
| `_redirects` | Keeps pre-cleanup URLs (e.g. `/FDR/...`) working | Rarely |

`dirtt-files` was merged into this repo (with its history) on 2026-11-18. That repo can be archived or deleted.

## Cloudflare Pages settings

- Production branch: `master`
- Build command: *(none)*
- Build output directory: `website`

Pages only publishes `website/`, and rejects files over 25 MiB. Deliverables therefore live in
`docs/`, and `functions/docs/[[path]].js` serves them at `dirtt.ndbre.com/docs/...` by fetching
them from GitHub (master, or the branch for a `<branch>.dirtt.pages.dev` preview) with the right
file type, so PDFs still preview in the page. Nothing in `docs/` counts against the 25 MiB limit.
