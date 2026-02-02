# Polymarket Bot API 问题分析与解决方案

## 1. 订单提交失败 (无 order_id)

**问题现象:**
- API 返回 HTTP 200 OK
- 但响应中无 `order_id` 字段
- 报错: "订单提交失败: 无订单ID返回"

**根本原因:**
- 余额/授权不足 (`not enough balance / allowance`)
- 或 API 响应格式异常

**解决方案:**
```python
# 已添加调试日志，打印完整响应
logger.info(f"[DEBUG] 订单响应: {order_result}")
```

**状态:** ✅ 已添加调试代码

---

## 2. Relayer V2 赎回 401 错误

**问题现象:**
- 端点 `/submit` 返回 401 Unauthorized
- 签名算法不匹配

**已尝试方案:**
- ✅ 毫秒时间戳 (13位)
- ✅ Secret base64 解码 (1个padding)
- ✅ 紧凑 JSON (无空格)
- ✅ 路径 `/submit` (无 `/v1`)
- ✅ 签名 message 格式: `timestamp + method + path + body`
- ❌ 仍返回 401

**可能原因:**
1. **Passphrase 需要 hex 解码** (64位hex → 32字节)
2. **Header 名称大小写** (可能服务器只认小写)
3. **API Key 权限不足** (需要特定权限才能使用 relayer)
4. **服务端点已变更** (可能已迁移到新域名)

**待测试方案:**
```python
# 1. Passphrase hex 解码
import binascii
passphrase = binascii.unhexlify(passphrase_hex).decode('utf-8', errors='ignore')

# 2. 小写 headers
headers = {
    'poly-builder-api-key': api_key,
    'poly-builder-timestamp': timestamp,
    'poly-builder-passphrase': passphrase,
    'poly-builder-signature': signature
}

# 3. 尝试其他端点
endpoints = [
    'https://relayer-v2.polymarket.com/submit',
    'https://relayer.polymarket.com/submit',
    'https://gasless.polymarket.com/submit'
]
```

**状态:** 🔄 需要进一步调试

**替代方案:**
- ✅ 手动赎回: https://polymarket.com/portfolio
- ✅ 直接合约赎回 (需 MATIC gas)

---

## 3. API 请求超时

**问题现象:**
- `httpx.ReadTimeout: The read operation timed out`
- 测试脚本连接超时

**可能原因:**
- 网络延迟
- 服务端负载高
- 请求参数错误导致服务端长时间处理

**解决方案:**
```python
# 增加超时时间
resp = requests.post(url, json=body, headers=headers, timeout=60)

# 或使用重试机制
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

session = requests.Session()
retries = Retry(total=3, backoff_factor=1)
session.mount('https://', HTTPAdapter(max_retries=retries))
```

**状态:** ⏸️ 暂时性网络问题

---

## 4. WebSocket 连接不稳定

**问题现象:**
- `Pong timeout detected`
- `Connection closed unexpectedly`
- 自动重连

**当前处理:**
- ✅ 已实现自动重连机制
- ✅ 价格缓存 (5秒内使用缓存价格)
- ✅ 指数退避重试

**状态:** ✅ 已处理，可自愈

---

## 5. 持仓追踪逻辑错误 (已修复)

**问题现象:**
- 下单成功但持仓记录无 `order_id`
- `_track_order` 无法追踪

**根本原因:**
- 代码逻辑顺序错误: 先更新 `position["order_id"]` 再创建 `position` 对象

**修复方案:**
```python
# 正确顺序:
1. 下单成功，获取 order_id
2. 创建 position 对象（包含 order_id，status="PENDING"）
3. 保存持仓
4. 启动 _track_order 追踪
```

**状态:** ✅ 已修复并推送

---

## 优先级建议

| 问题 | 优先级 | 状态 |
|------|--------|------|
| 持仓追踪逻辑 | P0 | ✅ 已修复 |
| 订单提交调试 | P1 | 🔄 等待下次运行 |
| Relayer 401 | P2 | ⏸️ 可手动赎回替代 |
| API 超时 | P3 | ⏸️ 暂时性问题 |
| WebSocket | P4 | ✅ 已自愈 |

---

*生成时间: 2026-02-02 01:00 UTC*
