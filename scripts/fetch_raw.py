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
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import yaml

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
    "cisco_ios": "ios",
    "cisco_nxos": "nxos",
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
    method: str
    url: str
    query_params: dict[str, str] | None
    headers: dict[str, str]
    body: dict | None
    timeout: float
    save_api_name: str
    save_device_type: str
    save_ip: str
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


async def execute_task(
    client: httpx.AsyncClient,
    task: FetchTask,
    sem: asyncio.Semaphore,
    stats: FetchStats,
) -> None:
    """Execute a single fetch task with semaphore-based concurrency control."""
    async with sem:
        try:
            if task.method == "POST":
                resp = await client.post(
                    task.url, json=task.body, timeout=task.timeout
                )
            else:
                resp = await client.get(
                    task.url,
                    params=task.query_params,
                    headers=task.headers,
                    timeout=task.timeout,
                )

            status = resp.status_code
            content = resp.text
            filepath = save_raw(
                task.save_api_name, task.save_device_type, task.save_ip, content
            )

            if 200 <= status < 300:
                stats.success += 1
                stats.results.append(
                    f"  OK   {task.display_label} -> HTTP {status}, "
                    f"{len(content)} bytes -> {filepath.name}"
                )
            else:
                stats.failed += 1
                stats.results.append(
                    f"  FAIL {task.display_label} -> HTTP {status}: "
                    f"{content[:100]}"
                )

        except httpx.ConnectError:
            stats.failed += 1
            stats.results.append(
                f"  FAIL {task.display_label} -> Connection refused"
            )
        except httpx.TimeoutException:
            stats.failed += 1
            stats.results.append(
                f"  FAIL {task.display_label} -> Timeout after {task.timeout}s"
            )
        except Exception as e:
            stats.failed += 1
            stats.results.append(
                f"  FAIL {task.display_label} -> {type(e).__name__}: {e}"
            )


async def fetch_all(
    config: dict,
    api_filter: str | None,
    target_filter: str | None,
    dry_run: bool,
    concurrency: int,
) -> None:
    """Main fetch loop — builds task list then executes concurrently."""
    sources = config.get("sources", {})
    endpoints = config.get("endpoints", {})
    targets = config.get("targets", [])
    apis = config.get("apis", [])
    ping_targets = config.get("ping_targets", {})

    stats = FetchStats()
    tasks: list[FetchTask] = []
    token_warned: set[str] = set()

    print("=" * 70)
    print("FETCH RAW DATA")
    print("=" * 70)

    for api_def in apis:
        api_name = api_def["name"]
        source_name = api_def["source"]
        endpoint_template = endpoints.get(api_name, "") or api_def.get("endpoint", "")
        method = api_def.get("method", "GET").upper()
        query_params_template = api_def.get("query_params")
        parser_cmd = api_def.get("parser_command", "")
        description = api_def.get("description", "")

        # Filter by API name
        if api_filter and api_filter not in api_name:
            continue

        # Skip if endpoint not configured
        if not endpoint_template:
            print(f"  SKIP {api_name}: endpoint not configured")
            stats.skipped += 1
            continue

        source_config = sources.get(source_name, {})
        base_url = source_config.get("base_url", "")
        timeout = source_config.get("timeout", 30)
        headers = get_auth_headers(source_config)

        # Warn about missing token once per source
        auth = source_config.get("auth")
        if auth and auth.get("token_env"):
            token_env = auth["token_env"]
            token_val = os.environ.get(token_env, "")
            if (not token_val or token_val.startswith("<")) and token_env not in token_warned:
                print(f"  WARN {token_env} not set or is placeholder")
                token_warned.add(token_env)

        if not base_url:
            print(f"  SKIP {api_name}: sources.{source_name}.base_url not configured")
            stats.skipped += 1
            continue

        # ── GNMSPING (POST) ──
        if api_name == "ping_batch":
            addresses = ping_targets.get("addresses", [])
            if not addresses:
                print(f"  SKIP {api_name}: no ping_targets.addresses configured")
                stats.skipped += 1
                continue

            url = build_url(base_url, endpoint_template)
            app_name_val = os.environ.get("GNMSPING_APP_NAME", "")
            token_val = os.environ.get("GNMSPING_TOKEN", "")
            body = {
                "app_name": app_name_val,
                "token": token_val,
                "addresses": addresses,
            }

            stats.total += 1
            tasks.append(FetchTask(
                api_name=api_name,
                description=description,
                method="POST",
                url=url,
                query_params=None,
                headers={},
                body=body,
                timeout=timeout,
                save_api_name=api_name,
                save_device_type="all",
                save_ip="batch",
                display_label=f"{api_name} ({len(addresses)} IPs)",
                parser_command="ping_batch",
            ))
            continue

        # ── FNA / DNA APIs (GET, per target) ──
        for target in targets:
            ip = target.get("ip", "")
            hostname = target.get("hostname", "") or ip
            raw_device_type = target.get("device_type", "")
            device_type = DEVICE_TYPE_MAP.get(raw_device_type, raw_device_type)

            if not ip:
                continue
            if target_filter and target_filter != ip:
                continue

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
                method=method,
                url=url,
                query_params=query_params,
                headers=headers,
                body=None,
                timeout=timeout,
                save_api_name=api_name,
                save_device_type=device_type,
                save_ip=ip,
                display_label=label,
                parser_command=resolved_parser,
            ))

    # ── Dry run: just print all tasks ──
    if dry_run:
        print(f"\nDry-run: {len(tasks)} requests would be made\n")
        for t in tasks:
            params_str = f"?{_format_params(t.query_params)}" if t.query_params else ""
            print(f"  {t.method} {t.url}{params_str}")
            print(f"       -> parser: {t.parser_command}")
        print(f"\n{'=' * 70}")
        print(f"SUMMARY: {stats.total} requests, {stats.skipped} skipped (dry-run)")
        print("=" * 70)
        return

    if not tasks:
        print("\nNo tasks to execute. Check config/api_test.yaml.")
        return

    # ── Execute all tasks concurrently ──
    print(f"\nExecuting {len(tasks)} requests (concurrency={concurrency})...\n")

    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(verify=False) as client:
        await asyncio.gather(
            *(execute_task(client, task, sem, stats) for task in tasks)
        )

    # ── Print results ──
    for line in sorted(stats.results):
        print(line)

    # ── Summary ──
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total:   {stats.total}")
    print(f"  Success: {stats.success}")
    print(f"  Failed:  {stats.failed}")
    print(f"  Skipped: {stats.skipped}")
    print(f"\n  Raw data saved to: {RAW_DIR}/")


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
    args = parser.parse_args()

    # Load .env for tokens
    load_env(ENV_PATH)

    # Load config
    global CONFIG_PATH
    if args.config:
        CONFIG_PATH = Path(args.config)
    config = load_config()

    asyncio.run(fetch_all(config, args.api, args.target, args.dry_run, args.concurrency))


if __name__ == "__main__":
    main()
