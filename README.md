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

### Inside `website/`

| Path | What it is | Who edits it |
|---|---|---|
| `index.html` | Page layout and the Home / About text | Occasionally |
| `content/devlog.js` | Devlog entries | Often |
| `content/deliverables.js` | Deliverables cards (instructions at the top) | Every deliverable |
| `content/team.js` | Team members | Rarely |
| `deliverables/<TYPE>/` | Every deliverable file, named `<YYYY-MM-DD>_<TYPE>.<ext>` (including ones over 25 MB) | Every deliverable |
| `devlog/<YYYY-MM-DD>/` | Images, models and files used by a devlog entry | With devlog entries |
| `assets/` | Stylesheet, script, logo/site images, team photos | Rarely |
| `_redirects` | Keeps pre-cleanup URLs (e.g. `/FDR/...`) working | Rarely |

`dirtt-files` was merged into this repo (with its history) on 2026-11-18. That repo can be archived or deleted.

## Cloudflare Pages settings

- Production branch: `master`
- Build command: `find website -type f -size +25M -print -delete`
- Build output directory: `website`

Pages rejects any single file over 25 MiB. The build command drops those files from the deploy
(they stay in the repo), and the site links to them on GitHub instead: list the format under
`onGitHub` in `website/content/deliverables.js`. The links look like
`https://github.com/ndbre/dirtt/raw/refs/heads/master/website/deliverables/<TYPE>/<file>`.
