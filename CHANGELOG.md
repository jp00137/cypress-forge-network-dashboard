# v0.4.0 — November 22, 2026

Linux support (tested on Debian 13). New shell scripts mirror the PowerShell ones: `scripts/setup.sh`, `start.sh`, `test.sh` and `connect-router.sh` (the same guided, read-only router connection). The optional `install-service.sh` and `uninstall-service.sh` run the dashboard as a systemd user service. A GitHub Actions workflow runs every test on Linux, router-gate tests included. Node.js 20.19+ is now accepted (Vite 7 needs 20.19+ or 22.12+). Shell scripts are kept with LF line endings by `.gitattributes`. See docs/LINUX-SUPPORT.md.

# v0.3.3 — November 22, 2026

The page subtitle reads "CF Network Dashboard / Home network" instead of "Cypress Forge / Home network". The README shows screenshots (demo data), and new issues get a short template asking for router model, OpenWrt version and app version.

# v0.3.2 — November 22, 2026

The sidebar footer reads "CF NETWORK DASHBOARD" with the app version, now taken from `frontend/package.json` (0.3.2) instead of a hard-coded "v0.2".

# v0.3.1 — November 22, 2026

The app carries the product name: the sidebar reads "CF Network Dashboard" with the CF emblem (it follows the accent colour), the tab title is "CF Network Dashboard" with the emblem as its icon, and the demo router is "OpenWrt router". The launcher recognises both the new and the old title. The README notes that the names and the emblem are not covered by the MIT license.

# v0.3.0 — November 22, 2026 (first public release)

Core colours are now CSS custom properties (`--cf-*`) in one token block, with no visible change: every colour stays within ΔE 3.5 of before. A test keeps literal colours out of the stylesheets and components. Add-ons can set `client = "file.js"` to have the dashboard import one script from their own folder; `/api/addons` lists it as `client`. Together these let an add-on recolour the dashboard (docs/THEME-SEAM.md, docs/ADDON-DESIGN.md). The free dashboard keeps its single dark look.

# v0.2 — November 14, 2026

Added an interactive port schematic with manual associations, device profiles, tags, notes, icons, recognition and attachment labels; a persistent device ledger and event timeline; observation comparisons; saved searches; local attention thresholds; CSV exports; validated workspace backup/restore; configurable database retention; a double-click launcher; nine backend tests and eight frontend tests.

Router collection remains six fixed read commands and disabled by default. Physical port identity is not inferred from `eth0` or bridge status. Port speed/duplex, firewall rules, NAT mappings, per-device bandwidth and mesh access-point attachment remain uncollected. No router, firewall or credential settings were changed.

Database migration adds `events` and `devices` tables and an index without removing the original snapshots table. Retained v0.1 snapshots seed the device ledger. Source rollback to v0.1 ignores the extra tables; a pre-update SQLite backup is also saved in `backups/`. v0.1 source baseline is unchanged. A separate v0.2 baseline archive is provided beside the project.

Local profiles are separate browser data: names/notes, manual topology, port associations, saved filters and alert preferences are scoped by mode and browser origin. Workspace export backs up these annotations; SQLite backup backs up observations/events/inventory. Restore validates field sizes, device identifiers, thresholds, mode and topology loops. CSV fields neutralize leading spreadsheet formula characters.
