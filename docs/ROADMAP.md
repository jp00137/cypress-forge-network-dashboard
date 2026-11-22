# Milestones

- M0 **Repository foundation:** private repo, architecture and security documents, synthetic examples.
- M1 **Data contracts:** typed vendor-neutral device/interface/link/metric/event schemas and fixtures.
- M2 **Read-only OpenWrt adapter:** authenticate, collect uptime, interfaces, leases and status; tests; no writes.
- M3 **Local API and persistence:** FastAPI + SQLite; migrations; retention policy; localhost only.
- M4 **Responsive UI:** status overview, inventory, interface metrics; Android viewport testing.
- M5 **Topology:** graph layout with observed/inferred/manual provenance; explicit Deco limitations.
- M6 **LAN phone access:** secure auth and controlled exposure after threat-model review.
- M7 **Second adapter:** SNMP/LLDP or another vendor to validate portability.
- M8 **Commercial readiness:** licensing, installer, documentation, security hardening and optional branding.
