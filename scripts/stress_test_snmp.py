"""
SNMP 採集壓力測試 — 模擬公司生產環境

模擬條件：
  - 400 台設備（350 台 SNMP 正常，50 台 SNMP 不通但 ping 可達）
  - 2 個 community string（tccd03ro, public）
  - SNMP_CONCURRENCY=50（全域 semaphore）
  - 同時跑多個 SNMP job（模擬 scheduler 同時觸發）

驗證項目：
  1. SNMP 不通的設備不會阻塞正常設備
  2. 所有正常設備都能在合理時間內完成
  3. negative cache 讓第二輪直接跳過不通設備
  4. community cache 讓已知設備不再重新探測
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock
from dataclasses import dataclass

# Setup path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("stress_test")

# ── Config ──
N_DEVICES = 400
N_UNREACHABLE = 50  # SNMP 不通但 ping 可達
N_COMMUNITIES = 2
CONCURRENCY = 50
PROBE_TIMEOUT = 3.0   # session_cache probe timeout
PROBE_RETRIES = 1
WALK_TIMEOUT = 120.0
NORMAL_WALK_LATENCY = 0.05   # 正常設備 walk 耗時 (秒)
NORMAL_GET_LATENCY = 0.02    # 正常設備 get 耗時 (秒)

# Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


@dataclass
class FakeTarget:
    ip: str
    community: str
    port: int = 161
    timeout: float = 3.0
    retries: int = 1


class RealisticMockEngine:
    """
    模擬真實 SNMP 行為：
    - 正常設備：快速回應
    - 不通設備：等到 timeout 才 raise SnmpTimeoutError
    """

    def __init__(self, unreachable_ips: set[str]):
        self._unreachable = unreachable_ips
        self._get_count = 0
        self._walk_count = 0
        self._timeout_count = 0

    async def get(self, target, *oids):
        from app.snmp.engine import SnmpTimeoutError
        self._get_count += 1

        if target.ip in self._unreachable:
            # 模擬真實行為：等到 per-PDU timeout
            pdu_wait = min(target.timeout * (target.retries + 1) + 2, 30.0)
            await asyncio.sleep(pdu_wait)
            self._timeout_count += 1
            raise SnmpTimeoutError(f"getCmd hung: {target.ip}")

        await asyncio.sleep(NORMAL_GET_LATENCY)
        return {"1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.11.2.3.7.11"}

    async def walk(self, target, oid_prefix, max_repetitions=None):
        from app.snmp.engine import SnmpTimeoutError
        self._walk_count += 1

        if target.ip in self._unreachable:
            pdu_wait = min(target.timeout * (target.retries + 1) + 2, 30.0)
            await asyncio.sleep(pdu_wait)
            self._timeout_count += 1
            raise SnmpTimeoutError(f"bulkCmd hung: {target.ip}")

        await asyncio.sleep(NORMAL_WALK_LATENCY)
        # 回傳假 OID 資料
        return [(f"{oid_prefix}.{i}", f"value_{i}") for i in range(1, 25)]


async def simulate_collection_job(
    job_name: str,
    devices: list[dict],
    engine: RealisticMockEngine,
    sem: asyncio.Semaphore,
    communities: list[str],
) -> dict:
    """模擬一個 SNMP collection job 的完整流程"""
    from app.snmp.session_cache import SnmpSessionCache
    from app.snmp.engine import SnmpTimeoutError

    cache = SnmpSessionCache(
        engine=engine,
        communities=communities,
        port=161,
        timeout=8.0,  # walk 用的 timeout
        retries=2,
    )

    results = {"ok": 0, "timeout": 0, "cached_skip": 0}

    async def collect_one(dev):
        async with sem:
            ip = dev["ip"]
            try:
                target = await cache.get_target(ip)
                # 模擬 walk
                await engine.walk(target, "1.3.6.1.2.1.2.2.1")
                results["ok"] += 1
            except SnmpTimeoutError as e:
                if "cached" in str(e):
                    results["cached_skip"] += 1
                else:
                    results["timeout"] += 1

    await asyncio.gather(*[collect_one(d) for d in devices])
    return results


async def main():
    from app.snmp.session_cache import SnmpSessionCache

    # 清除任何先前的 cache
    SnmpSessionCache.clear_all()

    # 建立設備清單
    devices = []
    unreachable_ips = set()
    for i in range(N_DEVICES):
        ip = f"10.63.85.{i + 1}"
        devices.append({"hostname": f"DEVICE-{i+1:03d}", "ip": ip})
        if i < N_UNREACHABLE:
            unreachable_ips.add(ip)

    communities = ["tccd03ro", "public"]
    engine = RealisticMockEngine(unreachable_ips)
    sem = asyncio.Semaphore(CONCURRENCY)

    print(f"\n{BOLD}{CYAN}{'='*60}")
    print(f"  SNMP 壓力測試 — 模擬公司生產環境")
    print(f"{'='*60}{RESET}\n")
    print(f"  設備總數:     {N_DEVICES}")
    print(f"  SNMP 不通:    {N_UNREACHABLE} 台 (ping 可達)")
    print(f"  SNMP 正常:    {N_DEVICES - N_UNREACHABLE} 台")
    print(f"  Community:    {len(communities)} 個")
    print(f"  Concurrency:  {CONCURRENCY} (全域 semaphore)")
    print(f"  Probe timeout: {PROBE_TIMEOUT}s × {PROBE_RETRIES+1} retries")
    print()

    # ── 測試 1: 單一 job，第一輪 ──
    print(f"{BOLD}{CYAN}── 測試 1: 單一 job (第一輪，含 community 探測) ──{RESET}")
    t0 = time.monotonic()
    r1 = await simulate_collection_job("get_fan", devices, engine, sem, communities)
    t1 = time.monotonic() - t0
    print(f"  完成: {r1['ok']}/{N_DEVICES} ok, {r1['timeout']} timeout, "
          f"{r1['cached_skip']} cached_skip")
    print(f"  耗時: {t1:.1f}s")
    print(f"  Engine calls: {engine._get_count} GET, {engine._walk_count} WALK, "
          f"{engine._timeout_count} timeouts")
    ok1 = r1["ok"] == N_DEVICES - N_UNREACHABLE
    print(f"  {GREEN}✓{RESET} 所有正常設備完成" if ok1 else f"  {RED}✗ 正常設備未全部完成{RESET}")
    print()

    # 重置 engine 計數器
    engine._get_count = 0
    engine._walk_count = 0
    engine._timeout_count = 0

    # ── 測試 2: 單一 job，第二輪（negative cache 生效） ──
    print(f"{BOLD}{CYAN}── 測試 2: 單一 job (第二輪，negative cache 生效) ──{RESET}")
    t0 = time.monotonic()
    r2 = await simulate_collection_job("get_fan_round2", devices, engine, sem, communities)
    t2 = time.monotonic() - t0
    print(f"  完成: {r2['ok']}/{N_DEVICES} ok, {r2['timeout']} timeout, "
          f"{r2['cached_skip']} cached_skip")
    print(f"  耗時: {t2:.1f}s")
    print(f"  Engine calls: {engine._get_count} GET, {engine._walk_count} WALK, "
          f"{engine._timeout_count} timeouts")
    ok2 = r2["cached_skip"] == N_UNREACHABLE
    print(f"  {GREEN}✓{RESET} 不通設備全部 cached skip (0s)" if ok2
          else f"  {RED}✗ 未全部 cached skip{RESET}")
    speedup = t1 / t2 if t2 > 0 else float('inf')
    print(f"  {GREEN}✓{RESET} 第二輪快 {speedup:.1f}x" if t2 < t1 * 0.5
          else f"  {YELLOW}△ 加速不夠明顯{RESET}")
    print()

    # 重置 engine 計數器
    engine._get_count = 0
    engine._walk_count = 0
    engine._timeout_count = 0

    # ── 測試 3: 4 個 job 同時跑（模擬 scheduler 同時觸發多個 client-related job） ──
    print(f"{BOLD}{CYAN}── 測試 3: 4 個 job 同時跑 (模擬 scheduler) ──{RESET}")
    t0 = time.monotonic()
    job_names = ["get_mac_table", "get_interface_status", "get_static_acl", "get_fan"]
    results = await asyncio.gather(*[
        simulate_collection_job(name, devices, engine, sem, communities)
        for name in job_names
    ])
    t3 = time.monotonic() - t0

    total_ok = sum(r["ok"] for r in results)
    total_timeout = sum(r["timeout"] for r in results)
    total_cached = sum(r["cached_skip"] for r in results)
    print(f"  4 jobs 合計: {total_ok} ok, {total_timeout} timeout, {total_cached} cached_skip")
    print(f"  耗時: {t3:.1f}s (4 job 共用 semaphore={CONCURRENCY})")
    print(f"  Engine calls: {engine._get_count} GET, {engine._walk_count} WALK")

    expected_ok = (N_DEVICES - N_UNREACHABLE) * len(job_names)
    ok3 = total_ok == expected_ok
    print(f"  {GREEN}✓{RESET} 所有正常設備 × 4 jobs = {expected_ok} 全部完成" if ok3
          else f"  {RED}✗ 預期 {expected_ok}，實際 {total_ok}{RESET}")
    ok4 = total_cached == N_UNREACHABLE * len(job_names)
    print(f"  {GREEN}✓{RESET} 不通設備全部 cached skip" if ok4
          else f"  {RED}✗ cached skip 不正確{RESET}")
    print()

    # ── 測試 4: 不通設備不會阻塞正常設備的時間驗證 ──
    print(f"{BOLD}{CYAN}── 測試 4: 阻塞時間驗證 ──{RESET}")

    # 理論最佳時間（只有正常設備）：350 台 / 50 concurrency × 0.07s per device
    ideal_time = (N_DEVICES - N_UNREACHABLE) / CONCURRENCY * (NORMAL_WALK_LATENCY + NORMAL_GET_LATENCY)
    print(f"  理論最佳 (無不通設備): {ideal_time:.1f}s")
    print(f"  第一輪實際: {t1:.1f}s (含 community 探測 timeout)")
    print(f"  第二輪實際: {t2:.1f}s (negative cache 生效)")
    print(f"  4 job 同時: {t3:.1f}s (共用 semaphore)")

    # 如果第二輪耗時 < 理論的 3 倍，表示不通設備沒有嚴重阻塞
    ok5 = t2 < ideal_time * 5
    print(f"  {GREEN}✓{RESET} 第二輪接近理論時間 (negative cache 有效)" if ok5
          else f"  {RED}✗ 第二輪仍然太慢，negative cache 可能沒生效{RESET}")
    print()

    # ── 總結 ──
    all_pass = all([ok1, ok2, ok3, ok4, ok5])
    print(f"{BOLD}{CYAN}{'='*60}")
    print(f"  總結")
    print(f"{'='*60}{RESET}")
    if all_pass:
        print(f"  {GREEN}{BOLD}ALL CHECKS PASSED{RESET}")
    else:
        print(f"  {RED}{BOLD}SOME CHECKS FAILED{RESET}")

    # Cache 狀態
    print(f"\n  Community cache: {len(SnmpSessionCache._community_cache)} entries")
    print(f"  Negative cache:  {len(SnmpSessionCache._negative_cache)} entries")
    print()

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
