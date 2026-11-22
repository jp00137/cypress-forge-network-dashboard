# Cypress Forge - connect to your OpenWrt router (one-time, guided).
# Creates a dedicated read-only dashboard key, installs it on the router over one
# password SSH session (the password is typed into SSH, never stored), writes
# config.local.json and verifies everything. Re-running it is safe.
param(
    [string]$Router = '',
    [string]$User = 'root',
    [string]$KeyName = 'cypress_forge_collector'
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$py = '.\.venv\Scripts\python.exe'
if (!(Test-Path $py)) { throw 'Run scripts\setup.ps1 first.' }
if (!(Get-Command ssh -ErrorAction SilentlyContinue)) {
    throw 'Windows OpenSSH client not found. Settings > System > Optional features > add "OpenSSH Client".'
}

function Step($n, $text) { Write-Host ""; Write-Host "[$n/5] $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "  OK  $text" -ForegroundColor Green }
function Fail($text) { Write-Host "  !!  $text" -ForegroundColor Red; exit 1 }

Write-Host 'Cypress Forge router connection' -ForegroundColor White
Write-Host 'This adds ONE read-only key to your router. No firewall, network, password or service changes.'

# 1. Router address
Step 1 'Router address'
if (!$Router) {
    $gw = (Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway } | Select-Object -First 1).IPv4DefaultGateway.NextHop
    if (!$gw) { $gw = '192.168.1.1' }
    $answer = Read-Host "  Router IP [$gw]"
    $Router = if ($answer) { $answer.Trim() } else { $gw }
}
if (!(Test-Connection $Router -Count 2 -Quiet)) { Fail "No answer from $Router. Check the address and that this PC is on the router's network." }
Ok "$Router answers"

# 2. Dedicated key (no passphrase: it can only run the dashboard's fixed reads)
Step 2 'Dashboard key'
$sshDir = Join-Path $env:USERPROFILE '.ssh'
$key = Join-Path $sshDir $KeyName
if (Test-Path "$key.pub") {
    Ok "Using existing key $KeyName"
} else {
    New-Item -ItemType Directory -Force $sshDir | Out-Null
    $p = Start-Process ssh-keygen -ArgumentList "-q -t ed25519 -N `"`" -C `"Cypress Forge collector`" -f `"$key`"" -NoNewWindow -Wait -PassThru
    if ($p.ExitCode -ne 0 -or !(Test-Path "$key.pub")) { Fail 'Could not create the key.' }
    Ok "Created $KeyName (private half stays in your .ssh folder)"
}

# 3. Install on the router (password typed into SSH once)
Step 3 'Install read-only access on the router'
$installer = Join-Path $env:TEMP 'cypress-forge-router-install.sh'
& $py -m backend.cli router-installer --pubkey "$key.pub" --out $installer | Out-Null
if ($LASTEXITCODE -ne 0) { Fail 'Could not prepare the router installer.' }
Write-Host "  SSH will connect to $User@$Router."
Write-Host '  - If asked to confirm the router''s fingerprint, compare it with LuCI (System > Administration > SSH Keys) or answer yes on a network you trust.'
Write-Host '  - Then type the router password. It is not shown or saved.'
cmd /c "ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password,keyboard-interactive -o StrictHostKeyChecking=ask $User@$Router sh -s < `"$installer`""
$code = $LASTEXITCODE
Remove-Item $installer -ErrorAction SilentlyContinue
if ($code -eq 2) { Fail 'This key already has a different entry on the router. Nothing was changed; see README (Router access).' }
if ($code -ne 0) { Fail 'Router install did not finish. Nothing in this PC''s config was changed.' }
Ok 'Router access installed'

# 4. Save settings
Step 4 'Save dashboard settings'
& $py -m backend.cli configure --host $Router --user $User --identity-file $key
if ($LASTEXITCODE -ne 0) { Fail 'Settings could not be saved.' }

# 5. Verify reads work and nothing else does
Step 5 'Verify'
$ErrorActionPreference = 'Continue'   # verification output arrives on stderr
$failed = $false
foreach ($check in 'verify-ports', 'verify-firewall', 'verify-dhcp', 'verify-locked') {
    $out = & $py -m backend.cli $check 2>&1
    if ($LASTEXITCODE -eq 0) { Ok ($out | Select-Object -First 1) } else { Write-Host "  !!  $check : $($out -join ' ')" -ForegroundColor Red; $failed = $true }
}
if ($failed) { Fail 'Some checks failed. Run:  .\.venv\Scripts\python.exe -m backend.cli diagnose' }

Write-Host ''
Write-Host 'All set. Start (or restart) the dashboard with Start Dashboard.cmd.' -ForegroundColor Green
Write-Host "To revoke access later:  $py -m backend.cli router-remover --pubkey `"$key.pub`" --out remove.sh  then run it on the router."
