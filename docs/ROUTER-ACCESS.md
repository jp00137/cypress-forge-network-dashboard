# Connecting the dashboard to an OpenWrt router

One command, run once from the project folder. In PowerShell on Windows:

```powershell
.\scripts\connect-router.ps1
```

or in a terminal on Linux:

```sh
./scripts/connect-router.sh
```

On Linux the key is created in `~/.ssh/cypress_forge_collector` instead of `%USERPROFILE%\.ssh\`. Each computer gets
its own collector key: connecting a second computer adds a second entry and leaves the first one working.

It walks through five steps:

1. **Router address.** Defaults to this PC's gateway.
2. **Dashboard key.** Creates `%USERPROFILE%\.ssh\cypress_forge_collector` (ed25519). It has no passphrase so the dashboard can run unattended, and it cannot do anything except the dashboard's reads (step 3).
3. **Router install.** Opens one SSH session with your router password (typed into SSH, never stored) and runs a generated installer that:
   - adds a gate script at `/etc/dropbear/cypress-forge-readonly.sh` that accepts only the exact read requests this app version sends and refuses everything else (exit 126);
   - adds the key to `/etc/dropbear/authorized_keys` with `command=` (forced to the gate), `no-pty`, `no-port-forwarding`, `no-agent-forwarding`, `no-X11-forwarding`;
   - keeps every existing key, backs up what it changes to `/etc/dropbear/cypress-forge-backup.*`, and changes no firewall, network, password or service settings.
   Re-running it is safe. A newer app version re-runs it to update the gate.
4. **Settings.** Writes `config.local.json` in live mode (previous copy saved as `config.local.json.bak`).
5. **Verify.** Status, ports, firewall and DHCP reads must pass, and an arbitrary command (`id`) must be refused.

The gate and the collector are generated from the same command tables in `backend/`, so they cannot drift apart.

## Revoke access

```powershell
.\.venv\Scripts\python.exe -m backend.cli router-remover --pubkey "$env:USERPROFILE\.ssh\cypress_forge_collector.pub" --out remove.sh
cmd /c "ssh root@192.168.1.1 sh -s < remove.sh"
```

Only the dashboard key is removed; other access entries stay.

## Troubleshooting

`.\.venv\Scripts\python.exe -m backend.cli diagnose` runs one collection and prints the real SSH error (key path hidden). Nothing is stored.
