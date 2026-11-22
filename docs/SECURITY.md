# Security and deployment guardrails

1. No WAN-facing dashboard, port forwards, or public endpoints by default.
2. Development servers listen on loopback only. Mobile LAN access requires authentication, authorization, TLS strategy, and firewall review.
3. Collectors use read-only protocols/commands and minimum privileges. Verify SSH authentication before collection; never embed passwords or private keys in code.
4. Never commit device inventories, MAC addresses, private IPs from real deployments, tokens, backup configs, or logs with secrets.
5. Rate-limit polling and discovery. Avoid invasive scanning, particularly during the MX64 stability observation.
6. Distinguish discovered data from manually entered assumptions. Track collection timestamps and provenance.
7. Maintain rollback and backups for application deployments; no router modifications are in scope.
8. Before commercial release, audit dependency licenses, security updates, and multi-tenant isolation requirements.
