#!/usr/bin/env python3
"""
Parser Validator

Test all parsers against real raw data from API test reports.

Usage:
    python scripts/test_parsers.py
    # or
    make test-parsers
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import parser registry and auto-discover ALL parsers (including new skeletons)
from app.parsers.registry import auto_discover_parsers, parser_registry

# Discover all parser plugins (including generated skeletons not in __init__.py)
auto_discover_parsers()

console = Console()


# =============================================================================
# Validation Result
# =============================================================================


class ValidationResult:
    """Single parser validation result."""

    def __init__(
        self,
        parser_name: str,
        api_name: str,
        target_name: str,
        status: str,  # "passed", "failed", "skipped"
        parsed_count: int = 0,
        sample_output: dict[str, Any] | None = None,
        error: str | None = None,
    ):
        self.parser_name = parser_name
        self.api_name = api_name
        self.target_name = target_name
        self.status = status
        self.parsed_count = parsed_count
        self.sample_output = sample_output
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "parser": self.parser_name,
            "test_data_source": f"api_name={self.api_name}, target={self.target_name}",
            "status": self.status,
            "parsed_count": self.parsed_count,
            "sample_output": self.sample_output,
            "error": self.error,
        }


# =============================================================================
# Utilities
# =============================================================================


def find_latest_report(reports_dir: Path) -> Path | None:
    """Find the latest API test report."""
    reports = list(reports_dir.glob("api_test_*.json"))
    if not reports:
        return None
    return max(reports, key=lambda p: p.stat().st_mtime)


def device_type_short(device_type: str) -> str:
    """Convert device_type to short form for parser naming."""
    return device_type.replace("cisco_", "")


def make_device_specific_name(api_name: str, device_type: str) -> str:
    """Insert device_type into API name before the source suffix.

    Examples:
        ("get_errors_fna", "hpe") -> "get_errors_hpe_fna"
        ("get_transceiver_fna", "cisco_ios") -> "get_transceiver_ios_fna"
    """
    short_dt = device_type_short(device_type)
    parts = api_name.rsplit("_", 1)
    if len(parts) == 2:
        return f"{parts[0]}_{short_dt}_{parts[1]}"
    return f"{api_name}_{short_dt}"


def find_parser_for_api(api_name: str, device_type: str | None = None) -> Any | None:
    """
    Find parser for given API name by matching parser.command.

    Strategy:
    1. Try exact api_name match against parser.command
    2. If device_type is provided, also try device-specific name
       (for FNA APIs: get_errors_fna + hpe -> get_errors_hpe_fna)

    Returns None if not found.
    """
    # Build list of candidate names to try
    candidates = [api_name]
    if device_type:
        candidates.append(make_device_specific_name(api_name, device_type))

    # Search by command field
    all_keys = parser_registry.list_parsers()
    all_parsers = [parser_registry.get(k.command, k.device_type) for k in all_keys]

    for candidate in candidates:
        for parser in all_parsers:
            if hasattr(parser, "command") and parser.command == candidate:
                return parser

    return None


# =============================================================================
# Parser Testing
# =============================================================================


def test_parser(
    api_name: str, target_name: str, raw_data: str, device_type: str | None = None
) -> ValidationResult:
    """Test a single parser with raw data."""
    # Find parser (try device-specific name for FNA APIs)
    parser = find_parser_for_api(api_name, device_type=device_type)

    if parser is None:
        return ValidationResult(
            parser_name="N/A",
            api_name=api_name,
            target_name=target_name,
            status="skipped",
            error=f"No parser found for API '{api_name}'",
        )

    parser_name = f"{parser.__class__.__name__} (command={parser.command})"

    # Test parser
    try:
        parsed_items = parser.parse(raw_data)

        # Validate results
        if not isinstance(parsed_items, list):
            return ValidationResult(
                parser_name=parser_name,
                api_name=api_name,
                target_name=target_name,
                status="failed",
                error="parse() must return a list",
            )

        # Get sample output (first item)
        sample_output = None
        if parsed_items:
            first_item = parsed_items[0]
            if hasattr(first_item, "model_dump"):
                sample_output = first_item.model_dump()
            elif hasattr(first_item, "dict"):
                sample_output = first_item.dict()
            else:
                sample_output = str(first_item)

        # count > 0 = passed, count = 0 = empty (skeleton not filled)
        status = "passed" if parsed_items else "empty"

        return ValidationResult(
            parser_name=parser_name,
            api_name=api_name,
            target_name=target_name,
            status=status,
            parsed_count=len(parsed_items),
            sample_output=sample_output,
        )

    except Exception as e:
        return ValidationResult(
            parser_name=parser_name,
            api_name=api_name,
            target_name=target_name,
            status="failed",
            error=f"{type(e).__name__}: {str(e)}",
        )


def test_all_parsers(report_path: Path) -> list[ValidationResult]:
    """Test all parsers against API test results."""
    # Load report
    with open(report_path) as f:
        report = json.load(f)

    # Filter successful results with raw_data
    successful_results = [
        r for r in report["results"] if r["success"] and r.get("raw_data")
    ]

    if not successful_results:
        console.print(
            "[yellow]⚠️  No successful API results with raw_data found[/yellow]"
        )
        return []

    console.print(f"📊 Found {len(successful_results)} API results to test\n")

    # Test each parser
    results: list[ValidationResult] = []
    for api_result in successful_results:
        api_name = api_result["api_name"]
        target_name = api_result["target_name"]
        raw_data = api_result["raw_data"]
        device_type = api_result.get("target_params", {}).get("device_type")

        validation_result = test_parser(api_name, target_name, raw_data, device_type)
        results.append(validation_result)

        # Log result
        if validation_result.status == "passed":
            console.print(
                f"  ✅ {validation_result.parser_name}: "
                f"parsed {validation_result.parsed_count} object(s)"
            )
        elif validation_result.status == "empty":
            console.print(
                f"  ⚠️  {validation_result.parser_name}: "
                f"returned 0 objects (parse() not implemented?)"
            )
        elif validation_result.status == "failed":
            console.print(
                f"  ❌ {validation_result.parser_name}: "
                f"{validation_result.error}"
            )
        else:  # skipped
            console.print(f"  ⏭️  {api_name}: {validation_result.error}")

    return results


# =============================================================================
# Report Generation
# =============================================================================


def save_validation_report(
    results: list[ValidationResult],
    source_report_path: Path,
    output_dir: Path,
) -> Path:
    """Save validation results to JSON report."""
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    report_path = output_dir / f"parser_test_{timestamp}.json"

    # Calculate summary
    passed_count = sum(1 for r in results if r.status == "passed")
    empty_count = sum(1 for r in results if r.status == "empty")
    failed_count = sum(1 for r in results if r.status == "failed")
    skipped_count = sum(1 for r in results if r.status == "skipped")

    report = {
        "timestamp": timestamp,
        "source_report": source_report_path.name,
        "summary": {
            "total_parsers_tested": len(results),
            "passed": passed_count,
            "empty": empty_count,
            "failed": failed_count,
            "skipped": skipped_count,
        },
        "results": [r.to_dict() for r in results],
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    return report_path


def print_summary_table(results: list[ValidationResult]):
    """Print a summary table of validation results."""
    table = Table(title="Parser Validation Summary")

    table.add_column("API Name", style="cyan")
    table.add_column("Parser", style="magenta")
    table.add_column("Status", style="bold")
    table.add_column("Parsed Count", justify="right")

    for result in results:
        status_emoji = {
            "passed": "✅",
            "empty": "⚠️",
            "failed": "❌",
            "skipped": "⏭️",
        }[result.status]

        status_color = {
            "passed": "green",
            "empty": "yellow",
            "failed": "red",
            "skipped": "dim",
        }[result.status]

        table.add_row(
            result.api_name,
            result.parser_name,
            f"[{status_color}]{status_emoji} {result.status}[/{status_color}]",
            str(result.parsed_count) if result.status in ("passed", "empty") else "-",
        )

    console.print("\n")
    console.print(table)


# =============================================================================
# Main
# =============================================================================


def main():
    """Main entry point."""
    console.print("\n[bold cyan]🧪 Parser Validator[/bold cyan]")

    # Find latest API test report
    reports_dir = PROJECT_ROOT / "reports"
    report_path = find_latest_report(reports_dir)

    if not report_path:
        console.print(
            "[red]❌ No API test reports found in reports/ directory[/red]"
        )
        console.print("[yellow]💡 Run 'make test-apis' first[/yellow]\n")
        sys.exit(1)

    console.print(f"📄 Using report: {report_path.name}")

    # Load parsers
    console.print(f"📦 Loaded {len(parser_registry.list_parsers())} parser(s) from registry")

    # Test all parsers
    console.print("\n[bold]Testing parsers...[/bold]")
    results = test_all_parsers(report_path)

    if not results:
        console.print("[yellow]⚠️  No parsers to test[/yellow]\n")
        sys.exit(0)

    # Print summary table
    print_summary_table(results)

    # Calculate summary
    passed_count = sum(1 for r in results if r.status == "passed")
    empty_count = sum(1 for r in results if r.status == "empty")
    failed_count = sum(1 for r in results if r.status == "failed")
    skipped_count = sum(1 for r in results if r.status == "skipped")

    console.print("\n[bold]📝 Summary:[/bold]")
    console.print(f"  ✅ Passed: {passed_count}/{len(results)}")
    console.print(f"  ⚠️  Empty: {empty_count}/{len(results)} (skeleton not filled)")
    console.print(f"  ❌ Failed: {failed_count}/{len(results)}")
    console.print(f"  ⏭️  Skipped: {skipped_count}/{len(results)}\n")

    # Save report
    output_dir = PROJECT_ROOT / "reports"
    validation_report_path = save_validation_report(results, report_path, output_dir)
    console.print(f"💾 Report saved to: [cyan]{validation_report_path}[/cyan]\n")

    # Exit with error if any tests failed
    if failed_count > 0:
        console.print("[red]❌ Some parsers failed validation[/red]\n")
        sys.exit(1)
    elif empty_count > 0 and passed_count == 0:
        console.print("[yellow]⚠️  All parsers are empty skeletons — fill in parse() logic[/yellow]\n")
    elif empty_count > 0:
        console.print(
            f"[bold green]🎉 {passed_count} parser(s) passed[/bold green], "
            f"[yellow]{empty_count} still empty[/yellow]\n"
        )
    else:
        console.print("[bold green]🎉 All parsers passed validation![/bold green]\n")


if __name__ == "__main__":
    main()
