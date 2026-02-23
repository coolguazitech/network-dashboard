#!/usr/bin/env python3
"""
Generate debug bundles for ALL parsers.

After running `make parse`, use this script to generate one .md file per
parser.  Each file is a self-contained prompt bundle that can be copied
to ChatGPT (or any AI) for parser evaluation and debugging.

The AI will:
  - If the parser output is correct → reply "OK"
  - If the parser output is wrong  → reply with the complete fixed parser

Generated files:  test_data/debug/{parser_command}.md

Usage:
    python scripts/generate_debug.py                    # all parsers
    python scripts/generate_debug.py --api get_fan      # only matching API
    python scripts/generate_debug.py --max-samples 5    # limit raw data files per bundle
"""
from __future__ import annotations

import argparse
import inspect
import re
import sys
import traceback
from pathlib import Path

# ── Resolve paths ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "test_data" / "raw"
DEBUG_DIR = PROJECT_ROOT / "test_data" / "debug"
CONVERGED_FILE = DEBUG_DIR / ".converged"
PLUGINS_DIR = PROJECT_ROOT / "app" / "parsers" / "plugins"

sys.path.insert(0, str(PROJECT_ROOT))

from app.core.enums import DeviceType  # noqa: E402
from app.parsers.registry import auto_discover_parsers, parser_registry  # noqa: E402
from app.parsers import protocols as proto_module  # noqa: E402

# ── ANSI colors ──
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    RED     = "\033[31m"
    CYAN    = "\033[36m"
    MAGENTA = "\033[35m"

# ── Constants ──
DEVICE_TYPE_ENUM = {
    "hpe": DeviceType.HPE,
    "ios": DeviceType.CISCO_IOS,
    "nxos": DeviceType.CISCO_NXOS,
}

FILENAME_PATTERN = re.compile(r"^(.+?)_(hpe|ios|nxos)_(.+)\.txt$")

# Map api_name prefix → model class(es) to extract source for
MODEL_MAP: dict[str, list[type]] = {
    "get_fan": [proto_module.FanStatusData],
    "get_version": [proto_module.VersionData],
    "get_power": [proto_module.PowerData],
    "get_mac_table": [proto_module.MacTableData],
    "get_uplink_lldp": [proto_module.NeighborData],
    "get_uplink_cdp": [proto_module.NeighborData],
    "get_uplink": [proto_module.NeighborData],
    "get_channel_group": [proto_module.PortChannelData],
    "get_error_count": [proto_module.InterfaceErrorData],
    "get_static_acl": [proto_module.AclData],
    "get_dynamic_acl": [proto_module.AclData],
    "get_gbic_details": [proto_module.TransceiverData, proto_module.TransceiverChannelData],
}

# ── Per-API extra notes injected into AI bundles ──
# Keyed by api_name prefix — matched via startswith()
EXTRA_NOTES: dict[str, str] = {
    "get_gbic_details": """
## ⚠️ CRITICAL: Multi-Channel Optics (QSFP/QSFP28/QSFP-DD)

Multi-channel optics (40G QSFP, 100G QSFP28) have **4 lanes**, each with
independent Tx/Rx power readings.

**You MUST parse ALL channels, not just channel 1.**

- `TransceiverData.channels` must contain ALL channels (typically 4 lanes)
- Each lane = one `TransceiverChannelData(channel=N, tx_power=..., rx_power=...)`
- If raw data shows Lane 1/2/3/4 or Channel 1/2/3/4, the channels list must have 4 entries

**Common mistake**: Only capturing channel 1 and reporting OK. This is WRONG.
Count the channels in the raw data and verify your parser returns the same count.
""",
}


def load_converged() -> set[str]:
    """Load the set of converged (confirmed OK) parser commands."""
    if not CONVERGED_FILE.exists():
        return set()
    return {
        line.strip()
        for line in CONVERGED_FILE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }


def save_converged(converged: set[str]) -> None:
    """Save the converged set to disk."""
    CONVERGED_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONVERGED_FILE.write_text(
        "# Converged parsers — AI confirmed OK, skipped by parse-debug\n"
        + "\n".join(sorted(converged))
        + "\n"
    )


def parse_filename(filename: str) -> tuple[str, str, str] | None:
    match = FILENAME_PATTERN.match(filename)
    if not match:
        return None
    return match.group(1), match.group(2), match.group(3)


def resolve_parser_command(api_name: str, device_type: str) -> str:
    for suffix in ("fna", "dna"):
        command = f"{api_name}_{device_type}_{suffix}"
        dt = DEVICE_TYPE_ENUM.get(device_type)
        parser = parser_registry.get(command, dt)
        if parser is not None:
            return command
    return f"{api_name}_{device_type}_fna"


def get_model_source(api_name: str) -> str:
    """Extract the relevant ParsedData model source code using inspect."""
    classes = None
    for prefix, cls_list in MODEL_MAP.items():
        if api_name.startswith(prefix):
            classes = cls_list
            break

    if not classes:
        return "# (Model not found for this API)"

    parts = []
    # Always include the base class definition
    parts.append("class ParsedData(BaseModel):\n    \"\"\"Base class for all parsed data.\"\"\"\n    pass")

    for cls in classes:
        try:
            source = inspect.getsource(cls)
            parts.append(source.strip())
        except (TypeError, OSError):
            parts.append(f"# Could not extract source for {cls.__name__}")

    return "\n\n".join(parts)


def get_parser_source(parser_command: str) -> tuple[str, str]:
    """Read parser source from disk. Returns (source_code, filepath)."""
    filepath = PLUGINS_DIR / f"{parser_command}_parser.py"
    if not filepath.exists():
        return f"# Parser file not found: {filepath}", str(filepath)
    return filepath.read_text(encoding="utf-8"), str(filepath.relative_to(PROJECT_ROOT))


def _get_extra_notes(api_name: str) -> str:
    """Look up per-API extra notes to inject into the bundle."""
    for prefix, note in EXTRA_NOTES.items():
        if api_name.startswith(prefix):
            return note.strip()
    return ""


def generate_bundle(
    parser_command: str,
    status: str,
    error_msg: str,
    raw_files: list[tuple[str, str]],
    model_source: str,
    parser_source: str,
    parser_filepath: str,
    record_count: int,
    sample_records: str,
    extra_notes: str = "",
) -> str:
    """Generate the markdown debug bundle content."""
    raw_sections = []
    for filename, content in raw_files:
        line_count = len(content.splitlines())
        byte_count = len(content.encode("utf-8"))
        raw_sections.append(
            f"### File: {filename}\n"
            f"({byte_count} bytes, {line_count} lines)\n\n"
            f"```\n{content}\n```"
        )
    raw_data_text = "\n\n".join(raw_sections) if raw_sections else "(No raw data files found)"

    status_description = ""
    if status == "empty":
        status_description = (
            f"- Parser returned: **0 records** (empty)\n"
            f"- This means the regex patterns did not match the raw data format."
        )
    elif status == "error":
        status_description = (
            f"- Parser returned: **ERROR** (threw an exception)\n"
            f"- Error: `{error_msg}`"
        )
    elif status == "ok":
        status_description = (
            f"- Parser returned: **{record_count} records**"
        )

    results_section = ""
    if sample_records:
        results_section = f"""
## Current Parse Results

```
{sample_records}
```
"""
    elif status == "empty":
        results_section = """
## Current Parse Results

Parser produced **no results** (empty list).
"""

    extra_notes_section = f"\n{extra_notes}\n" if extra_notes else ""

    return f"""# Parser Evaluation: {parser_command}

## Task

You are a Python parser developer. Review the parser below, its raw input
data, and its current output. Then decide:

- **If the parser output correctly matches the raw data** → reply with
  exactly one line: `OK`
- **If the parser output is wrong, missing data, or the parser crashed** →
  reply with the COMPLETE fixed parser file (full Python code, ready to
  paste into `{parser_filepath}`)

**Rules for fixing:**
1. The parser must accept raw text and return a list of Pydantic model objects
2. Handle edge cases: empty input, missing fields, varying whitespace
3. Return `[]` if no valid data — **never raise exceptions**
4. Do NOT modify: class name, `device_type`, `command`, or imports
5. Keep the `parser_registry.register(...)` call at the bottom
6. Keep the `=== ParsedData Model ===` block in the module docstring
7. Return the COMPLETE file — no `...`, no "rest unchanged"
{extra_notes_section}
## Current Status

{status_description}

## ParsedData Model Definition

These are the Pydantic model(s) this parser must produce. Do NOT modify
these — they are defined in `app/parsers/protocols.py`.

```python
{model_source}
```

## Current Parser Source Code

File: `{parser_filepath}`

```python
{parser_source}
```

## Raw Data (real switch output)

These are **real** raw outputs from production switches.

{raw_data_text}
{results_section}
## Your Response

Compare the raw data against the parse results.
- If results correctly capture all data from the raw output → reply `OK`
- If results are wrong or missing → reply with the COMPLETE fixed parser file
"""


def mark_converged(parser_commands: list[str]) -> None:
    """Mark parser(s) as converged (AI confirmed OK)."""
    converged = load_converged()
    for cmd in parser_commands:
        # Validate: check if parser file exists
        parser_file = PLUGINS_DIR / f"{cmd}_parser.py"
        if not parser_file.exists():
            print(f"  {C.RED}UNKNOWN{C.RESET} {cmd} — "
                  f"no parser file found at {parser_file.relative_to(PROJECT_ROOT)}")
            continue
        converged.add(cmd)
        print(f"  {C.GREEN}CONVERGED{C.RESET} {cmd}")
        # Remove the .md bundle since it's no longer needed
        md_path = DEBUG_DIR / f"{cmd}.md"
        if md_path.exists():
            md_path.unlink()
    save_converged(converged)


def main() -> None:
    argp = argparse.ArgumentParser(
        description="Generate debug bundles for all parsers"
    )
    argp.add_argument(
        "--api", type=str, default=None,
        help="Only generate for specific API (substring match)"
    )
    argp.add_argument(
        "--max-samples", type=int, default=0,
        help="Max raw data files per bundle (0=unlimited)"
    )
    argp.add_argument(
        "--ok", type=str, nargs="+", default=None,
        metavar="PARSER",
        help="Mark parser(s) as converged (AI confirmed OK). "
             "Example: --ok get_fan_nxos_dna get_uplink_hpe_fna"
    )
    argp.add_argument(
        "--reset", action="store_true",
        help="Reset all converged marks (re-evaluate everything)"
    )
    args = argp.parse_args()

    # Handle --reset
    if args.reset:
        if CONVERGED_FILE.exists():
            CONVERGED_FILE.unlink()
        print(f"  {C.YELLOW}Reset{C.RESET} all converged marks")
        return

    # Handle --ok: mark parsers as converged and exit
    if args.ok:
        mark_converged(args.ok)
        return

    # Discover parsers
    count = auto_discover_parsers()
    print(f"\n  {C.DIM}Loaded {count} parser modules, {len(parser_registry._parsers)} registered{C.RESET}\n")

    if not RAW_DIR.exists():
        print(f"  {C.RED}No raw data directory: {RAW_DIR}{C.RESET}")
        print(f"  Run {C.CYAN}make fetch{C.RESET} first.")
        sys.exit(1)

    raw_files = sorted(RAW_DIR.glob("*.txt"))
    if not raw_files:
        print(f"  {C.RED}No .txt files in {RAW_DIR}{C.RESET}")
        sys.exit(1)

    # Load converged set
    converged = load_converged()
    converged_mtime = CONVERGED_FILE.stat().st_mtime if CONVERGED_FILE.exists() else 0

    # Group raw files by parser_command
    files_by_parser: dict[str, list[tuple[str, str, str, str]]] = {}

    for filepath in raw_files:
        parsed = parse_filename(filepath.name)
        if parsed is None:
            continue
        api_name, device_type, ip = parsed

        if args.api and args.api not in api_name:
            continue

        parser_command = resolve_parser_command(api_name, device_type)
        files_by_parser.setdefault(parser_command, []).append(
            (filepath.name, api_name, device_type, ip)
        )

        # Auto-invalidate converged mark if raw data is newer
        if parser_command in converged and filepath.stat().st_mtime > converged_mtime:
            converged.discard(parser_command)
            save_converged(converged)
            print(f"  {C.YELLOW}STALE{C.RESET}  {parser_command} — new raw data, re-evaluating")

    if not files_by_parser:
        print(f"  {C.YELLOW}No matching raw data files found.{C.RESET}")
        return

    # Process each parser
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    generated = 0
    skipped_converged = 0

    print(f"{C.BOLD}{C.MAGENTA}{'═' * 70}")
    print(f"  GENERATING DEBUG BUNDLES")
    print(f"{'═' * 70}{C.RESET}\n")

    for parser_command, file_entries in sorted(files_by_parser.items()):
        # Skip converged parsers
        if parser_command in converged:
            skipped_converged += 1
            print(f"  {C.DIM}  DONE  {parser_command} (converged){C.RESET}")
            continue

        api_name = file_entries[0][1]
        device_type = file_entries[0][2]
        dt_enum = DEVICE_TYPE_ENUM.get(device_type)

        parser = parser_registry.get(parser_command, dt_enum)

        # Collect raw data
        raw_data: list[tuple[str, str]] = []
        for filename, _, _, _ in file_entries:
            filepath = RAW_DIR / filename
            content = filepath.read_text(encoding="utf-8")
            raw_data.append((filename, content))

        if args.max_samples > 0:
            raw_data = raw_data[:args.max_samples]

        # Run parser on all raw files to determine status
        overall_status = "ok"
        overall_error = ""
        total_records = 0
        sample_lines: list[str] = []

        if parser is None:
            overall_status = "error"
            overall_error = f"Parser not found: {parser_command}"
        else:
            all_empty = True
            for filename, content in raw_data:
                try:
                    results = parser.parse(content)
                    if results:
                        all_empty = False
                        total_records += len(results)
                        for r in results:
                            d = r.model_dump() if hasattr(r, "model_dump") else vars(r)
                            sample_lines.append(f"[{filename}] {d}")
                    else:
                        sample_lines.append(f"[{filename}] (empty)")
                except Exception as e:
                    overall_status = "error"
                    overall_error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
                    sample_lines.append(f"[{filename}] ERROR: {e}")
                    break

            if overall_status != "error" and all_empty:
                overall_status = "empty"

        # Get model source and parser source
        model_source = get_model_source(api_name)
        parser_source, parser_filepath = get_parser_source(parser_command)
        sample_records = "\n".join(sample_lines) if sample_lines else ""
        extra_notes = _get_extra_notes(api_name)

        # Generate bundle
        bundle = generate_bundle(
            parser_command=parser_command,
            status=overall_status,
            error_msg=overall_error,
            raw_files=raw_data,
            model_source=model_source,
            parser_source=parser_source,
            parser_filepath=parser_filepath,
            record_count=total_records,
            sample_records=sample_records,
            extra_notes=extra_notes,
        )

        # Write
        output_path = DEBUG_DIR / f"{parser_command}.md"
        output_path.write_text(bundle, encoding="utf-8")
        generated += 1

        status_label = {
            "empty": f"{C.YELLOW}EMPTY{C.RESET}",
            "error": f"{C.RED}ERROR{C.RESET}",
            "ok": f"{C.GREEN}   OK{C.RESET}",
        }[overall_status]

        print(f"  {status_label} {parser_command} → {C.CYAN}{output_path.relative_to(PROJECT_ROOT)}{C.RESET}")

    # Summary
    print(f"\n{C.BOLD}{C.MAGENTA}{'═' * 70}{C.RESET}")
    print(f"  {C.BOLD}SUMMARY{C.RESET}")
    print(f"{C.BOLD}{C.MAGENTA}{'═' * 70}{C.RESET}")
    print(f"  Generated:  {C.BOLD}{generated}{C.RESET} bundles")
    if skipped_converged:
        print(f"  Converged:  {C.GREEN}{skipped_converged}{C.RESET} (AI confirmed OK)")
    remaining = generated
    print(f"  Remaining:  {C.BOLD}{remaining}{C.RESET} need AI review")
    if remaining == 0 and skipped_converged > 0:
        print(f"\n  {C.GREEN}{C.BOLD}All parsers converged!{C.RESET} "
              f"Ready for next round: {C.CYAN}make clean-raw && make fetch-sample{C.RESET}")
    elif generated > 0:
        print(f"\n  {C.BOLD}Workflow:{C.RESET}")
        print(f"  1. Open a .md file from {C.CYAN}test_data/debug/{C.RESET}")
        print(f"  2. Copy entire content → paste to ChatGPT")
        print(f"  3. AI replies {C.GREEN}OK{C.RESET} → mark as converged:")
        print(f"     {C.CYAN}make parse-ok P=get_fan_nxos_dna{C.RESET}")
        print(f"     AI replies with code → paste into {C.CYAN}app/parsers/plugins/{C.RESET}")
        print(f"  4. Run {C.CYAN}make parse-debug{C.RESET} again → repeat until all converged")


if __name__ == "__main__":
    main()
