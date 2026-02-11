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

from app.parsers.protocols import BaseParser
from app.parsers.registry import parser_registry


class {{class_name}}(BaseParser):
    """
    Parser for {{api_name}} API response.

    Example raw output from {{target_name}}:
    ```
{{example_raw_data}}
    ```

    TODO: Determine the appropriate ParsedData type for this API.
    Common types:
    - FanData (for fan status)
    - InterfaceErrorData (for error counts)
    - TransceiverData (for transceiver Tx/Rx power)
    - PowerData (for power supply status)
    - PortChannelData (for port-channel status)
    - PingData (for ping results)
    - ... (see app/parsers/protocols.py for full list)

    Once you determine the type, update this class:
    1. Import the ParsedData type and DeviceType enum if needed
    2. Add Generic[YourType] to BaseParser
    3. Set device_type (e.g., DeviceType.HPE) or None for generic
    4. Implement parse() method

    Example after filling in:
        from app.core.enums import DeviceType
        from app.parsers.protocols import BaseParser, FanStatusData

        class {{class_name}}(BaseParser[FanStatusData]):
            device_type = DeviceType.HPE
            command = "{{api_name}}"

            def parse(self, raw_output: str) -> list[FanStatusData]:
                # Your parsing logic here
                ...
    """

    # TODO: Set device_type based on target device
    device_type = None  # e.g., DeviceType.HPE (or None for generic)
    command = "{{api_name}}"

    def parse(self, raw_output: str) -> list:
        """
        Parse raw API output into structured data.

        Args:
            raw_output: Raw text response from API

        Returns:
            List of parsed data objects (type depends on your ParsedData choice)

        TODO: Implement parsing logic here.
        Steps:
        1. Choose appropriate ParsedData type (e.g., FanData, TransceiverData)
        2. Split raw_output into lines or use regex patterns
        3. Extract fields and create ParsedData instances
        4. Return list of parsed objects

        Example:
            import re

            results = []
            for line in raw_output.strip().splitlines():
                match = re.match(r"some_pattern", line)
                if match:
                    results.append(YourParsedDataType(...))
            return results
        """
        results = []

        # TODO: Add your parsing logic here

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


def truncate_raw_data(raw_data: str, max_lines: int = 20) -> str:
    """Truncate raw data for example in docstring."""
    lines = raw_data.splitlines()
    if len(lines) <= max_lines:
        return raw_data

    truncated = "\n".join(lines[:max_lines])
    return f"{truncated}\n... (truncated, {len(lines) - max_lines} more lines)"


# =============================================================================
# Parser Generation
# =============================================================================


def generate_parser(
    api_name: str,
    target_name: str,
    source: str,
    endpoint: str,
    raw_data: str,
    output_dir: Path,
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

    # Truncate raw data for example
    example_raw_data = truncate_raw_data(raw_data)
    # Indent for docstring
    example_raw_data = "\n".join(f"    {line}" for line in example_raw_data.splitlines())

    # Render template
    template = Template(PARSER_TEMPLATE)
    content = template.render(
        api_name=api_name,
        class_name=class_name,
        source=source,
        endpoint=endpoint,
        target_name=target_name,
        example_raw_data=example_raw_data,
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
                )
                if output_path:
                    generated_count += 1
        else:
            # Device-specific API (e.g., DNA) or non-switch API (e.g., GNMSPING)
            result = results[0]
            output_path = generate_parser(
                api_name=api_name,
                target_name=result["target_name"],
                source=api_name,
                endpoint=result.get("url", "Unknown"),
                raw_data=result["raw_data"],
                output_dir=output_dir,
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
        console.print("  1. Open generated parser files")
        console.print("  2. Copy raw_data from report")
        console.print("  3. Ask AI to write parse() method")
        console.print("  4. Fill AI-generated code into skeleton")
        console.print("  5. Run 'make test-parsers' to validate\n")


if __name__ == "__main__":
    main()
