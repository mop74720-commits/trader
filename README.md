# Trader Lab

基于本目录 GenericAgent × AI Trader 调研资料的**架构复现**。可本地运行、持久化、审计的模拟交易实验台，包含中文看板、规则认知、可选模型接口、策略信号、独立风控巡检、模拟撮合与候选因子研究。

不是原项目源码，也未集成 GenericAgent runtime。原项目私有公式、Prompt、交易所执行细节没有公开，本仓库使用明确的独立实现。初版聚焦验证完整闭环。

## 启动

Python 3.11+，无第三方运行依赖。在项目目录执行：

```powershell
python run.py
```

打开 http://127.0.0.1:8765 。首次启动创建 `data/trader.sqlite3`，以 10,000 USDC 模拟资金回放 48 根合成 K 线，产生真实计算的净值、订单、决策与研究结果，然后暂停。页面按钮可以启动、暂停、推进一小时、运行研究、查看输入快照、导出全部成交。

- 自动模式默认每 3 秒生成一根模拟 15 分钟 K 线；每 4 根运行一次认知，每 672 根运行一次研究。
- 暂停会冻结模拟行情；此时不再产生价格风险。真实行情下不能采用这种暂停语义。
- 停止并清仓会锁定该账户。新实验使用新数据库路径，不覆盖旧记录。
- 重启恢复现金、仓位与日志，自动保持暂停，旧快照标为过期；推进后生成新快照。
- 默认规则引擎，**没有模型请求、真实行情请求或交易所订单**。默认启用独立公共情报采集（Fed RSS、CoinDesk RSS、Telegram 公共频道、Polymarket）；加 `--no-intelligence` 可完全关闭情报联网。

```powershell
python run.py --port 8766 --db data/experiment-02.sqlite3 --no-demo
python -m unittest discover -s tests -v
```

## 实现边界

| 模块 | 当前实现 |
| --- | --- |
| Market Data | 固定随机种子的合成 OHLCV、合成 funding；BTC / ETH / SOL |
| Intelligence | 独立公共采集、证据版本、去重聚合、时效/来源评估、摘录式摘要；RSS / Telegram 公共频道 / Polymarket 已接入；X 与自有 JSONL 可配置 |
| Planner | 规则策略：趋势效率 + 短期动量，或 VWAP 均值回归；可选模型 JSON 提议 |
| Critic | 独立接口，默认高波动规则审查；可选模型审查；拥有 veto 权 |
| Risk | 波动率仓位、止损、总敞口、回撤阶梯、快照过期、价格偏离限制 |
| Execution | 本地多头现货模拟，现金约束、全额撮合、双边费用与滑点 |
| Researcher | 统计研究器，选择动量窗口，隔离标签的训练/验证，Trial / Rejected |
| Persistence | SQLite 原子保存账户状态与追加审计，同一快照认知去重 |
| UI | 净值、仓位、市场、决策快照、研究结果、运行状态、CSV 导出 |

原站当前描述 Critic 提示风险、Planner 最终决定；本复现选择资料早期的 veto 模式。研究器不是自主写代码的 LLM agent，因子不会自动参与交易。没有空头、杠杆、真实交易所、订单簿、部分成交、实盘对账或模型 token 成本统计。

## 数据与控制流程

```text
合成 OHLCV → 因子 / Snapshot → Planner → Critic
                                  ↓ 审查通过
                       确定性 Risk → Paper Exchange → SQLite

每根新 K 线 → 独立风控巡检 → 止损 / 回撤熔断
历史 K 线 → 统计 Researcher → 训练 / 留出验证 → Trial 或 Rejected
```

行情/风控线程与认知线程独立。模型慢响应时行情与止损仍推进；执行时重新检查价格、快照年龄、当前现金与账户熔断状态。模型异常或合同校验失败会记为 veto，本轮不执行订单，不静默切换规则下单。

## 信息来源与消息官子系统

看板「情报中心」展示来源健康、当前摘要、历史回放、证据详情和事件通知。来源配置位于 `config/intelligence.sources.json`，独立数据库为 `data/intelligence.sqlite3`。**不修改已有交易数据库结构**。完整设计、字段和复现边界见 [docs/intelligence.md](docs/intelligence.md)。

```powershell
# 只启动消息官，不运行交易服务（默认每 5 秒检查各来源是否到期）
python -m trader.intelligence

# 对到期来源采集一轮并退出；遵守原有轮询间隔和失败退避
python -m trader.intelligence --once

# 不联网，查看当前摘要或按采集截止时间回放
python -m trader.intelligence --digest
python -m trader.intelligence --digest --as-of "2026-09-09T13:00:00Z"

# 使用其他配置与新情报数据库
python run.py --intel-config config/intelligence.sources.json --intel-db data/intelligence-research.sqlite3
```

交易服务已内嵌独立采集线程，不要同时对同一情报数据库运行独立采集进程。暂停模拟交易不暂停公共信息采集。X 源默认关闭；开启需要配置 `enabled: true`、提供环境变量 `TRADER_X_BEARER_TOKEN`，并显式传 `--enable-x-api`（可能计费，未执行在线调用）。

模型模式的 Planner 和 Critic 接收同一份情报摘要，连同原始证据 ID、出处、时间和来源健康保存到每轮决策快照。截止时间为 `min(模拟时间, 当前墙钟时间)`，晚于该时点才采集的新闻不会进入输入。规则 Planner 不使用文本产生买卖信号；合成行情与真实新闻组合仅用于接口实验，不构成有效历史回测。

## 风控和账本口径

- 多头现货模拟；单资产开仓名义预算不超过净值 20%，总敞口开仓预算不超过 60%。行情漂移后不主动再平衡，因此持仓比例可能越过开仓比例。
- 止损距离 = `clip(1.5 × 日波动率, 2%, 8%)`；单笔计划止损风险预算为净值的 0.5%，再乘 Planner 风险倾向及回撤缩放。
- 回撤从历史净值高点计算；达到 3% / 5% 时风险缩放为 50% / 25%，达到 8% 清仓并锁定新开仓。
- 快照墙钟年龄超过 30 秒或当前价偏离快照超过 1%，禁止新开仓；允许减仓。
- 每次成交收取 6 bps 手续费和 5 bps 不利滑点；开仓和止损同时写入本地状态。
- 多头止损以该 K 线 `low <= stop` 触发；跳空低开按 `min(open, stop)` 再扣滑点成交。止损不保证最大实际亏损，跳空和交易费用可能放大损失。
- 同一快照 tick 只允许一次认知轮；成交和账户状态在同一个 SQLite 事务内保存。这个机制适用于本地模拟账本，不声称提供真实交易所 exactly-once 执行。
- 净值 = 现金 + 持仓按最新模拟收盘价估值。累计收益已含已发生手续费和滑点，未扣尚未平仓的未来退出费用。模型费用不包含在净值中。
- 看板保留最近 100 轮认知、300 笔成交、600 个净值点；SQLite audit 追加保留所有事件，CSV 从完整审计记录导出。请勿同时启动多个进程写同一个数据库。

## 研究口径

只用 BTC 历史合成数据，在前 70% 数据上选择 8 / 16 / 32 根动量窗口；训练标签到验证边界之间隔离 4 根 K 线。IC 和 rank-IC 为信号与未来 4 根收益的时序相关性。验证指标不参与窗口选择。

扣费平均收益使用每 4 根一次的不重叠多头信号交易，计入双边费用和滑点。至少 32 个验证信号、8 笔交易、IC 与 rank-IC 均超过 0.03 且平均净收益为正才进入 Trial，否则 Rejected。Trial 永远没有资金权限。

这些阈值用于演示研究治理流程。反复运行相邻窗口不构成独立检验；未实现显著性检验、多重检验修正、滚动 walk-forward、真实数据样本外回测。合成行情上的收益不能证明真实市场有效性。

## 可选模型模式

默认不启用。用户自行配置当前进程环境变量后，以 `--llm` 显式启用 OpenAI-compatible Chat Completions 接口；该操作会向所配置服务发送模拟市场/账户快照，并可能产生提供商费用。

| 环境变量 | 含义 |
| --- | --- |
| `TRADER_LLM_BASE_URL` | 含 API 版本的接口根路径，例如服务提供商的 `/v1` 地址 |
| `TRADER_LLM_API_KEY` | 仅从环境读取，不写入数据库或日志 |
| `TRADER_PLANNER_MODEL` | Planner 模型标识 |
| `TRADER_CRITIC_MODEL` | Critic 模型标识，缺省同 Planner |

```powershell
python run.py --llm --db data/model-experiment.sqlite3 --no-demo
```

远程接口要求 HTTPS（本机 localhost / 127.0.0.1 可用 HTTP）。需要支持 `response_format: json_object`。服务不自动降级接口参数；不兼容、超时或 JSON 无效时该轮停止。没有调用真实提供商验证，模型费用需查看提供商账单。

## 文件入口

- `trader/market.py`：合成行情、因子计算。
- `trader/cognition.py`：规则 / 模型 Planner 与 Critic、严格提议校验。
- `trader/engine.py`：风控、撮合、持久化、审计。
- `trader/research.py`：候选因子研究与留出评估。
- `trader/server.py`：仅绑定 127.0.0.1 的服务与后台调度。
- `trader/web/`：无构建步骤的中文看板。
- `tests/`：账本、止损跳空、熔断、去重、隔离、合同与 HTTP 回归测试。

## 原始参考

- [GenericAgent](https://github.com/lsdefine/GenericAgent)
- [Trader 公开运行站点](https://trader.gaagent.ai/)
- 本目录 `GenericAgent_Trader_项目概况.md`、`GenericAgent_Trader_原始链接汇总.md`
