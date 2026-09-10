# GenericAgent × AI Trader 原始资料与链接汇总

> 本文件只汇总与当前项目有关的原始资料入口。  
> 为便于回溯，按照“底座 → 早期雏形 → 成熟 Trader → 关键补充资料 → 原始截图”的顺序整理。

---

# 1. GenericAgent 官方仓库

## GenericAgent GitHub

https://github.com/lsdefine/GenericAgent

作用：

```text
整个项目的 Agent Runtime 底座
```

主要用于查看：

```text
agent_loop.py
agentmain.py
ga.py
llmcore.py
memory/
reflect/
plugins/
frontends/
```

其中最值得先看的：

```text
agent_loop.py
reflect/scheduler.py
reflect/autonomous.py
reflect/agent_team_worker.py
memory/
```

---

# 2. GenericAgent 官方网站

https://gaagent.ai/

作用：

```text
GenericAgent 官方入口
```

---

# 3. GenericAgent Technical Report

https://arxiv.org/abs/2604.17091

作用：

```text
理解 GenericAgent 的技术设计
```

---

# 4. GenericAgent Technical Report 复现仓库

https://github.com/JinyiHan99/GA-Technical-Report

作用：

```text
GenericAgent 技术报告相关代码与数据
```

---

# 5. GenericAgent 社区正式介绍帖

https://linux.do/t/topic/1962519

用途：

```text
理解 GenericAgent 的早期公开介绍
Memory
Reflect
自进化
Browser
SOP
Multi-Agent 方向
```

该帖由 `ozer_23` 发布。

其中一个关键作者回复说明：

```text
项目属于知识工厂团队
肖军组
梁老师（GitHub 作者）主导项目
```

注意：

```text
Linux.DO 用户 ozer_23
≠
GitHub owner lsdefine

目前只能确认团队关联，
不能确认两者是同一个账号。
```

---

# 6. 最关键的历史雏形帖

## GenericAgent 实战 | 天才消息官 + 天才交易员

https://linux.do/t/topic/2029982

发布时间：

```text
2026-04-22
```

这是整个项目历史链中最关键的原始资料之一。

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

还出现：

```text
GA 群的一位佬补上了最后一块拼图
```

该页面现在可能无法正常公开访问，但已经保存过本地 HTML。

原始 canonical URL：

https://linux.do/t/topic/2029982

---

# 7. GenericAgent 接入群聊相关实践

## GenericAgent 实践日记 | 接入国民级 App 群聊

https://linux.do/t/topic/1974935

用途：

```text
理解 ozer_23 如何使用 GA
探索外部系统
接入群聊
形成可复用能力
```

这篇对于理解：

```text
天才消息官可能不是固定 Collector，
而是 GA 自主探索后形成 Skill / SOP
```

非常重要。

---

# 8. GenericAgent Web / Browser 能力相关帖子

https://linux.do/t/topic/1968386

用途：

```text
理解 GenericAgent 的真实浏览器能力
Web Bridge
登录态浏览
网页自动化
从实践中蒸馏 Skill
```

---

# 9. Trader 当前公开运行站点

https://trader.gaagent.ai/

这是目前观察成熟 Trader 最重要的入口。

可用于查看：

```text
Dashboard
Decision Timeline
Factor Zoo
System Health
Model / Token Cost
```

成熟版本公开展示的角色包括：

```text
Planner
Critic
Researcher
```

用户截图对应时点：

```text
Planner     GPT-5.6 Sol
Critic      Grok-4.6
Researcher  Kimi-K3
```

---

# 10. 赛博量化正式启动帖

## [第一章：天才的陨落] GenericAgent 赛博量化启动

https://linux.do/t/topic/2798309

发布时间：

```text
2026-08-23
```

该帖确认：

```text
基于 GenericAgent

使用 Reflect 反射模式

约每 1 小时进行交易认知

初始本金 115 USDC
```

当时模型描述为：

```text
主脑：
GPT-5.6 Sol

圆桌反驳：
Kimi-K3
Grok-4.6
```

当时信息来源明确包括：

```text
天才消息官
TG
X
Polymarket
宏观经济
虚拟币相关信息
```

注意：

```text
这是较早阶段的角色命名。

后来的成熟 Trader 页面已经演化为：

Planner     GPT-5.6 Sol
Critic      Grok-4.6
Researcher  Kimi-K3
```

不要把两个时间点的角色定义直接视为完全相同。

---

# 11. 100 天挑战 Day 1 主帖

## 全自主自进化量化交易 Agent——100 天挑战

https://linux.do/t/topic/2799021

发布时间：

```text
2026-08-24
```

这是成熟公开实验主线。

帖子链接了：

https://trader.gaagent.ai/

并展示成熟 Trader 的多个页面，包括：

```text
主页
决策
因子库
Token 消耗
```

---

# 12. Day 1 第 3 页：消息官最关键的作者回复

https://linux.do/t/topic/2799021?page=3

这是“天才消息官”目前最重要的公开证据之一。

作者明确表示其数据大意为：

```text
不是简单依赖公开数据

自己整合数据

TG + X
+ 一些自己的渠道
```

并明确描述：

```text
有一个信息收集 Agent
先搜集好
再交给交易员
```

同时讨论过：

```text
未来让主脑看 BBS 人类讨论
Prompt Injection
```

附近回复还提到：

```text
整个交易框架由 Fable 协助完成
参考了大量论文和金融交易书籍
```

---

# 13. Day 1 复盘

## BTC 涨了 22%，AI 却在“完美风控”地看戏

https://linux.do/t/topic/2807914

用途：

```text
理解：
Planner / Critic 治理
Risk
Remain Flat
BBS
Token 成本
实盘运行反馈
```

这篇尤其重要的是：

```text
Planner / Critic 治理关系的演进
```

---

# 14. Day 2–4 实盘更新

## 天才交易员，10% 收益率

https://linux.do/t/topic/2819990

用途：

```text
观察系统后续实盘状态
风险变化
止损调整
BBS 安全问题
实际运行演进
```

该阶段公开提到：

```text
BBS 曾被 AI Bot 攻入
之后进行了修复
```

因此 Prompt Injection / 外部 Agent 攻击不是纯理论问题。

---

# 15. Trader Dashboard 原始截图

https://cdn3.ldstatic.com/original/4X/4/7/5/475ab0884d794be0263592c25418d97c2be7f51a.png

内容：

```text
Trader Dashboard
账户
PnL
Drawdown
System Health
Agent Roles
Risk Ticks
Decision Rounds
Stop Coverage
```

---

# 16. Trader Decision Timeline 原始截图

https://cdn3.ldstatic.com/original/4X/c/4/e/c4e0382a30c18cfab7d9a7ead101755cc8fccfc4.png

内容：

```text
认知轮
事件轮
Planner View
Critic Verdict
Regime
Final Decision
```

---

# 17. Trader Factor Zoo 原始截图

https://cdn3.ldstatic.com/original/4X/8/a/6/8a60264bee236cfc8c64372cf64b2832893f3168.png

内容：

```text
Factor Zoo
Core
Active
Trial
Retired
Rejected

IC
rank IC
historical IC
factor category
```

---

# 18. Trader Token / Cost 原始截图

https://cdn3.ldstatic.com/original/4X/6/e/c/6ec44f8bec68a486765227f2ea50eb58d49c3532.png

内容：

```text
30-day model cost
decision rounds
average cost per round
model usage
```

---

# 19. 当前最关键的证据链

如果只保留最重要的 8 个入口：

```text
1.
https://github.com/lsdefine/GenericAgent

2.
https://trader.gaagent.ai/

3.
https://linux.do/t/topic/1962519

4.
https://linux.do/t/topic/2029982

5.
https://linux.do/t/topic/2798309

6.
https://linux.do/t/topic/2799021

7.
https://linux.do/t/topic/2799021?page=3

8.
https://linux.do/t/topic/2819990
```

这条链基本覆盖：

```text
GenericAgent 底座
↓
GA 自进化 / Reflect
↓
天才消息官起源
↓
TG + X
↓
天才交易员
↓
TG + X + Polymarket
↓
独立信息收集 Agent
↓
Planner / Critic / Researcher
↓
Factor Zoo
↓
Risk / Execution
↓
成熟 Trader
```

---

# 20. 开源与私有边界对应的链接

## 可直接查看源码

GenericAgent：

https://github.com/lsdefine/GenericAgent

## 可观察运行行为

Trader：

https://trader.gaagent.ai/

## 可追溯历史演进

GenericAgent 介绍：

https://linux.do/t/topic/1962519

早期天才消息官 + 天才交易员：

https://linux.do/t/topic/2029982

赛博量化正式启动：

https://linux.do/t/topic/2798309

100 天挑战：

https://linux.do/t/topic/2799021

关键作者回复：

https://linux.do/t/topic/2799021?page=3

后续实盘：

https://linux.do/t/topic/2819990

---

# 21. 当前没有找到独立公开链接的部分

截至目前，没有找到独立公开仓库对应：

```text
天才消息官完整源码
Trader production source
Risk Engine
Execution Engine
Factor Formula
Planner Prompt
Critic Prompt
Researcher Prompt
私有 TG / X source list
```

因此这些部分目前只能通过：

```text
作者帖子
公开 Trader UI
决策日志
GenericAgent 源码
```

反推其架构，而不能声称已经拿到原始实现。
