// Plain JS so it runs under the core CSP (script-src 'self', no inline scripts).
async function load() {
  const summary = document.getElementById('summary');
  try {
    const res = await fetch('/api/addon/hello/stats');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const s = await res.json();
    const last = s.last_snapshot
      ? new Date(s.last_snapshot.timestamp * 1000).toLocaleString() + ', ' + s.last_snapshot.clients + ' clients'
      : 'none yet';
    summary.textContent = s.snapshots + ' snapshots seen (last: ' + last + '); ' + s.event_total + ' events.';
    const body = document.getElementById('events');
    body.replaceChildren();
    for (const [kind, count] of Object.entries(s.events)) {
      const row = body.insertRow();
      row.insertCell().textContent = kind;
      row.insertCell().textContent = count;
    }
  } catch (err) {
    summary.textContent = 'Could not load stats: ' + err.message;
  }
}
load();
setInterval(load, 30000);
