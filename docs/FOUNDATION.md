# Cypress Forge Network Dashboard

**Status:** Repository foundation / planning baseline. No functional collector, API, or frontend has been verified or included.

Independent, vendor-neutral, read-only network monitoring and topology dashboard. First target: OpenWrt on a repurposed Meraki MX64. Future adapters may support SNMP/LLDP and other vendor APIs.

## Goals
- Responsive dashboard for desktop and Android phone.
- Normalize devices, interfaces, links, metrics, and events across vendors.
- Distinguish **observed**, **inferred**, and **manual** topology links.
- Local-first, free/open-source, private development.
- Keep router configuration unchanged during the existing stability observation.

## Proposed stack (not yet implemented)
React + TypeScript frontend; Python FastAPI backend; SQLite for early history; pluggable collectors; SSH/ubus OpenWrt adapter initially. Future SNMP/LLDP integration subject to device capabilities.

## Security
- Private repository; never commit passwords, SSH private keys, secrets, device inventories, or real addresses.
- Collectors must default to read-only and least privilege; avoid storing root credentials.
- Bind dev API to 127.0.0.1; phone access requires a separately reviewed authentication and LAN exposure design.
- No router-side installation or settings changes without explicit approval.
- No intrusive discovery scans during the baseline observation.

## Repository contents
- `docs/`: decisions, milestones, baseline (sanitized), security and handoff.
- `examples/`: synthetic sample topology and configuration.
- `frontend/`, `backend/`, `collectors/`, `database/`, `tests/`: placeholders for future verified implementation.

## Next steps
1. Import verified code from the separate Work session, after inspecting files for secrets and unintended changes.
2. Add a documented local startup workflow and automated tests.
3. Validate read-only SSH authentication and allowed commands on OpenWrt.
4. Implement normalized inventory, device status, and metrics; test with synthetic fixtures first.
5. Implement topology and mobile responsive UI.
6. Design secure authenticated LAN phone access; do not simply expose a development server.

See `docs/DECISIONS.md`.
