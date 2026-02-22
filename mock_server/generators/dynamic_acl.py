"""Mock: Dynamic ACL \u7d81\u5b9a (get_dynamic_acl)\u3002\u7121\u6536\u6582\u884c\u70ba\u3002"""
from __future__ import annotations


def generate(device_type: str, **_kw: object) -> str:
    lines = ["Interface,ACL"]
    for i in range(1, 21):
        acl_num = 3560 + i
        lines.append(f"GE1/0/{i},{acl_num}")
    return "\n".join(lines)
