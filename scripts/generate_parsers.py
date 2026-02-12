#!/usr/bin/env python3
"""
Parser Skeleton Generator

Generate parser skeleton files based on successful API test results.
De-coupled from indicators - focuses on API names only.

Usage:
    python scripts/generate_parsers.py
    # or
    make gen-parsers
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

from jinja2 import Template
from rich.console import Console

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

console = Console()


# =============================================================================
# Parser Template
# =============================================================================

PARSER_TEMPLATE = '''"""
Parser for '{{api_name}}' API.

Auto-generated skeleton by scripts/generate_parsers.py.
Fill in the parse() method logic.

API Source: {{source}}
Endpoint: {{endpoint}}
Target: {{target_name}}
"""
from __future__ import annotations

{% if device_type_enum %}
from app.core.enums import DeviceType
{% endif %}
from app.parsers.protocols import BaseParser{% if parsed_data %}, {{parsed_data}}{% endif %}
{% for extra_import in extra_imports %}
from app.parsers.protocols import {{extra_import}}
{% endfor %}
from app.parsers.registry import parser_registry


class {{class_name}}(BaseParser{% if parsed_data %}[{{parsed_data}}]{% endif %}):
    """
    Parser for {{api_name}} API response.
{% if parsed_data_source %}

    Target data model ({{parsed_data}}):
    ```python
{{parsed_data_source}}
    ```
{% endif %}

    Raw output example from {{target_name}}:
    ```
{{example_raw_data}}
    ```
    """

    device_type = {{device_type_enum or 'None'}}
    command = "{{api_name}}"

    def parse(self, raw_output: str) -> list[{{parsed_data or 'dict'}}]:
        results: list[{{parsed_data or 'dict'}}] = []

        # TODO: Implement parsing logic

        return results


# Register parser
parser_registry.register({{class_name}}())
'''


# =============================================================================
# Utilities
# =============================================================================


def to_pascal_case(snake_str: str) -> str:
    """Convert snake_case to PascalCase.

    Examples:
        "get_fan_hpe" -> "GetFanHpe"
        "ping_batch" -> "PingBatch"
    """
    return "".join(word.capitalize() for word in snake_str.split("_"))


def find_latest_report(reports_dir: Path) -> Path | None:
    """Find the latest API test report."""
    reports = list(reports_dir.glob("api_test_*.json"))
    if not reports:
        return None
    return max(reports, key=lambda p: p.stat().st_mtime)


def _strip_docstrings(source: str) -> str:
    """Remove docstrings from class source to avoid triple-quote conflicts."""
    import ast as _ast
    import textwrap

    try:
        dedented = textwrap.dedent(source)
        tree = _ast.parse(dedented)
    except SyntaxError:
        return source

    lines = dedented.splitlines()

    # Collect line ranges to remove (docstring Expr nodes)
    ranges_to_remove: list[tuple[int, int]] = []
    for node in _ast.walk(tree):
        if isinstance(node, (_ast.ClassDef, _ast.FunctionDef, _ast.AsyncFunctionDef)):
            if (
                node.body
                and isinstance(node.body[0], _ast.Expr)
                and isinstance(node.body[0].value, (_ast.Constant, _ast.Str))
            ):
                doc_node = node.body[0]
                ranges_to_remove.append(
                    (doc_node.lineno - 1, doc_node.end_lineno)  # type: ignore
                )

    if not ranges_to_remove:
        return source

    # Remove docstring lines (reverse order to preserve indices)
    result_lines = list(lines)
    for start, end in sorted(ranges_to_remove, reverse=True):
        del result_lines[start:end]

    return "\n".join(result_lines)


def get_parsed_data_source(parsed_data_name: str | None) -> tuple[str, list[str]]:
    """Get source code of a ParsedData class and any referenced model classes.

    Returns:
        (source_code, extra_imports) — source indented for docstring,
        and list of additional class names that need importing.
    """
    if not parsed_data_name:
        return "", []

    try:
        from app.parsers import protocols

        cls = getattr(protocols, parsed_data_name, None)
        if cls is None:
            return "", []

        source = inspect.getsource(cls)
        # Strip docstrings — they break the outer docstring's triple-quotes
        source = _strip_docstrings(source)
        indented = "\n".join(f"    {line}" for line in source.splitlines())

        # Find referenced model classes (e.g., TransceiverChannelData)
        extra_imports: list[str] = []
        for _name, field_info in cls.model_fields.items():
            annotation = field_info.annotation
            # Unwrap list[], Optional[], etc.
            for arg in getattr(annotation, "__args__", []):
                if (
                    isinstance(arg, type)
                    and hasattr(protocols, arg.__name__)
                    and arg.__name__ != parsed_data_name
                    and issubclass(arg, protocols.BaseModel)
                ):
                    extra_imports.append(arg.__name__)
                    # Also include its source
                    extra_source = _strip_docstrings(inspect.getsource(arg))
                    extra_indented = "\n".join(
                        f"    {line}" for line in extra_source.splitlines()
                    )
                    indented = extra_indented + "\n\n" + indented

        return indented, extra_imports

    except Exception:
        return "", []


# =============================================================================
# Parser Generation
# =============================================================================


DEVICE_TYPE_ENUM_MAP: dict[str, str] = {
    "hpe": "DeviceType.HPE",
    "cisco_ios": "DeviceType.CISCO_IOS",
    "cisco_nxos": "DeviceType.CISCO_NXOS",
}


def generate_parser(
    api_name: str,
    target_name: str,
    source: str,
    endpoint: str,
    raw_data: str,
    output_dir: Path,
    device_type: str | None = None,
    parsed_data: str | None = None,
) -> Path | None:
    """Generate a single parser skeleton file."""
    # Generate class name
    class_name = to_pascal_case(api_name) + "Parser"

    # Generate filename
    filename = f"{api_name}_parser.py"
    output_path = output_dir / filename

    # Skip if file already exists
    if output_path.exists():
        console.print(f"  ⏭️  Skipped {filename} (already exists)")
        return None

    # Include full raw data so AI can understand the complete format
    example_raw_data = "\n".join(f"    {line}" for line in raw_data.splitlines())

    # Resolve device_type to enum expression
    device_type_enum = DEVICE_TYPE_ENUM_MAP.get(device_type or "")

    # Get ParsedData class source for docstring
    parsed_data_source, extra_imports = get_parsed_data_source(parsed_data)

    # Render template
    template = Template(PARSER_TEMPLATE)
    content = template.render(
        api_name=api_name,
        class_name=class_name,
        source=source,
        endpoint=endpoint,
        target_name=target_name,
        example_raw_data=example_raw_data,
        device_type_enum=device_type_enum,
        parsed_data=parsed_data,
        parsed_data_source=parsed_data_source,
        extra_imports=extra_imports,
    )

    # Write file
    with open(output_path, "w") as f:
        f.write(content)

    console.print(f"  ✅ Created {filename}")
    return output_path


def device_type_short(device_type: str) -> str:
    """Convert device_type to short form for parser naming.

    Examples:
        "hpe" -> "hpe"
        "cisco_ios" -> "ios"
        "cisco_nxos" -> "nxos"
    """
    return device_type.replace("cisco_", "")


def make_device_specific_name(api_name: str, device_type: str) -> str:
    """Insert device_type into API name before the source suffix.

    Examples:
        ("get_errors_fna", "hpe") -> "get_errors_hpe_fna"
        ("get_transceiver_fna", "cisco_ios") -> "get_transceiver_ios_fna"
    """
    short_dt = device_type_short(device_type)
    # Split at last underscore to get source suffix (e.g., "fna")
    parts = api_name.rsplit("_", 1)
    if len(parts) == 2:
        return f"{parts[0]}_{short_dt}_{parts[1]}"
    return f"{api_name}_{short_dt}"


def generate_all_parsers(report_path: Path, output_dir: Path) -> int:
    """Generate parser skeletons for all successful API results.

    Handles two cases:
    - Device-specific APIs (DNA): one parser per API name
    - Generic APIs (FNA): one parser per (API name, device_type) combination
    """
    from collections import defaultdict

    # Load report
    with open(report_path) as f:
        report = json.load(f)

    # Filter successful results
    successful_results = [r for r in report["results"] if r["success"]]

    if not successful_results:
        console.print("[yellow]⚠️  No successful API results found in report[/yellow]")
        return 0

    console.print(f"📊 Found {len(successful_results)} successful API results\n")

    # Group results by api_name to detect generic APIs (multiple device_types)
    groups: dict[str, list[dict]] = defaultdict(list)
    for result in successful_results:
        groups[result["api_name"]].append(result)

    # Generate parsers
    generated_count = 0

    for api_name, results in groups.items():
        # Check how many distinct device_types this API was tested against
        device_types = set()
        for r in results:
            dt = r["target_params"].get("device_type")
            if dt:
                device_types.add(dt)

        # Get parsed_data from the first result (same for all results of this API)
        parsed_data_type = results[0].get("parsed_data")

        if len(device_types) > 1:
            # Generic API (e.g., FNA): generate one parser per device_type
            for result in results:
                dt = result["target_params"].get("device_type")
                if not dt:
                    continue
                parser_name = make_device_specific_name(api_name, dt)
                output_path = generate_parser(
                    api_name=parser_name,
                    target_name=result["target_name"],
                    source=api_name,
                    endpoint=result.get("url", "Unknown"),
                    raw_data=result["raw_data"],
                    output_dir=output_dir,
                    device_type=dt,
                    parsed_data=parsed_data_type,
                )
                if output_path:
                    generated_count += 1
        else:
            # Device-specific API (e.g., DNA) or non-switch API (e.g., GNMSPING)
            result = results[0]
            dt = result["target_params"].get("device_type")
            output_path = generate_parser(
                api_name=api_name,
                target_name=result["target_name"],
                source=api_name,
                endpoint=result.get("url", "Unknown"),
                raw_data=result["raw_data"],
                output_dir=output_dir,
                device_type=dt,
                parsed_data=parsed_data_type,
            )
            if output_path:
                generated_count += 1

    return generated_count


# =============================================================================
# Main
# =============================================================================


def main():
    """Main entry point."""
    console.print("\n[bold cyan]📝 Parser Skeleton Generator[/bold cyan]")

    # Find latest report
    reports_dir = PROJECT_ROOT / "reports"
    report_path = find_latest_report(reports_dir)

    if not report_path:
        console.print(
            "[red]❌ No API test reports found in reports/ directory[/red]"
        )
        console.print("[yellow]💡 Run 'make test-apis' first[/yellow]\n")
        sys.exit(1)

    console.print(f"📄 Using report: {report_path.name}")

    # Prepare output directory
    output_dir = PROJECT_ROOT / "app" / "parsers" / "plugins"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate parsers
    console.print("\n[bold]Generating parser skeletons...[/bold]")
    generated_count = generate_all_parsers(report_path, output_dir)

    # Print summary
    console.print(f"\n[bold]📝 Summary:[/bold]")
    console.print(f"  ✅ Generated: {generated_count} new parser(s)")
    console.print(f"  📁 Output directory: {output_dir}\n")

    if generated_count > 0:
        console.print(
            "[bold green]🎉 Parser skeletons generated successfully![/bold green]"
        )
        console.print("\n[bold]Next steps:[/bold]")
        console.print("  1. Open a parser file (raw data + ParsedData fields included)")
        console.print("  2. Ask AI: 'fill in the parse() method'")
        console.print("  3. Run 'make test-parsers' to validate\n")


if __name__ == "__main__":
    main()
