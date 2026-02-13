#!/usr/bin/env python3
"""
Fetch raw API data from real FNA/DNA/GNMSPING servers.

Reads config/api_test.yaml, calls each API for each target switch,
and saves raw responses to test_data/raw/{api}_{device_type}_{ip}.txt

Usage:
    python scripts/fetch_raw.py                    # fetch all
    python scripts/fetch_raw.py --api get_fan      # only specific API
    python scripts/fetch_raw.py --target 10.1.1.1  # only specific target
    python scripts/fetch_raw.py --dry-run          # print URLs only
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx
import yaml

# ── Resolve paths ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "api_test.yaml"
RAW_DIR = PROJECT_ROOT / "test_data" / "raw"
ENV_PATH = PROJECT_ROOT / ".env"

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
            print(f"  Warning: {token_env} not set or is placeholder")
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


def fetch_all(config: dict, api_filter: str | None, target_filter: str | None,
              dry_run: bool) -> None:
    """Main fetch loop."""
    sources = config.get("sources", {})
    endpoints = config.get("endpoints", {})
    targets = config.get("targets", [])
    apis = config.get("apis", [])
    ping_targets = config.get("ping_targets", {})

    # Stats
    total = 0
    success = 0
    failed = 0
    skipped = 0

    print("=" * 70)
    print("FETCH RAW DATA")
    print("=" * 70)

    for api_def in apis:
        api_name = api_def["name"]
        source_name = api_def["source"]
        # Endpoint comes from top-level endpoints section (fallback to inline for compat)
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
            print(f"\n--- {api_name} ({description}) ---")
            print(f"  Skipped: endpoint not configured in endpoints.{api_name}")
            skipped += 1
            continue

        source_config = sources.get(source_name, {})
        base_url = source_config.get("base_url", "")
        timeout = source_config.get("timeout", 30)
        headers = get_auth_headers(source_config)

        if not base_url:
            print(f"\n--- {api_name} ({description}) ---")
            print(f"  Skipped: sources.{source_name}.base_url not configured")
            skipped += 1
            continue

        # ── GNMSPING (POST, special handling) ──
        if api_name == "ping_batch":
            total += 1
            addresses = ping_targets.get("addresses", [])
            if not addresses:
                print(f"\n--- {api_name} ---")
                print("  Skipped: no ping_targets.addresses configured")
                skipped += 1
                continue

            endpoint = endpoint_template
            url = build_url(base_url, endpoint)

            # Build request body
            app_name = os.environ.get("GNMSPING_APP_NAME", "")
            token = os.environ.get("GNMSPING_TOKEN", "")
            body = {
                "app_name": app_name,
                "token": token,
                "addresses": addresses,
            }

            print(f"\n--- {api_name} ({description}) ---")
            print(f"  POST {url}")
            print(f"  Body: {len(addresses)} addresses")

            if dry_run:
                skipped += 1
                continue

            try:
                resp = httpx.post(url, json=body, timeout=timeout)
                status = resp.status_code
                content = resp.text
                filepath = save_raw(api_name, "all", "batch", content)
                print(f"  -> HTTP {status}, {len(content)} bytes -> {filepath.name}")
                if 200 <= status < 300:
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"  -> ERROR: {e}")
                failed += 1

            continue

        # ── FNA / DNA APIs (GET, per target) ──
        for target in targets:
            ip = target.get("ip", "")
            hostname = target.get("hostname", "") or ip
            raw_device_type = target.get("device_type", "")
            device_type = DEVICE_TYPE_MAP.get(raw_device_type, raw_device_type)

            # Skip targets with empty IP
            if not ip:
                continue

            # Filter by target
            if target_filter and target_filter != ip:
                continue

            total += 1

            # Resolve endpoint and query params
            endpoint = resolve_endpoint(endpoint_template, ip, device_type)
            query_params = resolve_query_params(
                query_params_template, ip, device_type
            )
            url = build_url(base_url, endpoint)

            # Resolve parser command for display
            resolved_parser = parser_cmd.replace("{device_type}", device_type)

            print(f"\n--- {api_name} / {device_type} / {ip} ({hostname}) ---")
            print(f"  GET {url}" + (f"?{_format_params(query_params)}" if query_params else ""))
            print(f"  Parser: {resolved_parser}")

            if dry_run:
                skipped += 1
                continue

            try:
                resp = httpx.get(
                    url, params=query_params, headers=headers, timeout=timeout
                )
                status = resp.status_code
                content = resp.text
                filepath = save_raw(api_name, device_type, ip, content)
                print(f"  -> HTTP {status}, {len(content)} bytes -> {filepath.name}")
                if 200 <= status < 300:
                    success += 1
                else:
                    failed += 1
                    print(f"  -> Response: {content[:200]}")
            except httpx.ConnectError:
                print(f"  -> ERROR: Connection refused ({base_url})")
                failed += 1
            except httpx.TimeoutException:
                print(f"  -> ERROR: Timeout after {timeout}s")
                failed += 1
            except Exception as e:
                print(f"  -> ERROR: {type(e).__name__}: {e}")
                failed += 1

    # ── Summary ──
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total:   {total}")
    if dry_run:
        print(f"  Dry-run: {skipped} (no actual requests made)")
    else:
        print(f"  Success: {success}")
        print(f"  Failed:  {failed}")
        print(f"  Skipped: {skipped}")
    print(f"\n  Raw data saved to: {RAW_DIR}/")


def _format_params(params: dict[str, str] | None) -> str:
    """Format query params for display."""
    if not params:
        return ""
    return "&".join(f"{k}={v}" for k, v in params.items())


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

    fetch_all(config, args.api, args.target, args.dry_run)


if __name__ == "__main__":
    main()
