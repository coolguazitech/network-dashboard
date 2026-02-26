"""Mock: Static ACL 綁定 (get_static_acl)。"""
from __future__ import annotations

import random

from mock_server.generators._probabilities import (
    STATIC_ACL_ALTERNATIVES,
    STATIC_ACL_CHANGE_PROB,
)

_BASELINE_ACL = 3001


def generate(device_type: str, **_kw: object) -> str:
    lines = ["Interface,ACL"]
    for i in range(1, 21):
        acl = _BASELINE_ACL
        # per-interface 隨機 ACL 變化
        if random.random() < STATIC_ACL_CHANGE_PROB:
            acl = random.choice(STATIC_ACL_ALTERNATIVES)
        lines.append(f"GE1/0/{i},{acl}")
    return "\n".join(lines)
