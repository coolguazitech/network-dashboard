"""
SNMP Collection Module.

提供 SNMP 模式的資料收集，作為 REST API 模式的替代方案。
透過 .env 的 COLLECTION_MODE=snmp 啟用。

架構：
    SnmpEngine      — pysnmp async wrapper (get/walk/get_bulk)
    SnmpSessionCache — community fallback + ifIndex→ifName cache
    BaseSnmpCollector — 每個指標的 SNMP 收集器基底
    SnmpCollectionService — 與 ApiCollectionService 同介面的服務層
"""
