#!/usr/bin/env bash
# =============================================================================
# SNMP OID 驗證腳本
#
# 用途：在公司環境中，對一台真實交換機執行所有 SNMP collector 用到的 OID，
#       將結果存成報告檔，帶回來比對 collector 解析邏輯是否正確。
#
# 使用方式：
#   1. 進入 app container:
#      docker exec -it netora_app bash
#
#   2. 執行腳本（HPE 交換機）:
#      bash /app/scripts/snmp_verify.sh <community> <交換機IP> hpe
#
#   3. 執行腳本（Cisco 交換機）:
#      bash /app/scripts/snmp_verify.sh <community> <交換機IP> cisco
#
#   4. 結果會存在 /tmp/snmp_verify_<IP>_<時間>.txt
#      把這個檔案帶出來即可
#
# =============================================================================

set -euo pipefail

if [ $# -lt 3 ]; then
    echo "用法: $0 <community> <IP> <vendor: hpe|cisco>"
    echo ""
    echo "範例:"
    echo "  $0 public 10.1.1.1 hpe"
    echo "  $0 MyComm 10.2.2.2 cisco"
    exit 1
fi

COMMUNITY="$1"
IP="$2"
VENDOR=$(echo "$3" | tr '[:upper:]' '[:lower:]')
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTFILE="/tmp/snmp_verify_${IP}_${TIMESTAMP}.txt"

# snmpwalk / snmpget wrapper — 記錄指令和輸出
run_get() {
    local label="$1"
    local oid="$2"
    echo "────────────────────────────────────────" >> "$OUTFILE"
    echo "[$label]" >> "$OUTFILE"
    echo "CMD: snmpget -v2c -c *** $IP $oid" >> "$OUTFILE"
    if output=$(snmpget -v2c -c "$COMMUNITY" "$IP" "$oid" 2>&1); then
        echo "$output" >> "$OUTFILE"
    else
        echo "ERROR: $output" >> "$OUTFILE"
    fi
    echo "" >> "$OUTFILE"
}

run_walk() {
    local label="$1"
    local oid="$2"
    echo "────────────────────────────────────────" >> "$OUTFILE"
    echo "[$label]" >> "$OUTFILE"
    echo "CMD: snmpwalk -v2c -c *** $IP $oid" >> "$OUTFILE"
    if output=$(snmpwalk -v2c -c "$COMMUNITY" "$IP" "$oid" 2>&1); then
        lines=$(echo "$output" | wc -l)
        echo "$output" >> "$OUTFILE"
        echo "(共 $lines 行)" >> "$OUTFILE"
    else
        echo "ERROR: $output" >> "$OUTFILE"
    fi
    echo "" >> "$OUTFILE"
}

# ── 開始 ──
echo "=============================================" > "$OUTFILE"
echo "SNMP OID 驗證報告" >> "$OUTFILE"
echo "交換機 IP : $IP" >> "$OUTFILE"
echo "廠商類型  : $VENDOR" >> "$OUTFILE"
echo "驗證時間  : $(date '+%Y-%m-%d %H:%M:%S')" >> "$OUTFILE"
echo "=============================================" >> "$OUTFILE"
echo "" >> "$OUTFILE"

echo "正在驗證 $VENDOR 交換機 $IP ..."

# ── 1. 基礎識別 ──
echo "  [1/10] 廠商識別 + 韌體版本 ..."
run_get  "sysObjectID（廠商識別）" "1.3.6.1.2.1.1.2.0"
run_get  "sysDescr（韌體版本）"    "1.3.6.1.2.1.1.1.0"

# ── 2. ifName 對照表 ──
echo "  [2/10] ifName 對照表 ..."
run_walk "ifName（ifIndex→介面名稱）" "1.3.6.1.2.1.31.1.1.1.1"

# ── 3. 風扇 ──
echo "  [3/10] 風扇狀態 ..."
if [ "$VENDOR" = "cisco" ]; then
    run_walk "Cisco ciscoEnvMonFanState"  "1.3.6.1.4.1.9.9.13.1.4.1.3"
    run_walk "Cisco ciscoEnvMonFanDescr"  "1.3.6.1.4.1.9.9.13.1.4.1.2"
else
    run_walk "HPE hh3cEntityExtErrorStatus" "1.3.6.1.4.1.25506.2.6.1.1.1.1.19"
    run_walk "entPhysicalClass（7=fan）"    "1.3.6.1.2.1.47.1.1.1.1.5"
    run_walk "entPhysicalName"              "1.3.6.1.2.1.47.1.1.1.1.7"
fi

# ── 4. 電源 ──
echo "  [4/10] 電源狀態 ..."
if [ "$VENDOR" = "cisco" ]; then
    run_walk "Cisco ciscoEnvMonSupplyState"  "1.3.6.1.4.1.9.9.13.1.5.1.3"
    run_walk "Cisco ciscoEnvMonSupplyDescr"  "1.3.6.1.4.1.9.9.13.1.5.1.2"
else
    # HPE 電源與風扇共用 ENTITY-MIB，entPhysicalClass=6 為電源
    # errorStatus 和 entPhysicalClass 已在風扇段 walk 過，這裡不重複
    echo "  (HPE 電源共用 ENTITY-MIB，已在風扇段取得)" >> "$OUTFILE"
fi

# ── 5. 光模組 ──
echo "  [5/10] 光模組 (Transceiver DOM) ..."
if [ "$VENDOR" = "cisco" ]; then
    run_walk "Cisco entSensorValue"     "1.3.6.1.4.1.9.9.91.1.1.1.1.4"
    run_walk "Cisco entSensorType"      "1.3.6.1.4.1.9.9.91.1.1.1.1.1"
    run_walk "Cisco entSensorScale"     "1.3.6.1.4.1.9.9.91.1.1.1.1.2"
    run_walk "Cisco entSensorPrecision" "1.3.6.1.4.1.9.9.91.1.1.1.1.3"
    run_walk "entPhysicalName"          "1.3.6.1.2.1.47.1.1.1.1.7"
    run_walk "entPhysicalContainedIn"   "1.3.6.1.2.1.47.1.1.1.1.4"
else
    run_walk "HPE hh3cTransceiverTxPower"     "1.3.6.1.4.1.25506.2.70.1.1.1.1.9"
    run_walk "HPE hh3cTransceiverRxPower"     "1.3.6.1.4.1.25506.2.70.1.1.1.1.12"
    run_walk "HPE hh3cTransceiverTemperature" "1.3.6.1.4.1.25506.2.70.1.1.1.1.15"
    run_walk "HPE hh3cTransceiverVoltage"     "1.3.6.1.4.1.25506.2.70.1.1.1.1.16"
fi

# ── 6. Interface 狀態 ──
echo "  [6/10] Interface 狀態 ..."
run_walk "ifOperStatus"         "1.3.6.1.2.1.2.2.1.8"
run_walk "ifHighSpeed"          "1.3.6.1.2.1.31.1.1.1.15"
run_walk "dot3StatsDuplexStatus" "1.3.6.1.2.1.10.7.2.1.19"

# ── 7. Interface 錯誤計數 ──
echo "  [7/10] Interface 錯誤計數 ..."
run_walk "ifInErrors"  "1.3.6.1.2.1.2.2.1.14"
run_walk "ifOutErrors" "1.3.6.1.2.1.2.2.1.20"

# ── 8. MAC Table ──
echo "  [8/10] MAC Table ..."
run_walk "dot1qTpFdbPort" "1.3.6.1.2.1.17.7.1.2.2.1.2"

# ── 9. Port-Channel / LAG ──
echo "  [9/10] Port-Channel / LAG ..."
run_walk "dot3adAggPortAttachedAggID"   "1.2.840.10006.300.43.1.2.1.1.13"
run_walk "dot3adAggPortActorOperState"  "1.2.840.10006.300.43.1.2.1.1.21"
run_walk "ifOperStatus (LAG 用)"        "1.3.6.1.2.1.2.2.1.8"

# ── 10. LLDP + CDP 鄰居 ──
echo "  [10/10] LLDP / CDP 鄰居 ..."
run_walk "lldpRemSysName"  "1.0.8802.1.1.2.1.4.1.1.9"
run_walk "lldpRemPortId"   "1.0.8802.1.1.2.1.4.1.1.7"
run_walk "lldpRemPortDesc" "1.0.8802.1.1.2.1.4.1.1.8"
run_walk "lldpLocPortDesc" "1.0.8802.1.1.2.1.3.7.1.4"

if [ "$VENDOR" = "cisco" ]; then
    run_walk "Cisco cdpCacheDeviceId"   "1.3.6.1.4.1.9.9.23.1.2.1.1.6"
    run_walk "Cisco cdpCacheDevicePort" "1.3.6.1.4.1.9.9.23.1.2.1.1.7"
fi

# ── 完成 ──
echo "" >> "$OUTFILE"
echo "=============================================" >> "$OUTFILE"
echo "驗證完成" >> "$OUTFILE"
echo "=============================================" >> "$OUTFILE"

echo ""
echo "驗證完成！報告已存到："
echo "  $OUTFILE"
echo ""
echo "請將此檔案帶出公司環境，用以下指令取出："
echo "  docker cp netora_app:$OUTFILE ."
