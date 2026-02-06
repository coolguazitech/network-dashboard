"""
Report Service.

Sanity Check 報告生成服務。
提供 HTML 報告生成功能，包含整體通過率、各指標統計、失敗詳情。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.indicator_service import IndicatorService


class ReportService:
    """Sanity Check 報告生成服務。"""

    def __init__(self) -> None:
        """初始化報告服務。"""
        self.indicator_service = IndicatorService()

    async def generate_html_report(
        self,
        maintenance_id: str,
        include_details: bool,
        session: AsyncSession,
    ) -> str:
        """
        生成完整的 HTML 報告。

        Args:
            maintenance_id: 歲修 ID
            include_details: 是否包含失敗詳情
            session: 資料庫 session

        Returns:
            完整的 HTML 字串
        """
        # 獲取摘要資料
        summary = await self.indicator_service.get_dashboard_summary(
            maintenance_id, session
        )

        # 獲取詳細失敗列表
        results = await self.indicator_service.evaluate_all(maintenance_id, session)

        indicator_details = {}
        for indicator_type, result in results.items():
            indicator_details[indicator_type] = {
                "indicator_type": result.indicator_type,
                "total_count": result.total_count,
                "pass_count": result.pass_count,
                "fail_count": result.fail_count,
                "pass_rate": result.pass_rate_percent,
                "failures": result.failures or [],
            }

        # 使用台灣時區 (UTC+8)
        tw_tz = timezone(timedelta(hours=8))
        generated_at = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S (台灣時間)")

        return self._render_html(
            maintenance_id=maintenance_id,
            generated_at=generated_at,
            summary=summary,
            indicator_details=indicator_details,
            include_details=include_details,
        )

    def _render_html(
        self,
        maintenance_id: str,
        generated_at: str,
        summary: dict[str, Any],
        indicator_details: dict[str, Any],
        include_details: bool,
    ) -> str:
        """渲染 HTML 報告。"""
        overall = summary.get("overall", {})
        overall_pass_rate = overall.get("pass_rate", 0)
        overall_total = overall.get("total_count", 0)
        overall_pass = overall.get("pass_count", 0)
        overall_fail = overall.get("fail_count", 0)

        # 決定整體狀態顏色
        if overall_pass_rate >= 95:
            status_color = "#10b981"  # green
            status_text = "PASS"
        elif overall_pass_rate >= 80:
            status_color = "#f59e0b"  # yellow
            status_text = "WARNING"
        else:
            status_color = "#ef4444"  # red
            status_text = "FAIL"

        # 生成指標卡片 HTML
        indicator_cards_html = self._generate_indicator_cards(
            summary.get("indicators", {}),
            indicator_details,
            include_details,
        )

        html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sanity Check Report - {maintenance_id}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: #e2e8f0;
            min-height: 100vh;
            padding: 2rem;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        .header {{
            text-align: center;
            margin-bottom: 2rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid #334155;
        }}

        .header h1 {{
            font-size: 2rem;
            color: #22d3ee;
            margin-bottom: 0.5rem;
        }}

        .header .meta {{
            color: #94a3b8;
            font-size: 0.875rem;
        }}

        .overall-status {{
            background: #1e293b;
            border-radius: 1rem;
            padding: 2rem;
            margin-bottom: 2rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 1rem;
            border: 1px solid #334155;
        }}

        .status-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.75rem 1.5rem;
            border-radius: 0.5rem;
            font-weight: 600;
            font-size: 1.25rem;
            background: {status_color}20;
            color: {status_color};
            border: 2px solid {status_color};
        }}

        .status-badge::before {{
            content: '';
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: {status_color};
        }}

        .overall-stats {{
            display: flex;
            gap: 2rem;
            flex-wrap: wrap;
        }}

        .stat {{
            text-align: center;
        }}

        .stat-value {{
            font-size: 2rem;
            font-weight: 700;
            color: #22d3ee;
        }}

        .stat-label {{
            font-size: 0.75rem;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .progress-bar {{
            width: 200px;
            height: 8px;
            background: #334155;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 0.5rem;
        }}

        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #22d3ee, #06b6d4);
            border-radius: 4px;
            width: {overall_pass_rate:.1f}%;
        }}

        .indicators-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        .indicator-card {{
            background: #1e293b;
            border-radius: 0.75rem;
            padding: 1.5rem;
            border: 1px solid #334155;
        }}

        .indicator-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }}

        .indicator-name {{
            font-size: 1.125rem;
            font-weight: 600;
            color: #f1f5f9;
            text-transform: capitalize;
        }}

        .indicator-rate {{
            font-size: 1.5rem;
            font-weight: 700;
        }}

        .rate-pass {{ color: #10b981; }}
        .rate-warning {{ color: #f59e0b; }}
        .rate-fail {{ color: #ef4444; }}

        .indicator-stats {{
            display: flex;
            gap: 1rem;
            margin-bottom: 1rem;
            font-size: 0.875rem;
            color: #94a3b8;
        }}

        .indicator-stats span {{
            display: flex;
            align-items: center;
            gap: 0.25rem;
        }}

        .failures-section {{
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid #334155;
        }}

        .failures-title {{
            font-size: 0.75rem;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.75rem;
        }}

        .failure-list {{
            max-height: 200px;
            overflow-y: auto;
        }}

        .failure-item {{
            padding: 0.5rem 0.75rem;
            background: #0f172a;
            border-radius: 0.375rem;
            margin-bottom: 0.5rem;
            font-size: 0.8125rem;
            font-family: 'SF Mono', Monaco, 'Consolas', monospace;
            color: #f87171;
        }}

        .failure-item:last-child {{
            margin-bottom: 0;
        }}

        .footer {{
            text-align: center;
            padding-top: 2rem;
            border-top: 1px solid #334155;
            color: #64748b;
            font-size: 0.75rem;
        }}

        @media print {{
            body {{
                background: white;
                color: #1e293b;
                padding: 1rem;
            }}

            .overall-status,
            .indicator-card {{
                background: #f8fafc;
                border-color: #e2e8f0;
            }}

            .header h1 {{
                color: #0891b2;
            }}

            .stat-value {{
                color: #0891b2;
            }}

            .indicator-name {{
                color: #1e293b;
            }}

            .failure-item {{
                background: #fef2f2;
                color: #dc2626;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <h1>Sanity Check Report</h1>
            <div class="meta">
                Maintenance ID: <strong>{maintenance_id}</strong> |
                Generated: {generated_at}
            </div>
        </header>

        <section class="overall-status">
            <div class="status-badge">{status_text}</div>
            <div class="overall-stats">
                <div class="stat">
                    <div class="stat-value">{overall_pass_rate:.1f}%</div>
                    <div class="stat-label">Pass Rate</div>
                    <div class="progress-bar">
                        <div class="progress-fill"></div>
                    </div>
                </div>
                <div class="stat">
                    <div class="stat-value">{overall_total}</div>
                    <div class="stat-label">Total Checks</div>
                </div>
                <div class="stat">
                    <div class="stat-value" style="color: #10b981">{overall_pass}</div>
                    <div class="stat-label">Passed</div>
                </div>
                <div class="stat">
                    <div class="stat-value" style="color: #ef4444">{overall_fail}</div>
                    <div class="stat-label">Failed</div>
                </div>
            </div>
        </section>

        <section class="indicators-grid">
            {indicator_cards_html}
        </section>

        <footer class="footer">
            <p>NETORA - Sanity Check Report</p>
            <p>This report was automatically generated.</p>
        </footer>
    </div>
</body>
</html>"""

        return html

    def _generate_indicator_cards(
        self,
        indicators_summary: dict[str, Any],
        indicator_details: dict[str, Any],
        include_details: bool,
    ) -> str:
        """生成各指標的卡片 HTML。"""
        cards = []

        indicator_names = {
            "transceiver": "Transceiver",
            "version": "Version",
            "uplink": "Uplink",
            "port_channel": "Port Channel",
            "power": "Power",
            "fan": "Fan",
            "error_count": "Error Count",
            "ping": "Ping",
        }

        for indicator_type, name in indicator_names.items():
            if indicator_type not in indicators_summary:
                continue

            summary = indicators_summary[indicator_type]
            details = indicator_details.get(indicator_type, {})

            pass_rate = summary.get("pass_rate", 0)
            total = summary.get("total_count", 0)
            passed = summary.get("pass_count", 0)
            failed = summary.get("fail_count", 0)
            failures = details.get("failures", [])

            # 決定顏色 class
            # 當 total 為 0 時，視為無資料而非失敗，顯示綠色
            if total == 0 or pass_rate >= 95:
                rate_class = "rate-pass"
            elif pass_rate >= 80:
                rate_class = "rate-warning"
            else:
                rate_class = "rate-fail"

            # 生成失敗列表 HTML
            failures_html = ""
            if include_details and failures:
                failure_items = ""
                for failure in failures[:20]:  # 最多顯示 20 筆
                    if isinstance(failure, dict):
                        # 根據不同指標格式化失敗資訊
                        if "device_name" in failure:
                            failure_text = failure.get("device_name", "Unknown")
                            if "port" in failure:
                                failure_text += f" - {failure['port']}"
                            if "reason" in failure:
                                failure_text += f": {failure['reason']}"
                        else:
                            failure_text = str(failure)
                    else:
                        failure_text = str(failure)
                    failure_items += f'<div class="failure-item">{failure_text}</div>\n'

                if len(failures) > 20:
                    failure_items += f'<div class="failure-item">... and {len(failures) - 20} more</div>\n'

                failures_html = f"""
                <div class="failures-section">
                    <div class="failures-title">Failed Items ({len(failures)})</div>
                    <div class="failure-list">
                        {failure_items}
                    </div>
                </div>"""

            card = f"""
            <div class="indicator-card">
                <div class="indicator-header">
                    <span class="indicator-name">{name}</span>
                    <span class="indicator-rate {rate_class}">{pass_rate:.1f}%</span>
                </div>
                <div class="indicator-stats">
                    <span>Total: {total}</span>
                    <span style="color: #10b981">✓ {passed}</span>
                    <span style="color: #ef4444">✗ {failed}</span>
                </div>
                {failures_html}
            </div>"""
            cards.append(card)

        return "\n".join(cards)
