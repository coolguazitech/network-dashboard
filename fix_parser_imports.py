#!/usr/bin/env python3
"""Fix parser imports - replace register_parser with proper registration."""

import re
from pathlib import Path

files_to_fix = [
    "app/parsers/plugins/ping.py",
    "app/parsers/plugins/hpe_fan.py",
    "app/parsers/plugins/cisco_nxos_fan.py",
    "app/parsers/plugins/hpe_error.py",
    "app/parsers/plugins/cisco_nxos_error.py",
    "app/parsers/plugins/hpe_power.py",
    "app/parsers/plugins/cisco_nxos_power.py",
    "app/parsers/plugins/hpe_port_channel.py",
]

for file_path in files_to_fix:
    path = Path(file_path)
    if not path.exists():
        print(f"Skipping {file_path} - not found")
        continue

    content = path.read_text()

    # Replace import lines
    content = re.sub(
        r'from app\.parsers\.protocols import BaseParser, ([^,\n]+), register_parser',
        r'from app.parsers.protocols import BaseParser, \1\nfrom app.parsers.registry import parser_registry',
        content
    )

    # Remove @register_parser decorator
    content = re.sub(r'@register_parser\n', '', content)

    # Find all parser classes
    parser_classes = re.findall(r'^class (\w+Parser)\(BaseParser', content, re.MULTILINE)

    # Check if already has registration
    if 'parser_registry.register' not in content and parser_classes:
        # Add registration at the end
        registration = '\n\n# Register parsers\n'
        for class_name in parser_classes:
            registration += f'parser_registry.register({class_name}())\n'
        content += registration

    # Write back
    path.write_text(content)
    print(f"✅ Fixed {file_path} - registered {len(parser_classes)} parsers")

print("\n✅ All files fixed!")
