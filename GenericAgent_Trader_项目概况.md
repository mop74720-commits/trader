# GenericAgent × AI Trader 项目概况

## 1. 项目定位

这个项目可以准确地概括为：

> **以 GenericAgent 为自主智能体底座，构建的一套面向加密资产真实资金交易的 AI-native autonomous systematic trading system。**

它不是“一个 LLM 看行情然后直接下单”的交易机器人，也不是普通的多 Agent 聊天系统。它把整个交易系统拆分为多个职责明确的层：

- 外部信息采集与情报整理
- 结构化市场数据与市场快照
- Planner 市场认知
- Critic 独立治理
- Strategy / Factor 信号
- 确定性 Risk Engine
- 交易执行
- Researcher 慢速研究与因子进化
- 全链路 Observability

其核心思想可以概括为：

```text
LLM = cognition / research / governance
Code = risk / execution / hard constraints
```

即：

```text
LLM 负责：
- 理解市场
- 判断 regime
- 形成交易观点
- 调整风险倾向
- 研究新因子
- 审查其他 Agent 的提议

确定性程序负责：
- 仓位
- 杠杆限制
- 止损
- 回撤控制
- 数据新鲜度
- 风险权限
- 订单执行
- 状态对账
```

所以整个系统不是：

```text
LLM → Exchange
```

而更接近：

```text
LLM Intent
    ↓
Governance / Policy
    ↓
Deterministic Risk
    ↓
Execution
    ↓
Exchange
```

---

## 2. GenericAgent：整个项目的底座

公开底座是：

```text
lsdefine/GenericAgent
```

GenericAgent 对自身的定位是：

> **A Minimal, Self-Evolving Autonomous Agent Framework**

其公开 README 中强调：

- 约 3K 行 seed code
- 9 个 atomic tools
- 约 100 行 Agent Loop
- 强调最小框架
- 强调自主探索
- 强调 Skill / SOP 自进化
- 强调真实浏览器、代码执行、文件系统、终端等系统级操作能力

GenericAgent 本身不是交易系统。

更准确的关系是：

```text
GenericAgent
=
Agent Runtime
+
Tool Calling
+
Browser / Code / Files
+
Memory
+
Skill / SOP
+
Reflect
+
Scheduler
+
Autonomous Execution
```

而 Trader 是建立在这套 Runtime 之上的交易领域系统。

---

## 3. GenericAgent 的 Agent Loop

公开源码 `agent_loop.py` 的核心逻辑可以概括为：

```text
Task
 ↓
LLM
 ↓
Tool Call
 ↓
Handler Dispatch
 ↓
Tool Result
 ↓
Next Prompt
 ↓
LLM
 ↓
...
 ↓
Task Done
```

也就是说，GenericAgent 的本质不是预制工作流引擎，而是一个通用的：

```text
LLM → Tool → Environment → Result → LLM
```

循环。

这使它可以在遇到新任务时：

```text
探索方法
↓
安装依赖
↓
写脚本
↓
调试
↓
验证
↓
沉淀执行经验
```

---

## 4. GenericAgent 的 9 个原子工具

公开 README 中的 9 个工具包括：

```text
code_run
file_read
file_write
file_patch
web_scan
web_execute_js
ask_user
update_working_checkpoint
start_long_term_update
```

对这个 Trader 项目来说，最关键的是：

```text
code_run
web_scan
web_execute_js
file_read / file_write
start_long_term_update
```

这些能力使 GenericAgent 可以自己建立：

- 信息抓取能力
- 浏览器登录态能力
- 外部 API 调用能力
- 数据处理脚本
- 定时工作流
- SOP / Skill

---

## 5. GenericAgent 的 Memory / Self-Evolution

GenericAgent 当前公开的 Memory 分层为：

```text
L0 Meta Rules
L1 Insight Index
L2 Global Facts
L3 Task Skills / SOPs
L4 Session Archive
```

可以理解为：

### L0 — Meta Rules

最高层行为约束与核心规则。

### L1 — Insight Index

压缩后的经验索引，用于快速定位已有能力。

### L2 — Global Facts

长期稳定事实与知识。

### L3 — Task Skills / SOPs

已经验证过、可复用的任务工作流。

### L4 — Session Archive

过去 Session 的归档，用于长周期记忆。

GenericAgent 所谓“自进化”不是训练模型参数，而是：

```text
New Task
 ↓
Autonomous Exploration
 ↓
Successful Execution
 ↓
Crystallize into Skill / SOP
 ↓
Reuse next time
```

这与“天才消息官”非常重要，因为消息官很可能不是一个固定的官方模块，而是某个 GenericAgent 实例在长期运行中形成的一组：

```text
Memory
Skill
SOP
Collector Script
Source Configuration
```

---

## 6. Reflect：持续自主运行机制

2026 年 4 月最早的“天才消息官 + 天才交易员”帖子里，作者明确强调：

```text
GA 的反射模式
```

GenericAgent 当前公开源码中的 Reflect 本质上是一个周期性或条件性检查器。

例如：

```python
INTERVAL = ...
ONCE = False

def check():
    ...
```

`check()` 返回任务 Prompt 时，就唤醒 Agent；返回空则继续等待。

因此 Reflect 可以表达：

```text
条件不满足
→ 不唤醒

条件满足
→ 唤醒 Agent
```

这使 GA 具备持续自主工作的基础。

---

## 7. Scheduler

GenericAgent 当前公开仓库存在：

```text
reflect/scheduler.py
```

支持：

```text
once
daily
weekday
weekly
monthly
every_Nh
every_Nm
every_Nd
```

它会读取任务配置，检查：

- enabled
- schedule
- cooldown
- max delay

条件满足时唤醒 Agent。

所以 GenericAgent 自身已经具备：

```text
Scheduled Work
+
Autonomous Agent
```

能力。

---

## 8. Event-driven Reflect

公开仓库中的：

```text
reflect/agent_team_worker.py
```

已经展示了一种事件式 Reflect：

```text
先检查外部来源
↓
没有新内容
→ None
→ 不唤醒

有新内容
→ 返回 Prompt
→ Agent 开始执行
```

这与后期 Trader 决策页面出现的：

```text
认知轮
事件轮
```

能够对应起来。

---

# 9. 项目的最早形态：天才消息官 + 天才交易员

目前最关键的历史资料之一，是 Linux.DO 的：

```text
topic/2029982
```

标题为：

> GenericAgent 实战 | 天才消息官 + 天才交易员

发布时间：

```text
2026-04-22
```

正文明确出现：

```text
关于 TG + X 信息渠道的采集

天才消息官上线
```

然后进入：

```text
关于天才交易员

直接来个多模型一起协商

Claude Opus 作为主脑
```

因此最初可以确认的架构是：

```text
Telegram
    │
X
    │
    ▼
天才消息官
    │
    ▼
整理后的情报
    │
    ▼
天才交易员
    │
    ▼
多模型协商
```

帖子还明确提到：

```text
GA 群的一位佬补上了最后一块拼图
```

说明早期信息链路至少有一部分能力来自 GA 社区成员的补充。

---

# 10. 天才消息官

“天才消息官”是独立的 Intelligence Collector / Information Agent。

它不是 Planner 临时去浏览网页。

早期公开确认的信息源是：

```text
Telegram
X
```

后续系统进一步扩展到：

```text
Telegram
X
Polymarket
其他作者自己整合的渠道
```

作者后续明确描述其架构为：

```text
一个信息收集 Agent
先把信息搜集好
再交给交易员
```

因此真实逻辑更接近：

```text
TG / X / Polymarket / Other
          │
          ▼
Information Collector Agent
          │
          ▼
Collect / Filter / Organize
          │
          ▼
Intelligence Digest / Event
          │
          ▼
Trader
```

目前没有找到“天才消息官”独立公开仓库或完整源码。

因此它更可能是：

```text
某个 GenericAgent 实例
+
私有 Memory
+
私有 Skill / SOP
+
私有采集脚本
+
私有信息源列表
```

---

# 11. 成熟 Trader

后期系统已经明显超越 4 月早期的“消息官 + 多模型交易员”。

成熟版至少明确存在三个核心角色：

```text
Planner
Critic
Researcher
```

用户提供的成熟版本截图显示当时模型配置为：

```text
Planner     GPT-5.6 Sol
Critic      Grok-4.6
Researcher  Kimi-K3
```

三个角色不是平行投票，而是不同职责和不同权限。

---

# 12. Planner

Planner 是实时市场认知者。

它负责：

- 判断当前市场 regime
- 形成风险倾向
- 决定是否应保持 flat
- 判断哪些 Strategy 更适合当前环境
- 判断当前是否应该增加或减少 exposure
- 综合市场数据、因子、外部情报和账户状态

成熟页面中可以看到典型决策语义：

```text
chopping
remain flat
minimum risk scale
no clean breakout
VWAP
Donchian
funding
```

因此 Planner 不是简单输出：

```text
BUY BTC
SELL ETH
```

它更像输出：

```text
Market Regime
+
Risk Posture
+
Strategy Permission
+
Capital Intent
+
Candidate Action
```

---

# 13. Critic

Critic 是整个系统的重要治理角色。

成熟 Trader 决策页明确表达：

```text
Planner 撰写观点
↓
Critic 裁决
↓
只有获批的动作
↓
才能继续进入交易层
```

所以 Critic 并不是“第二个给建议的模型”。

它具有：

```text
Approve / Veto
```

性质。

因此真正结构是：

```text
Planner
  ↓
Proposal
  ↓
Critic
 ├─ Approve
 └─ Veto
```

而不是：

```text
模型 A / B / C
多数票
```

这意味着：

```text
Cognition
和
Governance
被拆分
```

---

# 14. Researcher

Researcher 是慢速研究 Agent。

它与 Planner 的职责完全不同。

Planner 关注：

```text
现在市场应该怎么处理
```

Researcher 关注：

```text
是否存在新的可交易规律
是否应该增加 / 淘汰 Factor
```

Researcher 的作用可以概括为：

```text
提出候选 Signal
↓
验证
↓
观察
↓
进入 Factor Zoo
↓
保留 / 淘汰
```

所以 Researcher 属于：

```text
Research / Evolution Plane
```

而不是实时交易决策的一部分。

---

# 15. Factor Zoo

成熟系统中的“因子库”是真正的量化 Signal / Factor 管理层，不是普通知识库。

页面公开展示：

```text
Factor Name
Category
Status
IC
rank IC
Historical IC
```

已经看到的核心因子包括：

```text
TSMOM (1w)
Momentum (24h)
Short-term reversal
Channel breakout
Funding carry MR
VWAP mean-reversion
```

因子类别包括：

```text
momentum
reversal
breakout
carry
...
```

---

# 16. Factor 生命周期

Factor Zoo 明确存在：

```text
Core
Active
Trial
Retired
Rejected
```

用户截图对应时点显示：

```text
Core      8
Active    0
Trial     0
Retired   0
Rejected 10
```

这说明：

```text
Researcher 提出 Factor
≠
Factor 自动参与实盘
```

而是存在：

```text
Research
↓
Validation
↓
Promotion / Rejection
```

机制。

---

# 17. IC / rank-IC

Factor Zoo 直接公开：

```text
IC
rank IC
```

说明 Factor 的评价至少包含统计意义上的未来收益相关性。

用户截图中部分公开值为：

```text
TSMOM (1w)
IC      -0.038
rank IC -0.033

Momentum (24h)
IC      +0.005
rank IC -0.007

Short-term reversal
IC      -0.002
rank IC -0.001

Channel breakout
IC      +0.003
rank IC -0.016

Funding carry MR
IC      +0.003
rank IC -0.015

VWAP mean-reversion
IC      +0.016
rank IC +0.030
```

这些数字也说明当时很多 Factor 的统计表现并不强。

因此这个页面并没有伪装成：

```text
AI 找到的每个因子都很厉害
```

反而真实公开了大量接近 0 或负的 IC。

---

# 18. Market Data Plane

从公开 Planner 文本与 Factor Zoo，可以确认或高度推断系统至少使用：

```text
Price
Returns
Momentum
VWAP
Donchian
Funding
Open Interest
Volatility
Factor Signals
```

这些结构化市场数据与外部 Intelligence 一起构成认知输入。

因此整个输入并非只有新闻，也不是只有行情。

---

# 19. Intelligence + Market Data 双输入

系统可以概括为两个主要输入域：

```text
Structured Market Data
+
Unstructured External Intelligence
```

前者包括：

```text
Price
Funding
OI
VWAP
Donchian
Momentum
Volatility
Factor
```

后者包括：

```text
Telegram
X
Polymarket
News
Macro events
Other channels
```

---

# 20. Snapshot

成熟 System Health 页面出现：

```text
镜像快照年龄
```

说明系统存在某种统一的市场状态 / Snapshot。

其意义是：

```text
同一轮 Planner / Critic
基于相对一致的时间点状态做判断
```

而不是不同组件临时各自取数据。

---

# 21. Market Regime / Policy

成熟决策中频繁出现：

```text
chopping
remain flat
minimum risk scale
```

说明系统并不是直接：

```text
Signal → Order
```

中间存在一个明显的：

```text
Regime / Policy Layer
```

用于决定：

- 当前市场是什么状态
- 哪些策略可以工作
- 是否应该缩小风险
- 是否应该保持空仓

---

# 22. Strategy Plane

当前暴露的 Strategy / Signal 类型至少包括：

```text
Momentum
Trend
Breakout
Short-term Reversal
VWAP Mean Reversion
Funding Carry / Funding MR
```

因此成熟系统可以理解为：

```text
Market / Factor Signals
↓
Planner
↓
Regime / Policy
↓
Strategy Permissions
↓
Risk
```

---

# 23. Risk Plane

成熟 Trader 最重要的特征之一，是：

```text
Risk Engine
与
LLM Cognition
明显分离
```

公开页面显示：

```text
Stop-loss coverage
Risk ticks
Max drawdown
Current drawdown
Last risk tick
Daemon uptime
Snapshot age
```

而这些检查频率远高于 LLM 认知。

---

# 24. Risk Daemon

用户截图对应某个时点可以看到类似：

```text
上次认知轮      约 25 分钟前
上次风险巡检    约 13 秒前
镜像快照年龄    约 36 秒
守护进程运行    约 4.9 小时
```

主页某时点还显示：

```text
运行约 0.7 天
决策轮次约 21
风险巡检约 923
```

这说明：

```text
Cognition
= 低频

Risk
= 高频
```

并且 Risk daemon 独立持续运行。

---

# 25. Stop-loss Coverage

主页明确存在：

```text
止损全覆盖
```

说明真实 open position 与 protection 之间存在明确对应关系。

但目前没有公开：

```text
具体 stop distance
ATR multiplier
dynamic stop formula
trailing rule
```

---

# 26. Drawdown Control

UI 公开：

```text
最大回撤
当前回撤
风险状态
```

并且作者对系统的描述中存在 drawdown ladder 概念。

因此系统不仅做：

```text
per-trade stop
```

还做：

```text
portfolio-level drawdown control
```

具体阈值与缩放公式未公开。

---

# 27. Volatility-aware Risk

公开系统描述和决策逻辑表明 volatility 参与仓位 / 风险调整。

因此交易权限不是：

```text
Planner 说买多少
→ 就买多少
```

而会被：

```text
Volatility
Portfolio State
Drawdown
Risk Scale
Strategy State
```

进一步限制。

具体公式未公开。

---

# 28. Execution Plane

系统明显存在实际交易执行层，因为公开项目就是面向真实资金账户。

但目前没有找到完整公开的 production execution source。

没有公开确认的具体实现包括：

```text
Order State Machine
Retry
Partial Fill
Idempotency
Reconciliation
Exchange-specific Logic
```

所以可以确认“执行层存在”，但不能声称已经掌握其源码。

---

# 29. 决策轮类型

成熟决策页面出现至少：

```text
认知轮
事件轮
```

这说明系统既支持：

```text
Scheduled Cognition
```

也支持：

```text
Event-triggered Cognition
```

这和 GenericAgent 的 Scheduler / Reflect 机制能够对应。

---

# 30. 三种时间尺度

整个系统最重要的结构之一是“三速运行”。

```text
FAST
秒级
Risk / Execution

MEDIUM
分钟 / 小时级
Planner / Critic Cognition

SLOW
周级
Researcher / Factor Evolution
```

可以浓缩为：

> **快速确定性控制 + 中速 LLM 认知 + 慢速 LLM 研究。**

---

# 31. 外部信息与 Prompt Injection

作者后续公开讨论表明，系统已经考虑：

```text
TG / X / BBS
等自然语言输入
```

带来的：

```text
错误信息
垃圾信息
操纵信息
Prompt Injection
AI Bot attack
```

问题。

这说明 Intelligence Plane 并不是简单：

```text
抓新闻 → 塞进 Prompt
```

而是已经意识到外部文本属于潜在攻击面。

---

# 32. BBS

后期作者还考虑让 Trader / main brain 接收 BBS 中的人类讨论。

同时公开记录过 AI Bot 攻入 BBS 的问题。

这使：

```text
External Natural Language
```

成为整个系统的重要安全边界。

---

# 33. Observability

成熟系统已经具有相当完整的 Observability。

公开页面至少展示：

```text
Equity
Principal
PnL

Positions

Max Drawdown
Current Drawdown

Decision Rounds
Risk Ticks

Last Cognition
Last Risk Tick

Snapshot Age
Daemon Uptime

Stop Coverage

Planner / Critic / Researcher

Factor Zoo
IC
rank IC

Token / Model Cost
```

因此项目不仅是：

```text
Trading Engine
```

同时也是：

```text
Operations
Monitoring
Audit
Cost Accounting
```

系统。

---

# 34. Dashboard

主页承担整个系统总览。

包括：

```text
账户状态
收益
回撤
当前仓位
Agent 状态
系统 Health
Stop Coverage
Runtime
Decision Rounds
Risk Ticks
```

因此它是一个完整 Control / Observation Dashboard。

---

# 35. Decision Timeline

决策页面展示：

```text
Round Type
Planner View
Critic Verdict
Regime
Final Action
```

因此系统的 AI 决策过程可以被回溯。

用户可以看到：

```text
为什么保持 flat
为什么判断 chopping
为什么降低 risk scale
```

---

# 36. Factor Zoo UI

Factor Zoo 页面公开：

```text
Factor Name
Category
IC
rank IC
State
Historical Trend
```

但具体公式隐藏。

因此其设计同时兼顾：

```text
内部研究管理
+
外部透明展示
+
核心 Formula 保密
```

---

# 37. Token / Cost Observability

Token 页面公开：

```text
30 天模型花费
决策轮数
单轮均价
不同模型成本
```

用户截图时点类似：

```text
30-day cost ≈ $0.60
Rounds = 21
Cost / round ≈ $0.029
```

说明 LLM 成本被作为系统运行指标，而不仅仅是 API 后台账单。

---

# 38. 整个项目可以拆成 9 个 Plane

```text
1. Intelligence Plane
外部消息与情报

2. Market Data Plane
行情、Funding、OI、Indicator、Factor

3. Cognition Plane
Planner

4. Governance Plane
Critic

5. Policy / Strategy Plane
Regime、风险倾向、策略权限

6. Risk Plane
高频确定性风控

7. Execution Plane
订单、仓位、交易所

8. Research / Evolution Plane
Researcher + Factor Zoo

9. Observability Plane
监控、审计、成本、健康状态
```

---

# 39. 整体数据流

```text
      Telegram / X / Polymarket
               │
               ▼
         天才消息官
               │
               ▼
      Intelligence Digest
               │
               │
Market Data ───┼─── Factor Signals
               │
               ▼
           Snapshot
               │
               ▼
            Planner
               │
               ▼
            Critic
        Approve / Veto
               │
               ▼
       Regime / Policy
               │
               ▼
          Strategy
               │
               ▼
    Deterministic Risk
               │
               ▼
          Execution
               │
               ▼
          Exchange
```

研究支线：

```text
Market History
      │
      ▼
  Researcher
      │
      ▼
Candidate Factor
      │
      ▼
  Validation
      │
      ▼
   Factor Zoo
      │
      ├─ Core
      ├─ Active
      ├─ Trial
      ├─ Retired
      └─ Rejected
```

---

# 40. 项目的核心权限分离

整个系统最关键的设计可以浓缩成 6 条：

```text
消息官 ≠ Trader

Planner ≠ Critic

Researcher ≠ Live Trader

LLM Cognition ≠ Risk Engine

Candidate Factor ≠ Active Factor

External Information ≠ Trading Instruction
```

这六条基本概括了整个系统的架构思想。

---

# 41. 项目不是传统量化，也不是纯 Agent

它融合了两套范式。

传统 Systematic Trading：

```text
Market Data
Factor
Signal
IC
Risk
Execution
Drawdown
```

AI Agent：

```text
External Intelligence
LLM Reasoning
Role Separation
Critic
Memory
Self-Evolution
Autonomous Research
```

这个项目真正的特点，就是将两套体系组合起来。

---

# 42. 开源与私有部分边界

## 已公开

```text
GenericAgent
Agent Loop
9 Atomic Tools
Memory 思路
Reflect
Scheduler
部分 Multi-Agent / Worker 能力
```

## 公开展示，但没有完整源码

```text
Trader Dashboard
Planner / Critic / Researcher 架构
Decision Timeline
Factor Zoo
Risk 状态
Token / Cost
系统运行表现
```

## 目前没有找到公开源码

```text
天才消息官实例
Trader 生产系统
Risk Engine
Execution Engine
Factor Formula
私有 Prompt
私有信息源
```

---

# 43. 当前明确未知的信息

目前仍然没有公开确认：

```text
天才消息官完整源码

Telegram 具体频道
X 具体账号
其他私有渠道

Collector 具体去重算法
事件聚类算法
信源评分算法
Digest Prompt

Planner 完整 System Prompt
Critic 完整 System Prompt
Researcher 完整 System Prompt

Planner / Critic 精确 Contract

risk scale 精确公式
volatility sizing 精确公式
drawdown ladder 精确阈值
stop-loss 精确公式

最大杠杆
最大仓位
最大风险预算

Factor 精确数学公式
IC forward horizon
Factor promotion threshold
完整 validation protocol

交易所 execution 实现
partial fill
retry
idempotency
reconciliation

数据库结构
Trader 私有完整源码
```

因此当前已经比较清楚的是：

```text
系统是什么
为什么这么分层
各 Agent 是什么角色
各 Loop 如何分时运行
Factor Zoo 如何存在
Risk 与 LLM 如何隔离
```

但仍不知道：

```text
私有 Prompt
私有参数
私有公式
私有交易源码
私有消息源
```

---

# 44. 最终精准概括

> **该项目是在 GenericAgent 这个最小、自进化 Agent Runtime 上成长起来的一套自主加密资产交易系统。最初形态是基于 GA Reflect 的“TG + X 天才消息官”和多模型“天才交易员”；成熟版本发展为 Planner、Critic、Researcher 三角色体系，其中 Planner 负责实时市场认知、regime 和风险倾向，Critic 负责独立审查并拥有交易动作的批准/否决权，Researcher 负责慢速提出、验证和淘汰因子。系统同时接入结构化市场数据和 TG/X/Polymarket 等外部情报，通过统一市场 Snapshot 形成认知输入。交易层并非由 LLM 直接控制，而是将认知结果继续交给策略、确定性 Risk Engine 和执行层；Risk daemon 以远高于 LLM 认知频率持续运行，并维护止损覆盖、回撤、数据新鲜度和其他风险状态。Researcher 的成果进入 Factor Zoo，以 IC、rank-IC 和 Core/Active/Trial/Retired/Rejected 生命周期管理，候选因子不会自动获得实盘资本权限。系统同时具有 Decision Timeline、Factor Zoo、System Health、风险巡检、Snapshot age、daemon uptime、LLM Token/Cost 等完整观测能力。因此它本质上不是一个“LLM 炒币 Bot”，而是一套把 Agent 认知、独立治理、量化信号、确定性风险、交易执行和持续研究进化组合在一起的 AI-native autonomous systematic trading system。**
