"""Parse committed UCI configuration without executing file contents."""
import shlex


def parse_uci(text):
    sections, current = [], None
    for number, line in enumerate(text.splitlines(), 1):
        parts = shlex.split(line, comments=True, posix=True)
        if not parts:
            continue
        if parts[0] == 'config' and len(parts) in (2, 3):
            current = dict(id=f'section-{len(sections)}', order=len(sections) + 1,
                           type=parts[1], name=parts[2] if len(parts) == 3 else '', options={})
            sections.append(current)
        elif current and parts[0] in ('option', 'list') and len(parts) == 3:
            key, value = parts[1:]
            if parts[0] == 'list':
                old = current['options'].setdefault(key, [])
                if not isinstance(old, list):
                    raise ValueError(f'Mixed list/option at line {number}')
                old.append(value)
            else:
                current['options'][key] = value
        else:
            raise ValueError(f'Unsupported configuration syntax at line {number}')
    if not sections:
        raise ValueError('Configuration has no sections')
    for section in sections:
        options = section['options']
        enabled = options.get('enabled', '1')
        section['enabled'] = False if enabled in ('0', 'false', 'no', 'off') else True if enabled in ('1', 'true', 'yes', 'on') else None
        section['label'] = options.get('name') or section['name'] or f"{section['type']} #{section['order']}"
    return sections


