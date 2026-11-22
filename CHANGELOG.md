# v0.3.1 — November 22, 2026

The app carries the product name: the sidebar reads "CF Network Dashboard" with the CF emblem (it follows the accent colour), the tab title is "CF Network Dashboard" with the emblem as its icon, and the demo router is "OpenWrt router". The launcher recognises both the new and the old title. The README notes that the names and the emblem are not covered by the MIT license.

# v0.3.0 — November 22, 2026 (first public release)

Core colours are now CSS custom properties (`--cf-*`) in one token block, with no visible change: every colour stays within ΔE 3.5 of before. A test keeps literal colours out of the stylesheets and components. Add-ons can set `client = "file.js"` to have the dashboard import one script from their own folder; `/api/addons` lists it as `client`. Together these let an add-on recolour the dashboard (docs/THEME-SEAM.md, docs/ADDON-DESIGN.md). The free dashboard keeps its single dark look.

# v0.2 — November 14, 2026

Added an interactive port schematic with manual associations, device profiles, tags, notes, icons, recognition and attachment labels; a persistent device ledger and event timeline; observation comparisons; saved searches; local attention thresholds; CSV exports; validated workspace backup/restore; configurable database retention; a double-click launcher; nine backend tests and eight frontend tests.

Router collection remains six fixed read commands and disabled by default. Physical port identity is not inferred from `eth0` or bridge status. Port speed/duplex, firewall rules, NAT mappings, per-device bandwidth and mesh access-point attachment remain uncollected. No router, firewall or credential settings were changed.

Database migration adds `events` and `devices` tables and an index without removing the original snapshots table. Retained v0.1 snapshots seed the device ledger. Source rollback to v0.1 ignores the extra tables; a pre-update SQLite backup is also saved in `backups/`. v0.1 source baseline is unchanged. A separate v0.2 baseline archive is provided beside the project.

Local profiles are separate browser data: names/notes, manual topology, port associations, saved filters and alert preferences are scoped by mode and browser origin. Workspace export backs up these annotations; SQLite backup backs up observations/events/inventory. Restore validates field sizes, device identifiers, thresholds, mode and topology loops. CSV fields neutralize leading spreadsheet formula characters.
