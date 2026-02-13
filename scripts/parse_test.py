#!/usr/bin/env python3
"""
Parse test — feed saved raw data into parsers and report results.

Scans test_data/raw/*.txt, determines the parser from the filename,
runs parser.parse(raw_output), and reports results.

Usage:
    python scripts/parse_test.py                     # parse all
    python scripts/parse_test.py --api get_fan       # only specific API
    python scripts/parse_test.py --verbose           # print full ParsedData
    python scripts/parse_test.py --save-report       # save report to test_data/reports/
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

# ── Resolve paths ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "test_data" / "raw"
REPORT_DIR = PROJECT_ROOT / "test_data" / "reports"

# Add project root to sys.path so we can import app modules
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.enums import DeviceType  # noqa: E402
from app.parsers.registry import auto_discover_parsers, parser_registry  # noqa: E402

# device_type string → DeviceType enum
DEVICE_TYPE_ENUM = {
    "hpe": DeviceType.HPE,
    "ios": DeviceType.CISCO_IOS,
    "nxos": DeviceType.CISCO_NXOS,
}

# Filename pattern: {api_name}_{device_type}_{ip}.txt
# api_name can contain underscores, so we match greedily up to the device_type
# Known device types: hpe, ios, nxos
FILENAME_PATTERN = re.compile(
    r"^(.+?)_(hpe|ios|nxos)_(.+)\.txt$"
)


def parse_filename(filename: str) -> tuple[str, str, str] | None:
    """
    Parse filename into (api_name, device_type, ip).

    Special case: ping_batch_all_batch.txt → (ping_batch, all, batch)
    """
    # Special handling for ping_batch
    if filename.startswith("ping_batch_"):
        return ("ping_batch", "all", "batch")

    match = FILENAME_PATTERN.match(filename)
    if not match:
        return None
    return match.group(1), match.group(2), match.group(3)


def resolve_parser_command(api_name: str, device_type: str) -> str:
    """
    Map api_name + device_type to parser command.

    FNA APIs: get_fan → get_fan_{device_type}_fna
    DNA APIs: get_fan → get_fan_{device_type}_dna
    Ping: ping_batch → ping_batch
    """
    if api_name == "ping_batch":
        return "ping_batch"

    # Try to find the parser by checking both FNA and DNA suffixes
    for suffix in ("fna", "dna"):
        command = f"{api_name}_{device_type}_{suffix}"
        dt = DEVICE_TYPE_ENUM.get(device_type)
        parser = parser_registry.get(command, dt)
        if parser is not None:
            return command

    # Fallback: return FNA pattern
    return f"{api_name}_{device_type}_fna"


def format_record_summary(record: object) -> str:
    """Format a single ParsedData record as a one-line summary."""
    d = record.model_dump() if hasattr(record, "model_dump") else vars(record)

    # Pick key fields based on data type
    class_name = type(record).__name__

    if class_name == "FanStatusData":
        return f"  {d.get('fan_id', '?')}: status={d.get('status', '?')}"
    elif class_name == "PowerData":
        return f"  {d.get('ps_id', '?')}: status={d.get('status', '?')}, watts={d.get('actual_output_watts', '?')}"
    elif class_name == "VersionData":
        return f"  version={d.get('version', '?')}, model={d.get('model', '?')}"
    elif class_name == "NeighborData":
        return f"  {d.get('local_interface', '?')} -> {d.get('remote_hostname', '?')} ({d.get('remote_interface', '?')})"
    elif class_name == "PortChannelData":
        return f"  {d.get('interface_name', '?')}: status={d.get('status', '?')}, members={d.get('members', [])}"
    elif class_name == "InterfaceErrorData":
        return f"  {d.get('interface_name', '?')}: crc_errors={d.get('crc_errors', 0)}"
    elif class_name == "MacTableData":
        return f"  {d.get('mac_address', '?')} vlan={d.get('vlan_id', '?')} port={d.get('interface_name', '?')}"
    elif class_name == "ArpData":
        return f"  {d.get('ip_address', '?')} -> {d.get('mac_address', '?')}"
    elif class_name == "AclData":
        return f"  {d.get('interface_name', '?')}: acl={d.get('acl_number', 'none')}"
    elif class_name == "PingResultData":
        status = "reachable" if d.get("is_reachable") else "unreachable"
        return f"  {d.get('ip_address', '?')}: {status}"
    elif class_name == "TransceiverData":
        channels = d.get("channels", [])
        return f"  {d.get('interface_name', '?')}: {len(channels)} ch, temp={d.get('temperature', '?')}"
    else:
        # Generic: show first 3 key-value pairs
        items = list(d.items())[:3]
        return "  " + ", ".join(f"{k}={v}" for k, v in items)


def run_parse_tests(
    api_filter: str | None,
    verbose: bool,
    save_report: bool,
    max_records: int,
) -> None:
    """Main parse test loop."""
    # Discover all parsers
    count = auto_discover_parsers()
    print(f"Loaded {count} parser modules, {len(parser_registry._parsers)} registered\n")

    if not RAW_DIR.exists():
        print(f"No raw data directory found: {RAW_DIR}")
        print("Run 'make fetch' first to fetch raw API data.")
        sys.exit(1)

    raw_files = sorted(RAW_DIR.glob("*.txt"))
    if not raw_files:
        print(f"No .txt files found in {RAW_DIR}")
        print("Run 'make fetch' first to fetch raw API data.")
        sys.exit(1)

    # Stats
    total = 0
    parsed_ok = 0
    empty = 0
    errors = 0
    report_entries: list[dict] = []

    print("=" * 70)
    print("PARSE TEST RESULTS")
    print("=" * 70)

    for filepath in raw_files:
        parsed_info = parse_filename(filepath.name)
        if parsed_info is None:
            print(f"\n--- {filepath.name} ---")
            print("  Skipped: could not parse filename")
            continue

        api_name, device_type, ip = parsed_info

        # Filter
        if api_filter and api_filter not in api_name:
            continue

        total += 1

        # Resolve parser command
        parser_command = resolve_parser_command(api_name, device_type)
        dt_enum = DEVICE_TYPE_ENUM.get(device_type)

        # Get parser
        parser = parser_registry.get(parser_command, dt_enum)

        print(f"\n--- {parser_command} ({device_type} / {ip}) ---")

        if parser is None:
            print(f"  Parser not found: {parser_command}")
            errors += 1
            report_entries.append({
                "file": filepath.name,
                "parser": parser_command,
                "status": "error",
                "error": "parser not found",
            })
            continue

        # Read raw data
        raw_output = filepath.read_text(encoding="utf-8")
        print(f"  Raw: {len(raw_output)} bytes, {len(raw_output.splitlines())} lines")

        # Parse
        try:
            results = parser.parse(raw_output)
        except Exception as e:
            print(f"  PARSE ERROR: {type(e).__name__}: {e}")
            if verbose:
                traceback.print_exc()
            errors += 1
            report_entries.append({
                "file": filepath.name,
                "parser": parser_command,
                "status": "error",
                "error": f"{type(e).__name__}: {e}",
            })
            continue

        record_count = len(results)

        if record_count == 0:
            print(f"  Parsed: 0 records  !! (empty -- parser may need adjustment)")
            empty += 1
            report_entries.append({
                "file": filepath.name,
                "parser": parser_command,
                "status": "empty",
                "record_count": 0,
            })
        else:
            print(f"  Parsed: {record_count} records  OK")
            parsed_ok += 1

            # Show record summaries
            display_count = min(record_count, max_records)
            for i, record in enumerate(results[:display_count]):
                print(format_record_summary(record))
            if record_count > display_count:
                print(f"  ... and {record_count - display_count} more")

            # Verbose: full JSON
            if verbose:
                print("  Full JSON:")
                for record in results[:display_count]:
                    d = record.model_dump() if hasattr(record, "model_dump") else vars(record)
                    print(f"    {json.dumps(d, ensure_ascii=False, default=str)}")

            report_entries.append({
                "file": filepath.name,
                "parser": parser_command,
                "status": "ok",
                "record_count": record_count,
                "sample": [
                    (r.model_dump() if hasattr(r, "model_dump") else vars(r))
                    for r in results[:3]
                ],
            })

    # ── Summary ──
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total:        {total}")
    print(f"  OK Parsed:    {parsed_ok}")
    print(f"  Empty result: {empty}")
    print(f"  Errors:       {errors}")

    if empty > 0:
        print(f"\n  Empty results (parser may need adjustment):")
        for entry in report_entries:
            if entry["status"] == "empty":
                print(f"    - {entry['file']} ({entry['parser']})")

    if errors > 0:
        print(f"\n  Errors:")
        for entry in report_entries:
            if entry["status"] == "error":
                print(f"    - {entry['file']}: {entry.get('error', '?')}")

    # Save report
    if save_report:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = REPORT_DIR / f"parse_report_{timestamp}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "timestamp": timestamp,
                    "total": total,
                    "ok": parsed_ok,
                    "empty": empty,
                    "errors": errors,
                    "results": report_entries,
                },
                f,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        print(f"\n  Report saved to: {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse raw API data with registered parsers and report results"
    )
    parser.add_argument(
        "--api", type=str, default=None,
        help="Only test specific API (substring match, e.g. 'fan', 'version')"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print full ParsedData JSON for each record"
    )
    parser.add_argument(
        "--save-report", action="store_true",
        help="Save report to test_data/reports/"
    )
    parser.add_argument(
        "--max-records", type=int, default=10,
        help="Max records to display per API (default: 10)"
    )
    args = parser.parse_args()

    run_parse_tests(args.api, args.verbose, args.save_report, args.max_records)


if __name__ == "__main__":
    main()
