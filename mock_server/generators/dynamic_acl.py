"""Mock: Dynamic ACL 綁定 (get_dynamic_acl)。"""
from __future__ import annotations

import random

from mock_server.generators._probabilities import DYNAMIC_ACL_CHANGE_PROB


def generate(device_type: str, **_kw: object) -> str:
    lines = ["Interface,ACL"]
    for i in range(1, 21):
        acl_num = 3560 + i  # baseline
        # per-interface 隨機 ACL 變化
        if random.random() < DYNAMIC_ACL_CHANGE_PROB:
            acl_num = 3560 + random.randint(1, 40)
        lines.append(f"GE1/0/{i},{acl_num}")
    return "\n".join(lines)
