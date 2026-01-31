# Polymarket 赎回功能修复报告

## 问题诊断

### 根本原因
- **旧 Relay 端点已停用**: `tx-relay.polymarket.com` DNS 解析失败
- **测试发现**: 所有 gasless relayer 端点均不可用
- **影响**: 自动赎回功能完全失效，需要手动赎回

### 测试结果
```
Relayer 端点状态:
❌ https://relayer.polymarket.com/relay - DNS 解析失败
❌ https://gasless.polymarket.com/relay - DNS 解析失败  
⚠️  https://api.polymarket.com/relay - 404 (存在但无服务)
❌ https://tx-relay.polymarket.com/relay - DNS 解析失败 (原端点)
```

## 修复方案

### 1. 多端点重试机制
- 尝试多个 relayer 端点
- 自动降级到直接合约交互
- 最后通知手动赎回

### 2. 直接合约交互 (Fallback)
当 relayer 不可用时，使用 Web3 直接与 CTF Exchange 合约交互：
- **合约地址**: `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E`
- **方法**: `redeemPositions`
- **要求**: 需要 MATIC 支付 gas (约 0.001-0.01 MATIC/次)

### 3. 手动赎回通知
当所有自动化方法失败时，通过 Telegram 通知用户手动赎回链接。

## 代码变更

### 修改文件: `btc_15m_bot_v3.py`

#### 变更 1: 扩展 `_raw_redeem` 方法
- 添加多 relayer 端点重试
- 添加 `_redeem_direct` 直接合约交互方法
- 改进错误处理和日志

#### 变更 2: 更新 `settle_positions` 方法
- 添加失败通知
- 提供手动赎回链接

### 新增文件

#### `redeem_fixed.py`
独立的赎回管理模块，提供：
- `RedeemManager` 类
- 多方式赎回（gasless → direct → manual）
- 备用 RPC 端点

#### `test_redeem_fix.py`
测试脚本，验证：
- RPC 连接
- Relayer 端点可用性
- 合约验证
- 赎回流程

#### `REDEEM_FIX_PATCH.md`
详细的补丁说明文档

## 使用建议

### 短期方案 (立即生效)
修复后的代码会自动：
1. 尝试所有可用的 relayer 端点
2. 失败时尝试直接合约交互
3. 仍失败则通知手动赎回

### 中期方案 (推荐)
**为钱包充值 MATIC**:
- 目标余额: 0.5-1 MATIC
- 用途: 直接合约交互 gas 费
- 预估消耗: 每次赎回约 0.001-0.01 MATIC

充值地址（签名钱包）:
```
0xB18Ec6606d4d7b87e9F4a5e0D1d36E41854E7A
```

### 长期方案
1. 监控 Polymarket 官方更新
2. 如推出新 relayer 服务，可更新 `RELAYER_URL`
3. 考虑使用第三方 relayer 服务

## 验证步骤

### 1. 运行测试脚本
```bash
cd /home/ubuntu/clawd/polymarket-bot
source venv/bin/activate
python3 test_redeem_fix.py
```

### 2. 检查测试结果
- ✅ RPC 连接正常
- ❌ Relayer 端点不可用 (预期)
- ✅ 合约验证通过
- ⚠️  需要 MATIC 余额

### 3. 监控日志
重启 bot 后观察日志：
- `启动自动赎回流程...` - 赎回开始
- `尝试 Relayer: ...` - 尝试各端点
- `所有 Relayer 端点失败，尝试直接赎回...` - 降级
- `直接赎回交易已发送: ...` - 直接交互
- `赎回成功` 或 `请手动赎回` - 最终结果

## 手动赎回指南

当自动赎回失败时：

1. **访问 Polymarket**: https://polymarket.com/portfolio
2. **找到已结算市场**
3. **点击 Redeem 按钮**
4. **确认交易** (需要 MATIC gas)

或直接访问市场链接：
```
https://polymarket.com/market/{condition_id}
```

## 技术细节

### CTF Exchange 合约
```solidity
function redeemPositions(
    address collateralToken,    // USDC: 0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174
    bytes32 parentCollectionId, // 0x0000000000000000000000000000000000000000000000000000000000000000
    bytes32 conditionId,        // 市场条件 ID
    uint256[] indexSets         // [1, 2] (Yes 和 No)
) external
```

### 调用数据构造
```python
func_selector = bytes.fromhex("8679b734")  // redeemPositions
data = func_selector + encode(
    ['address', 'bytes32', 'bytes32', 'uint256[]'],
    [USDC_ADDRESS, parent_id, condition_id, [1, 2]]
)
```

## 风险与注意事项

1. **Gas 费用**: 直接交互需要 MATIC，确保钱包有余额
2. **交易失败**: 可能因网络拥堵或合约问题失败
3. **资金安全**: 合约交互使用标准 CTF Exchange，资金安全

## 后续跟进

- [ ] 监控 relayer 服务恢复情况
- [ ] 充值 MATIC 到签名钱包
- [ ] 测试实际赎回流程
- [ ] 考虑实现批量赎回功能

---

**修复完成时间**: 2026-01-31
**修复版本**: btc_15m_bot_v3.py ( patched )
**测试状态**: ✅ 代码测试通过，等待实际赎回验证
