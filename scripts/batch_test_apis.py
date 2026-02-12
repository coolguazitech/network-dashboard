#!/usr/bin/env python3
"""
API Batch Tester

Batch test all APIs defined in config/api_test.yaml with live progress display.

Usage:
    python scripts/batch_test_apis.py
    # or
    make test-apis
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
)

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables
load_dotenv()

console = Console()


# =============================================================================
# Data Models
# =============================================================================


class TestResult:
    """Single API test result."""

    def __init__(
        self,
        api_name: str,
        target_name: str,
        target_params: dict[str, Any],
        success: bool,
        status_code: int | None = None,
        response_time_ms: float | None = None,
        url: str | None = None,
        request_body: str | None = None,
        raw_data: str | None = None,
        parsed_data: str | None = None,
        error: str | None = None,
        error_detail: str | None = None,
    ):
        self.api_name = api_name
        self.target_name = target_name
        self.target_params = target_params
        self.success = success
        self.status_code = status_code
        self.response_time_ms = response_time_ms
        self.url = url
        self.request_body = request_body
        self.raw_data = raw_data
        self.parsed_data = parsed_data
        self.error = error
        self.error_detail = error_detail

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "api_name": self.api_name,
            "target_name": self.target_name,
            "target_params": self.target_params,
            "success": self.success,
            "status_code": self.status_code,
            "response_time_ms": self.response_time_ms,
            "url": self.url,
            "request_body": json.loads(self.request_body)
            if self.request_body
            else None,
            "raw_data": self.raw_data,
            "parsed_data": self.parsed_data,
            "error": self.error,
            "error_detail": self.error_detail,
        }


# =============================================================================
# Configuration Loading
# =============================================================================


def load_config(config_path: Path) -> dict[str, Any]:
    """Load API test configuration from YAML."""
    if not config_path.exists():
        console.print(f"[red]❌ Config file not found: {config_path}[/red]")
        sys.exit(1)

    with open(config_path) as f:
        return yaml.safe_load(f)


# =============================================================================
# URL Building
# =============================================================================


def substitute_placeholders(template: str, params: dict[str, Any]) -> str:
    """
    Substitute {placeholder} with values from params.

    Examples:
        "/api/{ip}" + {"ip": "10.1.1.1"} -> "/api/10.1.1.1"
        "{tenant_group}" + {"tenant_group": "F18"} -> "F18"
    """
    result = template
    for key, value in params.items():
        placeholder = f"{{{key}}}"
        if placeholder in result:
            # Handle list values (e.g., {ips} -> ["10.1.1.1", "10.1.1.2"])
            if isinstance(value, list):
                result = result.replace(placeholder, json.dumps(value))
            else:
                result = result.replace(placeholder, str(value))
    return result


def build_url(
    api_def: dict[str, Any],
    target_params: dict[str, Any],
    sources: dict[str, Any],
) -> str:
    """Build complete URL for API request."""
    source_name = api_def["source"]
    source_config = sources.get(source_name)

    if not source_config:
        raise ValueError(f"Unknown source: {source_name}")

    # Handle GNMSPING with tenant_group-based base_url selection
    if source_name == "GNMSPING":
        tenant_group = substitute_placeholders(
            api_def.get("tenant_group", ""), target_params
        )
        base_url = source_config["base_urls"].get(tenant_group)
        if not base_url:
            raise ValueError(
                f"No base_url for tenant_group '{tenant_group}' in GNMSPING"
            )
    else:
        base_url = source_config["base_url"]

    # Substitute endpoint path placeholders
    endpoint = substitute_placeholders(api_def["endpoint"], target_params)

    return base_url.rstrip("/") + endpoint


def build_query_params(
    api_def: dict[str, Any], target_params: dict[str, Any]
) -> dict[str, str]:
    """Build query parameters with placeholder substitution."""
    query_params = api_def.get("query_params", {})
    result = {}
    for key, value_template in query_params.items():
        value = substitute_placeholders(str(value_template), target_params)
        result[key] = value
    return result


def build_request_body(
    api_def: dict[str, Any],
    target_params: dict[str, Any],
    sources: dict[str, Any],
) -> str | None:
    """Build request body from template with placeholder substitution.

    Also injects source-level env vars (e.g., app_name_env, token_env)
    so body templates can use {app_name} and {token} placeholders.
    """
    body_template = api_def.get("request_body_template")
    if not body_template:
        return None

    # Merge source-level env vars into params for substitution
    merged_params = dict(target_params)
    source_name = api_def.get("source")
    source_config = sources.get(source_name, {})
    for key in ("app_name", "token"):
        env_key = source_config.get(f"{key}_env")
        if env_key:
            value = os.getenv(env_key)
            if value:
                merged_params[key] = value

    return substitute_placeholders(body_template, merged_params)


def get_auth_header(api_def: dict[str, Any], sources: dict[str, Any]) -> dict[str, str]:
    """Get authorization header if required."""
    if not api_def.get("requires_auth", False):
        return {}

    source_name = api_def["source"]
    source_config = sources.get(source_name, {})
    token_env = source_config.get("token_env")

    if not token_env:
        return {}

    token = os.getenv(token_env)
    if not token:
        console.print(
            f"[yellow]⚠️  Warning: {token_env} not set in environment[/yellow]"
        )
        return {}

    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# API Testing
# =============================================================================


async def test_api(
    api_def: dict[str, Any],
    target: dict[str, Any],
    sources: dict[str, Any],
    client: httpx.AsyncClient,
) -> TestResult:
    """Test a single API with a single target."""
    api_name = api_def["name"]
    target_name = target["name"]
    target_params = target["params"]
    parsed_data_type = api_def.get("parsed_data")

    try:
        # Build request
        url = build_url(api_def, target_params, sources)
        method = api_def.get("method", "GET").upper()
        query_params = build_query_params(api_def, target_params)
        headers = get_auth_header(api_def, sources)

        # Start timer
        start_time = time.time()

        # Execute request
        body = None
        if method == "POST":
            body = build_request_body(api_def, target_params, sources)
            response = await client.post(
                url,
                params=query_params,
                headers=headers,
                content=body,
                timeout=10.0,
            )
        else:  # GET
            response = await client.get(
                url,
                params=query_params,
                headers=headers,
                timeout=10.0,
            )

        # Calculate response time
        response_time_ms = (time.time() - start_time) * 1000

        # Check response
        response.raise_for_status()

        return TestResult(
            api_name=api_name,
            target_name=target_name,
            target_params=target_params,
            success=True,
            status_code=response.status_code,
            response_time_ms=response_time_ms,
            url=str(response.request.url),
            request_body=body,
            raw_data=response.text,
            parsed_data=parsed_data_type,
        )

    except httpx.HTTPStatusError as e:
        response_time_ms = (time.time() - start_time) * 1000
        return TestResult(
            api_name=api_name,
            target_name=target_name,
            target_params=target_params,
            success=False,
            status_code=e.response.status_code,
            response_time_ms=response_time_ms,
            url=str(e.request.url),
            request_body=body,
            parsed_data=parsed_data_type,
            error=f"HTTP {e.response.status_code}",
            error_detail=e.response.text[:200],
        )

    except httpx.TimeoutException as e:
        return TestResult(
            api_name=api_name,
            target_name=target_name,
            target_params=target_params,
            success=False,
            status_code=0,
            request_body=body,
            parsed_data=parsed_data_type,
            error="TimeoutException",
            error_detail=f"Connection timeout after 10.0 seconds: {str(e)}",
        )

    except Exception as e:
        return TestResult(
            api_name=api_name,
            target_name=target_name,
            target_params=target_params,
            success=False,
            status_code=0,
            request_body=body,
            parsed_data=parsed_data_type,
            error=type(e).__name__,
            error_detail=str(e),
        )


def match_target_filter(api_def: dict[str, Any], target: dict[str, Any]) -> bool:
    """Check if a target matches the API's target_filter."""
    target_filter = api_def.get("target_filter")
    if not target_filter:
        # No filter = match all targets
        return True

    # Check type filter (e.g., "switch" or "gnmsping")
    filter_type = target_filter.get("type")
    if filter_type and target.get("type") != filter_type:
        return False

    # Check device_type filter (e.g., "hpe", "cisco_ios", "cisco_nxos")
    filter_device_type = target_filter.get("device_type")
    if filter_device_type:
        target_device_type = target.get("params", {}).get("device_type")
        if target_device_type != filter_device_type:
            return False

    return True


def build_test_matrix(
    apis: list[dict[str, Any]], targets: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Build test matrix by matching APIs to targets using target_filter."""
    tests = []
    for api in apis:
        for target in targets:
            if match_target_filter(api, target):
                tests.append((api, target))
    return tests


async def test_all_apis(
    config: dict[str, Any], progress: Progress, task_id: TaskID
) -> list[TestResult]:
    """Test all APIs against matched targets with live progress."""
    sources = config["settings"]["sources"]
    targets = config["test_targets"]
    apis = config["apis"]

    # Build test matrix with target_filter matching
    tests = build_test_matrix(apis, targets)
    total_tests = len(tests)

    console.print(f"📊 Found {len(apis)} APIs, {len(targets)} targets -> {total_tests} matched tests\n")

    results: list[TestResult] = []

    async with httpx.AsyncClient() as client:
        for api, target in tests:
            result = await test_api(api, target, sources, client)
            results.append(result)

            # Update progress
            progress.update(task_id, advance=1)

            # Log result
            if result.success:
                console.print(
                    f"  ✅ {result.api_name} @ {result.target_name} "
                    f"({result.response_time_ms:.0f}ms)"
                )
            else:
                console.print(
                    f"  ❌ {result.api_name} @ {result.target_name} "
                    f"({result.error})"
                )

    return results


# =============================================================================
# Report Generation
# =============================================================================


def save_report(results: list[TestResult], config_path: Path, output_dir: Path) -> Path:
    """Save test results to JSON report."""
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    report_path = output_dir / f"api_test_{timestamp}.json"

    # Calculate summary
    success_count = sum(1 for r in results if r.success)
    failed_count = len(results) - success_count

    report = {
        "timestamp": timestamp,
        "config_file": str(config_path),
        "summary": {
            "total_tests": len(results),
            "success": success_count,
            "failed": failed_count,
        },
        "results": [r.to_dict() for r in results],
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    return report_path


# =============================================================================
# Main
# =============================================================================


async def main():
    """Main entry point."""
    console.print("\n[bold cyan]🚀 API Batch Tester[/bold cyan]")

    # Load config
    config_path = PROJECT_ROOT / "config" / "api_test.yaml"
    console.print(f"📄 Config: {config_path}")

    config = load_config(config_path)

    # Prepare output directory
    output_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(exist_ok=True)

    # Test all APIs with progress bar
    console.print("\n[bold]Testing APIs...[/bold]")

    total_tests = len(build_test_matrix(config["apis"], config["test_targets"]))

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("Testing...", total=total_tests)
        start_time = time.time()
        results = await test_all_apis(config, progress, task_id)
        duration = time.time() - start_time

    # Print summary
    success_count = sum(1 for r in results if r.success)
    failed_count = len(results) - success_count

    console.print("\n[bold]📝 Summary:[/bold]")
    console.print(f"  ✅ Success: {success_count}/{len(results)}")
    console.print(f"  ❌ Failed: {failed_count}/{len(results)}")
    console.print(f"  ⏱️  Duration: {duration:.2f}s\n")

    # Save report
    report_path = save_report(results, config_path, output_dir)
    console.print(f"💾 Report saved to: [cyan]{report_path}[/cyan]\n")


if __name__ == "__main__":
    asyncio.run(main())
