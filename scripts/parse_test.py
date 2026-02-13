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

# ── ANSI colors ──
class C:
    """ANSI color codes for terminal output."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    RED     = "\033[31m"
    CYAN    = "\033[36m"
    MAGENTA = "\033[35m"
    WHITE   = "\033[37m"

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
    print(f"\n  {C.DIM}Loaded {count} parser modules, {len(parser_registry._parsers)} registered{C.RESET}\n")

    if not RAW_DIR.exists():
        print(f"  {C.RED}No raw data directory found: {RAW_DIR}{C.RESET}")
        print(f"  Run {C.CYAN}make fetch{C.RESET} first to fetch raw API data.")
        sys.exit(1)

    raw_files = sorted(RAW_DIR.glob("*.txt"))
    if not raw_files:
        print(f"  {C.RED}No .txt files found in {RAW_DIR}{C.RESET}")
        print(f"  Run {C.CYAN}make fetch{C.RESET} first to fetch raw API data.")
        sys.exit(1)

    # Stats
    total = 0
    parsed_ok = 0
    empty = 0
    errors = 0
    report_entries: list[dict] = []

    print(f"{C.BOLD}{C.MAGENTA}{'═' * 70}")
    print(f"  PARSE TEST RESULTS")
    print(f"{'═' * 70}{C.RESET}")

    for filepath in raw_files:
        parsed_info = parse_filename(filepath.name)
        if parsed_info is None:
            print(f"\n  {C.DIM}--- {filepath.name} ---{C.RESET}")
            print(f"  {C.DIM}Skipped: could not parse filename{C.RESET}")
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

        print(f"\n  {C.BOLD}--- {parser_command} ({device_type} / {ip}) ---{C.RESET}")

        if parser is None:
            print(f"    {C.RED}Parser not found: {parser_command}{C.RESET}")
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
        print(f"    {C.DIM}Raw: {len(raw_output)} bytes, {len(raw_output.splitlines())} lines{C.RESET}")

        # Parse
        try:
            results = parser.parse(raw_output)
        except Exception as e:
            print(f"    {C.RED}PARSE ERROR: {type(e).__name__}: {e}{C.RESET}")
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
            print(f"    {C.YELLOW}Parsed: 0 records  !! (empty — parser may need adjustment){C.RESET}")
            empty += 1
            report_entries.append({
                "file": filepath.name,
                "parser": parser_command,
                "status": "empty",
                "record_count": 0,
            })
        else:
            print(f"    {C.GREEN}Parsed: {record_count} records  OK{C.RESET}")
            parsed_ok += 1

            # Show record summaries
            display_count = min(record_count, max_records)
            for i, record in enumerate(results[:display_count]):
                print(f"    {C.DIM}{format_record_summary(record)}{C.RESET}")
            if record_count > display_count:
                print(f"    {C.DIM}... and {record_count - display_count} more{C.RESET}")

            # Verbose: full JSON
            if verbose:
                print(f"    {C.DIM}Full JSON:{C.RESET}")
                for record in results[:display_count]:
                    d = record.model_dump() if hasattr(record, "model_dump") else vars(record)
                    print(f"      {C.DIM}{json.dumps(d, ensure_ascii=False, default=str)}{C.RESET}")

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
    print(f"\n{C.BOLD}{C.MAGENTA}{'═' * 70}{C.RESET}")
    print(f"  {C.BOLD}SUMMARY{C.RESET}")
    print(f"{C.BOLD}{C.MAGENTA}{'═' * 70}{C.RESET}")
    print(f"  Total:        {C.BOLD}{total}{C.RESET}")
    print(f"  OK Parsed:    {C.GREEN}{C.BOLD}{parsed_ok}{C.RESET}")
    if empty:
        print(f"  Empty result: {C.YELLOW}{C.BOLD}{empty}{C.RESET}")
    else:
        print(f"  Empty result: {empty}")
    if errors:
        print(f"  Errors:       {C.RED}{C.BOLD}{errors}{C.RESET}")
    else:
        print(f"  Errors:       {errors}")

    if empty > 0:
        print(f"\n  {C.YELLOW}Empty results (parser may need adjustment):{C.RESET}")
        for entry in report_entries:
            if entry["status"] == "empty":
                print(f"    {C.YELLOW}-{C.RESET} {entry['file']} {C.DIM}({entry['parser']}){C.RESET}")

    if errors > 0:
        print(f"\n  {C.RED}Errors:{C.RESET}")
        for entry in report_entries:
            if entry["status"] == "error":
                print(f"    {C.RED}-{C.RESET} {entry['file']}: {entry.get('error', '?')}")

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
