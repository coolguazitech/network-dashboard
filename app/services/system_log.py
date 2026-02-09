"""
System Log Service.

提供統一的日誌寫入介面，將錯誤和重要事件寫入 DB。
使用獨立 session，確保即使主請求 rollback 也能寫入。
"""
from __future__ import annotations

import logging
import re
import traceback as tb_module

from app.db.base import get_session_context
from app.db.models import SystemLog

logger = logging.getLogger(__name__)


def format_error_detail(
    exc: BaseException | None = None,
    tb_text: str | None = None,
    context: dict[str, str] | None = None,
) -> str:
    """
    格式化錯誤詳情，方便在系統日誌頁面快速定位問題。

    Args:
        exc: 例外物件（優先使用）
        tb_text: 完整 traceback 文字（若無 exc 時使用）
        context: 業務上下文（如設備名、歲修 ID 等）

    Returns:
        格式化後的 detail 字串
    """
    lines: list[str] = []

    # --- 錯誤定位 ---
    exc_type = ""
    exc_msg = ""
    exc_location = ""

    if exc is not None:
        exc_type = type(exc).__name__
        exc_msg = str(exc)
        # 取得完整 traceback
        if tb_text is None:
            tb_text = tb_module.format_exc()
            # 如果 format_exc() 回傳 "NoneType: None"，改用 exception info
            if tb_text.strip() == "NoneType: None":
                tb_text = "".join(tb_module.format_exception(exc))
    elif tb_text:
        # 從 traceback 文字提取類型和訊息
        last_line = tb_text.strip().rsplit("\n", 1)[-1]
        if ":" in last_line:
            exc_type, _, exc_msg = last_line.partition(":")
            exc_type = exc_type.strip()
            exc_msg = exc_msg.strip()
        else:
            exc_type = last_line.strip()

    # 從 traceback 提取最後一個 frame 的位置
    if tb_text:
        # 找所有 File "..." 行，取最後一個
        frames = re.findall(
            r'File "([^"]+)", line (\d+), in (\w+)',
            tb_text,
        )
        if frames:
            filepath, lineno, funcname = frames[-1]
            # 簡化路徑：移除 /workspace/ 前綴
            filepath = re.sub(r"^/workspace/", "", filepath)
            exc_location = f"{filepath}:{lineno} ({funcname})"

    lines.append("┌ 錯誤定位")
    if exc_type:
        lines.append(f"│ 類型: {exc_type}")
    if exc_msg:
        # 截斷過長的訊息
        msg_display = exc_msg[:300] + "..." if len(exc_msg) > 300 else exc_msg
        lines.append(f"│ 訊息: {msg_display}")
    if exc_location:
        lines.append(f"│ 位置: {exc_location}")

    # --- 上下文 ---
    if context:
        lines.append("│")
        lines.append("│ 上下文:")
        for key, value in context.items():
            if value:
                lines.append(f"│   {key}: {value}")

    # --- 完整 Traceback ---
    if tb_text and tb_text.strip() != "NoneType: None":
        lines.append("│")
        lines.append("└ 完整 Traceback")
        for tb_line in tb_text.strip().split("\n"):
            lines.append(f"  {tb_line}")
    else:
        lines.append("└")

    return "\n".join(lines)


async def write_log(
    *,
    level: str,
    source: str,
    summary: str,
    detail: str | None = None,
    module: str | None = None,
    user_id: int | None = None,
    username: str | None = None,
    maintenance_id: str | None = None,
    request_path: str | None = None,
    request_method: str | None = None,
    status_code: int | None = None,
    ip_address: str | None = None,
) -> None:
    """
    寫入一筆系統日誌到 DB。

    Args:
        level: 日誌等級 (ERROR / WARNING / INFO)
        source: 來源 (api / scheduler / frontend / service)
        summary: 中文摘要（用戶看的）
        detail: 技術細節 / traceback
        module: 模組名稱
        user_id: 觸發的用戶 ID
        username: 觸發的用戶名
        maintenance_id: 歲修 ID
        request_path: API 路徑
        request_method: HTTP method
        status_code: HTTP status code
        ip_address: 客戶端 IP
    """
    try:
        async with get_session_context() as session:
            log_entry = SystemLog(
                level=level.upper(),
                source=source,
                module=module,
                summary=summary[:500] if summary else "",
                detail=detail,
                user_id=user_id,
                username=username,
                maintenance_id=maintenance_id,
                request_path=request_path,
                request_method=request_method,
                status_code=status_code,
                ip_address=ip_address,
            )
            session.add(log_entry)
            await session.commit()
    except Exception as e:
        # 日誌寫入本身失敗時只記錄到 stdout，不能再拋異常
        logger.error("Failed to write system log: %s", e)
