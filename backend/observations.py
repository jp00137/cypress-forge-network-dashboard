"""Evidence-based differences. Missing observations are never called offline."""
def changes(before, after):
    if not before or not after:
        return []
    result = []

    def emit(kind, subject, message, severity='info'):
        result.append(dict(kind=kind, subject=subject, message=message, severity=severity))

    a, b = before['router'], after['router']
    if b['uptime'] < a['uptime']:
        emit('router_reboot', 'router', 'Router uptime decreased; a reboot or uptime reset was observed.', 'warning')
    if a.get('release') != b.get('release'):
        emit('firmware_changed', 'router', f"Firmware changed: {a.get('release')} → {b.get('release')}.", 'warning')
    old = {c['mac']: c for c in before['clients']}
    new = {c['mac']: c for c in after['clients']}
    for mac in new.keys() - old.keys():
        emit('device_observed', mac, f"{new[mac]['name']} appeared in router records ({new[mac]['ip']}).")
    for mac in old.keys() - new.keys():
        emit('device_missing', mac, f"{old[mac]['name']} is absent from this observation; connectivity is unknown.")
    for mac in old.keys() & new.keys():
        if old[mac]['ip'] != new[mac]['ip']:
            emit('address_changed', mac, f"IP changed: {old[mac]['ip']} → {new[mac]['ip']}.")
    old = {i['name']: i for i in before['interfaces']}
    new = {i['name']: i for i in after['interfaces']}
    for name in new.keys() - old.keys():
        emit('interface_added', name, 'Logical interface appeared in OpenWrt records.')
    for name in old.keys() - new.keys():
        emit('interface_removed', name, 'Logical interface is no longer reported.', 'warning')
    for name in old.keys() & new.keys():
        a, b = old[name], new[name]
        if a['up'] != b['up']:
            emit('interface_up' if b['up'] else 'interface_down', name,
                 'Logical interface is now ' + ('up.' if b['up'] else 'down.'), 'info' if b['up'] else 'warning')
        if a.get('addresses') != b.get('addresses'):
            emit('interface_address', name, f"Addresses changed: {', '.join(a.get('addresses', [])) or 'none'} → {', '.join(b.get('addresses', [])) or 'none'}.")
        for key in ('rx_errors', 'tx_errors', 'rx_dropped', 'tx_dropped'):
            delta = b.get('counters', {}).get(key, 0) - a.get('counters', {}).get(key, 0)
            if delta > 0:
                emit('interface_errors', name, f'{key}: {delta} additional packets since prior observation.', 'warning')
    old_ports = {p['name']: p for p in before.get('ports', [])}
    for port in after.get('ports', []):
        prior = old_ports.get(port['name'])
        if not prior:
            continue
        if prior.get('carrier') is not None and port.get('carrier') is not None and prior['carrier'] != port['carrier']:
            emit('port_link_up' if port['carrier'] else 'port_link_down', port['name'],
                 'OpenWrt port carrier ' + ('detected.' if port['carrier'] else 'lost.'), 'info' if port['carrier'] else 'warning')
        if prior.get('carrier') is True and port.get('carrier') is True:
            if prior.get('speed_mbps') is not None and port.get('speed_mbps') is not None and (prior['speed_mbps'], prior.get('duplex')) != (port['speed_mbps'], port.get('duplex')):
                emit('port_speed_changed', port['name'], f"Negotiated link changed: {prior['speed_mbps']} Mbps {prior.get('duplex')} → {port['speed_mbps']} Mbps {port.get('duplex')}.", 'warning')
        for key in ('rx_errors', 'tx_errors', 'rx_dropped', 'tx_dropped'):
            delta = port.get('counters', {}).get(key, 0) - prior.get('counters', {}).get(key, 0)
            if delta > 0:
                emit('port_errors', port['name'], f'{key}: {delta} additional packets since prior observation.', 'warning')
    return result
