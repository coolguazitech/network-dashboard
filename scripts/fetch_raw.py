#!/usr/bin/env python3
"""
Fetch raw API data from real FNA/DNA/GNMSPING servers.

Reads config/api_test.yaml, calls each API for each target switch,
and saves raw responses to test_data/raw/{api}_{device_type}_{ip}.txt

Uses async httpx with concurrency control to handle many targets efficiently.

Usage:
    python scripts/fetch_raw.py                    # fetch all
    python scripts/fetch_raw.py --api get_fan      # only specific API
    python scripts/fetch_raw.py --target 10.1.1.1  # only specific target
    python scripts/fetch_raw.py --dry-run          # print URLs only
    python scripts/fetch_raw.py --concurrency 20   # max parallel requests
    python scripts/fetch_raw.py --timeout 60       # override read timeout (seconds)
    python scripts/fetch_raw.py --connect-timeout 5 # set connect timeout (seconds)
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import random
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import yaml

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
    BG_GREEN  = "\033[42m"
    BG_RED    = "\033[41m"
    BG_YELLOW = "\033[43m"

# ── Resolve paths ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "api_test.yaml"
RAW_DIR = PROJECT_ROOT / "test_data" / "raw"
ENV_PATH = PROJECT_ROOT / ".env"

DEFAULT_CONCURRENCY = 10

# device_type mapping: config value → DeviceType.api_value
DEVICE_TYPE_MAP = {
    "hpe": "hpe",
    "ios": "ios",
    "nxos": "nxos",
}


def load_env(env_path: Path) -> None:
    """Load .env file into os.environ (simple key=value parser)."""
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Don't override existing env vars
        if key not in os.environ:
            os.environ[key] = value


def load_config() -> dict:
    """Load and return api_test.yaml config."""
    if not CONFIG_PATH.exists():
        print(f"Error: Config file not found: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def resolve_endpoint(endpoint: str, ip: str, device_type: str) -> str:
    """Substitute {ip} and {device_type} placeholders in endpoint."""
    return endpoint.replace("{ip}", ip).replace("{device_type}", device_type)


def resolve_query_params(
    params: dict[str, str] | None, ip: str, device_type: str
) -> dict[str, str] | None:
    """Substitute placeholders in query params."""
    if not params:
        return None
    resolved = {}
    for k, v in params.items():
        resolved[k] = str(v).replace("{ip}", ip).replace("{device_type}", device_type)
    return resolved


def get_auth_headers(source_config: dict) -> dict[str, str]:
    """Build auth headers from source config."""
    auth = source_config.get("auth")
    if not auth:
        return {}

    auth_type = auth.get("type", "")
    token_env = auth.get("token_env", "")

    if auth_type == "header" and token_env:
        token = os.environ.get(token_env, "")
        if not token or token.startswith("<"):
            return {}
        return {"Authorization": f"Bearer {token}"}

    return {}


def build_url(base_url: str, endpoint: str) -> str:
    """Build full URL from base_url + endpoint."""
    return base_url.rstrip("/") + endpoint


def save_raw(api_name: str, device_type: str, ip: str, content: str) -> Path:
    """Save raw response to file and return the path."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{api_name}_{device_type}_{ip}.txt"
    filepath = RAW_DIR / filename
    filepath.write_text(content, encoding="utf-8")
    return filepath


def _format_params(params: dict[str, str] | None) -> str:
    """Format query params for display."""
    if not params:
        return ""
    return "&".join(f"{k}={v}" for k, v in params.items())


# ── Async fetch task ──


@dataclass
class FetchTask:
    """A single fetch task to execute."""
    api_name: str
    description: str
    url: str
    query_params: dict[str, str] | None
    headers: dict[str, str]
    timeout: float
    connect_timeout: float
    save_api_name: str
    save_device_type: str
    save_ip: str
    save_hostname: str
    display_label: str
    parser_command: str


@dataclass
class FetchStats:
    """Mutable stats counter."""
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[str] = field(default_factory=list)
    unreachable: list[dict[str, str]] = field(default_factory=list)


def _print_progress(progress: dict) -> None:
    """Overwrite current line with a progress bar."""
    done = progress["done"]
    total = progress["total"]
    elapsed = time.monotonic() - progress["start_time"]
    pct = done / total if total else 0

    bar_width = 30
    filled = int(bar_width * pct)
    bar = "█" * filled + "░" * (bar_width - filled)

    line = (
        f"\r  {C.CYAN}[{bar}]{C.RESET}"
        f"  {C.BOLD}{done}{C.RESET}/{total}"
        f"  ({pct:.0%})"
        f"  {C.DIM}elapsed {elapsed:.1f}s{C.RESET}"
    )
    sys.stdout.write(line)
    sys.stdout.flush()


async def execute_task(
    client: httpx.AsyncClient,
    task: FetchTask,
    sem: asyncio.Semaphore,
    stats: FetchStats,
    progress: dict,
) -> None:
    """Execute a single fetch task with semaphore-based concurrency control."""
    async with sem:
        try:
            task_timeout = httpx.Timeout(
                task.timeout, connect=task.connect_timeout,
            )
            resp = await client.get(
                task.url,
                params=task.query_params,
                headers=task.headers,
                timeout=task_timeout,
            )

            status = resp.status_code
            content = resp.text
            filepath = save_raw(
                task.save_api_name, task.save_device_type, task.save_ip, content
            )

            if 200 <= status < 300:
                stats.success += 1
                stats.results.append(
                    f"  {C.GREEN} OK {C.RESET} {task.display_label} "
                    f"{C.DIM}HTTP {status}, {len(content)} bytes{C.RESET} "
                    f"-> {C.CYAN}{filepath.name}{C.RESET}"
                )
            else:
                stats.failed += 1
                stats.results.append(
                    f"  {C.RED}FAIL{C.RESET} {task.display_label} "
                    f"{C.RED}HTTP {status}{C.RESET}: {content[:80]}"
                )

        except httpx.ConnectError:
            stats.failed += 1
            stats.unreachable.append({
                "ip": task.save_ip, "hostname": task.save_hostname,
                "device_type": task.save_device_type, "error": "Connection refused",
            })
            stats.results.append(
                f"  {C.RED}FAIL{C.RESET} {task.display_label} "
                f"{C.RED}Connection refused{C.RESET}"
            )
        except httpx.TimeoutException:
            stats.failed += 1
            stats.unreachable.append({
                "ip": task.save_ip, "hostname": task.save_hostname,
                "device_type": task.save_device_type,
                "error": f"Timeout after {task.timeout}s",
            })
            stats.results.append(
                f"  {C.RED}FAIL{C.RESET} {task.display_label} "
                f"{C.RED}Timeout after {task.timeout}s{C.RESET}"
            )
        except Exception as e:
            stats.failed += 1
            stats.results.append(
                f"  {C.RED}FAIL{C.RESET} {task.display_label} "
                f"{C.RED}{type(e).__name__}: {e}{C.RESET}"
            )
        finally:
            progress["done"] += 1
            _print_progress(progress)


async def fetch_all(
    config: dict,
    api_filter: str | None,
    target_filter: str | None,
    dry_run: bool,
    concurrency: int,
    timeout_override: float | None = None,
    connect_timeout: float = 10.0,
    clean_raw: bool = True,
) -> None:
    """Main fetch loop — builds task list then executes concurrently."""
    sources = config.get("sources", {})
    endpoints = config.get("endpoints", {})
    targets = config.get("targets", [])
    apis = config.get("apis", [])

    # Auto-clean raw data directory (skip for dry-run or filtered fetches)
    if clean_raw and not dry_run and not api_filter and not target_filter:
        if RAW_DIR.exists():
            shutil.rmtree(RAW_DIR)
            print(f"  {C.DIM}Cleaned {RAW_DIR}/{C.RESET}")
    stats = FetchStats()
    tasks: list[FetchTask] = []
    token_warned: set[str] = set()

    print(f"\n{C.BOLD}{C.CYAN}{'═' * 70}")
    print(f"  FETCH RAW DATA")
    print(f"{'═' * 70}{C.RESET}\n")

    for api_def in apis:
        api_name = api_def["name"]
        source_name = api_def["source"]
        endpoint_raw = endpoints.get(api_name, "") or api_def.get("endpoint", "")
        query_params_template = api_def.get("query_params")
        parser_cmd = api_def.get("parser_command", "")
        description = api_def.get("description", "")

        # endpoint_raw can be:
        #   str  — shared endpoint for all device_types (FNA style)
        #   dict — per-device_type endpoints (DNA style: {hpe: "...", ios: "...", nxos: "..."})
        is_per_device = isinstance(endpoint_raw, dict)

        # Filter by API name
        if api_filter and api_filter not in api_name:
            continue

        # Skip if endpoint not configured (string case)
        if not is_per_device and not endpoint_raw:
            print(f"  {C.DIM}SKIP{C.RESET} {api_name}: {C.DIM}endpoint not configured{C.RESET}")
            stats.skipped += 1
            continue
        # Skip if all per-device endpoints are empty
        if is_per_device and not any(endpoint_raw.values()):
            print(f"  {C.DIM}SKIP{C.RESET} {api_name}: {C.DIM}endpoint not configured{C.RESET}")
            stats.skipped += 1
            continue

        source_config = sources.get(source_name, {})
        base_url = source_config.get("base_url", "")
        timeout = timeout_override if timeout_override is not None else source_config.get("timeout", 30)
        headers = get_auth_headers(source_config)

        # Warn about missing token once per source
        auth = source_config.get("auth")
        if auth and auth.get("token_env"):
            token_env = auth["token_env"]
            token_val = os.environ.get(token_env, "")
            if (not token_val or token_val.startswith("<")) and token_env not in token_warned:
                print(f"  {C.YELLOW}WARN{C.RESET} {token_env} not set or is placeholder")
                token_warned.add(token_env)

        if not base_url:
            print(f"  {C.DIM}SKIP{C.RESET} {api_name}: {C.DIM}sources.{source_name}.base_url not configured{C.RESET}")
            stats.skipped += 1
            continue

        # ── FNA / DNA APIs (per target) ──
        for target in targets:
            ip = target.get("ip", "")
            hostname = target.get("hostname", "") or ip
            raw_device_type = target.get("device_type", "")
            device_type = DEVICE_TYPE_MAP.get(raw_device_type, raw_device_type)

            if not ip:
                continue
            if target_filter and target_filter != ip:
                continue

            # Resolve endpoint: dict → per-device_type, str → shared
            if is_per_device:
                endpoint_template = endpoint_raw.get(device_type, "")
                if not endpoint_template:
                    print(f"  {C.DIM}SKIP{C.RESET} {api_name}/{device_type}: "
                          f"{C.DIM}endpoint not configured for {device_type}{C.RESET}")
                    stats.skipped += 1
                    continue
            else:
                endpoint_template = endpoint_raw

            endpoint = resolve_endpoint(endpoint_template, ip, device_type)
            query_params = resolve_query_params(
                query_params_template, ip, device_type
            )
            url = build_url(base_url, endpoint)
            resolved_parser = parser_cmd.replace("{device_type}", device_type)
            label = f"{api_name}/{device_type}/{ip} ({hostname})"

            stats.total += 1
            tasks.append(FetchTask(
                api_name=api_name,
                description=description,
                url=url,
                query_params=query_params,
                headers=headers,
                timeout=timeout,
                connect_timeout=connect_timeout,
                save_api_name=api_name,
                save_device_type=device_type,
                save_ip=ip,
                save_hostname=hostname,
                display_label=label,
                parser_command=resolved_parser,
            ))

    # ── Dry run: just print all tasks ──
    if dry_run:
        print(f"\n  {C.BOLD}Dry-run: {len(tasks)} requests would be made{C.RESET}\n")
        for t in tasks:
            params_str = f"?{_format_params(t.query_params)}" if t.query_params else ""
            print(f"  {C.CYAN}GET{C.RESET} {t.url}{params_str}")
            print(f"       {C.DIM}parser: {t.parser_command}{C.RESET}")
        print(f"\n{C.BOLD}{C.CYAN}{'═' * 70}{C.RESET}")
        print(f"  {C.BOLD}SUMMARY{C.RESET}: {stats.total} requests, {stats.skipped} skipped {C.DIM}(dry-run){C.RESET}")
        print(f"{C.BOLD}{C.CYAN}{'═' * 70}{C.RESET}")
        return

    if not tasks:
        print(f"\n  {C.YELLOW}No tasks to execute. Check config/api_test.yaml.{C.RESET}")
        return

    # ── Execute all tasks concurrently ──
    timeout_info = f"timeout={tasks[0].timeout}s, connect={tasks[0].connect_timeout}s"
    print(f"\n  {C.BOLD}Fetching {len(tasks)} requests "
          f"{C.DIM}(concurrency={concurrency}, {timeout_info}){C.RESET}\n")

    progress = {"done": 0, "total": len(tasks), "start_time": time.monotonic()}
    _print_progress(progress)

    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(verify=False) as client:
        await asyncio.gather(
            *(execute_task(client, task, sem, stats, progress) for task in tasks)
        )

    # Clear progress line
    sys.stdout.write("\r" + " " * 80 + "\r")
    sys.stdout.flush()

    # ── Print results ──
    for line in sorted(stats.results):
        print(line)

    # ── Summary ──
    print(f"\n{C.BOLD}{C.CYAN}{'═' * 70}{C.RESET}")
    print(f"  {C.BOLD}SUMMARY{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'═' * 70}{C.RESET}")
    print(f"  Total:   {C.BOLD}{stats.total}{C.RESET}")
    print(f"  Success: {C.GREEN}{C.BOLD}{stats.success}{C.RESET}")
    if stats.failed:
        print(f"  Failed:  {C.RED}{C.BOLD}{stats.failed}{C.RESET}")
    else:
        print(f"  Failed:  {stats.failed}")
    if stats.skipped:
        print(f"  Skipped: {C.DIM}{stats.skipped}{C.RESET}")
    else:
        print(f"  Skipped: {stats.skipped}")
    print(f"\n  Raw data saved to: {C.CYAN}{RAW_DIR}/{C.RESET}")

    # ── Unreachable devices report ──
    if stats.unreachable:
        unreachable_path = PROJECT_ROOT / "test_data" / "unreachable_devices.csv"
        unreachable_path.parent.mkdir(parents=True, exist_ok=True)
        seen_ips: set[str] = set()
        rows: list[dict[str, str]] = []
        for entry in stats.unreachable:
            if entry["ip"] not in seen_ips:
                seen_ips.add(entry["ip"])
                rows.append(entry)
        with open(unreachable_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ip", "hostname", "device_type", "error"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n  {C.YELLOW}Unreachable devices: {len(rows)}{C.RESET}")
        print(f"  Saved to: {C.CYAN}{unreachable_path}{C.RESET}")


def load_inventory_targets(inventory_path: str, sample_size: int | None) -> list[dict]:
    """
    Load targets from a CSV inventory file with optional random sampling.

    CSV expected columns: ip, hostname, device_type
    Sampling is balanced across device_types.
    """
    path = Path(inventory_path)
    if not path.exists():
        print(f"Error: Inventory file not found: {path}")
        sys.exit(1)

    devices_by_type: dict[str, list[dict]] = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ip = (row.get("ip") or "").strip()
            hostname = (row.get("hostname") or "").strip()
            raw_dt = (row.get("device_type") or "").strip().lower()
            if not ip or not raw_dt:
                continue
            dt = DEVICE_TYPE_MAP.get(raw_dt, raw_dt)
            devices_by_type.setdefault(dt, []).append({
                "ip": ip,
                "hostname": hostname or ip,
                "device_type": dt,
            })

    if not devices_by_type:
        print(f"Error: No valid devices found in {path}")
        sys.exit(1)

    total = sum(len(v) for v in devices_by_type.values())
    print(f"\n  {C.DIM}Inventory: {total} devices across "
          f"{len(devices_by_type)} device types{C.RESET}")
    for dt, devs in sorted(devices_by_type.items()):
        print(f"    {dt}: {len(devs)}")

    if sample_size is None:
        return [d for devs in devices_by_type.values() for d in devs]

    # Balanced random sampling
    num_types = len(devices_by_type)
    per_type = sample_size // num_types
    remainder = sample_size % num_types

    sampled: list[dict] = []
    leftover_types: list[str] = []

    for dt in sorted(devices_by_type.keys()):
        available = devices_by_type[dt]
        take = min(per_type, len(available))
        sampled.extend(random.sample(available, take))
        if len(available) > take:
            leftover_types.append(dt)

    # Redistribute remainder
    extra = remainder
    for dt in leftover_types:
        if extra <= 0:
            break
        already = {d["ip"] for d in sampled}
        available = [d for d in devices_by_type[dt] if d["ip"] not in already]
        take = min(extra, len(available))
        if take > 0:
            sampled.extend(random.sample(available, take))
            extra -= take

    print(f"\n  {C.BOLD}Sampled {len(sampled)} devices:{C.RESET}")
    type_counts: dict[str, int] = {}
    for d in sampled:
        type_counts[d["device_type"]] = type_counts.get(d["device_type"], 0) + 1
    for dt, count in sorted(type_counts.items()):
        print(f"    {dt}: {count}")

    return sampled


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch raw API data from real FNA/DNA/GNMSPING servers"
    )
    parser.add_argument(
        "--api", type=str, default=None,
        help="Only fetch specific API (substring match, e.g. 'fan', 'get_version')"
    )
    parser.add_argument(
        "--target", type=str, default=None,
        help="Only fetch for specific target IP"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print URLs without making actual requests"
    )
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
        help=f"Max parallel requests (default: {DEFAULT_CONCURRENCY})"
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to config file (default: config/api_test.yaml)"
    )
    parser.add_argument(
        "--timeout", type=float, default=None,
        help="Override read timeout in seconds (default: per-source config value)"
    )
    parser.add_argument(
        "--connect-timeout", type=float, default=10.0,
        help="Connect timeout in seconds (default: 10)"
    )
    parser.add_argument(
        "--no-clean", action="store_true",
        help="Do not clean test_data/raw/ before fetching (default: auto-clean)"
    )
    parser.add_argument(
        "--inventory", type=str, default=None,
        help="Path to device inventory CSV (columns: ip, hostname, device_type). "
             "Overrides targets from yaml config."
    )
    parser.add_argument(
        "--sample", type=int, default=None,
        help="Number of devices to randomly sample from inventory (balanced by device_type). "
             "Requires --inventory."
    )
    args = parser.parse_args()

    if args.sample and not args.inventory:
        print("Error: --sample requires --inventory")
        sys.exit(1)

    # Load .env for tokens
    load_env(ENV_PATH)

    # Load config
    global CONFIG_PATH
    if args.config:
        CONFIG_PATH = Path(args.config)
    config = load_config()

    # Override targets from inventory CSV if provided
    if args.inventory:
        config["targets"] = load_inventory_targets(args.inventory, args.sample)

    asyncio.run(fetch_all(
        config, args.api, args.target, args.dry_run, args.concurrency,
        timeout_override=args.timeout,
        connect_timeout=args.connect_timeout,
        clean_raw=not args.no_clean,
    ))


if __name__ == "__main__":
    main()
