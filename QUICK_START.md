# Network Dashboard 快速开始

本指南帮助您快速启动并测试 Network Dashboard 项目。

---

## 📋 前置要求

- Python 3.11+ (已安装 venv)
- MariaDB/MySQL (已运行)
- Node.js 16+ (用于前端)

---

## 🚀 快速启动 (3 步)

### Step 1: 启动 Mock API Server

```bash
# 在终端 1
./scripts/run_mock_server.sh
```

等待看到:
```
INFO:     Uvicorn running on http://0.0.0.0:8001
```

### Step 2: 初始化数据库和填充数据

```bash
# 在终端 2
source venv/bin/activate

# 初始化数据库和创建测试交换机
python scripts/init_test_db.py

# 填充测试数据
export EXTERNAL_API_SERVER="http://localhost:8001"
python scripts/seed_test_data.py --scenario 01_baseline --maintenance-id TEST-100
```

预期输出:
```
✅ Scenario seeding complete!
Collections: 13/16
Ping indicator: 1/1 passed (100%)
```

### Step 3: 启动后端并访问 API

```bash
# 在终端 2 或新终端
uvicorn app.main:app --reload --port 8000
```

测试 API:
```bash
# 获取指标摘要
curl http://localhost:8000/api/v1/dashboard/maintenance/TEST-100/summary

# 获取 ping 指标详情
curl http://localhost:8000/api/v1/indicators/ping
```

---

## 🎯 验证系统工作

### 1. 检查 Mock Server
```bash
curl http://localhost:8001/
curl http://localhost:8001/admin/devices
```

### 2. 检查数据收集
```bash
# 列出已注册的 parsers
python scripts/list_parsers.py

# 应该显示 18 个 parsers
```

### 3. 测试不同场景
```bash
# 光模块故障场景
python scripts/seed_test_data.py --scenario 02_transceiver_failure --maintenance-id TEST-FAIL-TRX

# 风扇故障场景
python scripts/seed_test_data.py --scenario 05_fan_failure --maintenance-id TEST-FAIL-FAN

# Uplink 断开场景
python scripts/seed_test_data.py --scenario 03_uplink_down --maintenance-id TEST-FAIL-UPLINK
```

---

## 📊 访问 Dashboard (可选)

```bash
# 终端 3
cd frontend
npm install  # 首次运行
npm run dev
```

访问: http://localhost:5173

---

## 🔍 常用命令

### 数据管理

```bash
# 重新填充数据
python scripts/seed_test_data.py --scenario 01_baseline --maintenance-id NEW-ID

# 填充所有场景
python scripts/seed_test_data.py --all
```

### Mock Server 管理

```bash
# 加载不同场景
curl -X POST http://localhost:8001/admin/load_scenario/02_transceiver_failure

# 重置为基线
curl -X POST http://localhost:8001/admin/reset

# 注入故障
curl -X POST http://localhost:8001/admin/inject_failure \
  -H "Content-Type: application/json" \
  -d '{"scenario": "fan_failure", "target_devices": ["switch-new-01"]}'
```

### 调试

```bash
# 检查数据库中的交换机
python scripts/check_db_values.py

# 调试 parser 查找
python scripts/debug_parser_lookup.py
```

---

## 📁 项目结构速览

```
network_dashboard/
├── app/
│   ├── parsers/
│   │   ├── plugins/         # 18 个 parser 插件
│   │   ├── protocols.py     # Parser 协议定义
│   │   └── registry.py      # Parser 注册表
│   ├── indicators/          # 8 个指标评估器
│   ├── services/
│   │   ├── data_collection.py
│   │   └── indicator_service.py
│   └── db/models.py         # 24 个数据库模型
├── tests/
│   ├── mock_api_server.py   # Mock API Server
│   ├── scenarios/           # 8 个测试场景
│   └── README.md
├── scripts/
│   ├── init_test_db.py
│   ├── seed_test_data.py
│   ├── run_mock_server.sh
│   └── list_parsers.py
└── E2E_TEST_REPORT.md       # 测试报告
```

---

## ✅ 当前系统状态

### 已实现 (Phase 1-3)
- ✅ 8 个指标评估器 (transceiver, uplink, ping, port_channel, power, fan, error_count, version)
- ✅ 18 个 parsers (Cisco NXOS, IOS; HPE Comware; Aruba)
- ✅ Mock API Server (8 个场景)
- ✅ 数据收集服务
- ✅ 指标评估服务
- ✅ Dashboard 后端 API
- ✅ 数据库模型 (24 张表)

### 测试验证结果
- **数据收集成功率**: 81.25% (13/16)
- **Ping 指标通过率**: 100% ✅
- **已注册 Parsers**: 18 个
- **Mock Server 场景**: 8 个

### 已知小问题
1. 缺少 version parsers (3个) - 低优先级
2. Uplink 需要配置 expectations - 预期行为
3. HPE ping parser 缺失 - 低优先级

---

## 🎯 下一步

### 如果想要完整功能
1. **Phase 4**: 实现 OLD vs NEW 对比功能
2. **Phase 5**: 数据库优化
3. 添加缺失的 3 个 version parsers

### 如果只是演示/测试
👉 **当前版本已经可用！**
- 启动 Mock Server
- 填充测试数据
- 启动后端 API
- 访问前端 Dashboard

---

## 📞 获取帮助

- **测试指南**: 查看 `tests/README.md`
- **测试报告**: 查看 `E2E_TEST_REPORT.md`
- **实施计划**: 查看 `~/.claude/plans/delegated-toasting-pretzel.md`

---

## 🐛 故障排查

### Mock Server 无法启动
```bash
# 检查端口占用
lsof -i :8001
# 如果被占用，kill 掉进程
kill -9 <PID>
```

### 数据收集失败
```bash
# 1. 确认 Mock Server 运行
curl http://localhost:8001/

# 2. 确认环境变量
echo $EXTERNAL_API_SERVER  # 应该是 http://localhost:8001

# 3. 检查 parsers 注册
python scripts/list_parsers.py
```

### API 返回 500 错误
```bash
# 检查数据库连接
# 查看后端日志找到具体错误
```

---

**最后更新**: 2026-01-25
**项目状态**: ✅ 核心功能可用，适合演示和测试
