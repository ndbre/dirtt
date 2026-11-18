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
| `docs/` | Large documents that can't go on the site (e.g. the 53 MB FDR deck) | No: linked from the site via GitHub |

`dirtt-files` was merged into this repo (with its history) on 2026-11-18. That repo can be archived or deleted.

## Cloudflare Pages settings

- Production branch: `master`
- Build command: *(none)*
- Build output directory: `website`

Pages rejects any single file over 25 MB. Keep big files outside `website/` (for example in `docs/`)
and link to them as `https://github.com/ndbre/dirtt/raw/refs/heads/master/<path>`.
