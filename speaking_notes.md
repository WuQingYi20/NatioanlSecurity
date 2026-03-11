# Sentinel-KG 讲解稿 / Speaking Notes

> 目标：用 5-8 分钟，指着 poster 把四个问题讲清楚。中英文混合，关键术语保留英文。

---

## 开场 (30s) — 定义问题

"我们的场景是：瑞典四个政府机构——税务局 Skatteverket、社保局 Försäkringskassan、就业局 Arbetsförmedlingen、公司注册局 Bolagsverket——把各自的数据整合成一个巨大的 Knowledge Graph，然后用 AI agents 在上面搜索威胁。同时，还要对接一家私营公司 CyberSecurity AB，它有自己的国际情报图谱，但服务多个国家——包括可能对瑞典有敌意的国家。

核心挑战是 **dual-system architecture**：一个是 sovereign 主权系统，一个是 commercial 商业系统，信任等级完全不同。"

---

## 架构走读 (60-90s) — 指着图从上到下

"我从上往下讲这个数据流。

**最上面**是 CyberSecurity AB。我们对它的定位是 **untrusted external feed**——假设来源 hypothesis source，不是可信结论。所有向 AB 发的查询都是 obfuscated（混淆的）和 batched（批量的），防止 AB 通过 query pattern 推断瑞典的情报优先级。数据是 **one-way flow**——瑞典查 AB，AB 不能查瑞典。

**下一层**是四个机构的数据，通过 Entity Resolution Pipeline 整合。瑞典有 personnummer（个人身份号码）和 organisationsnummer（组织编号），这是天然的 unique identifier，大约 85% 的实体可以直接匹配，剩下 15% 靠概率匹配 + 人工确认。最终形成 **Sovereign Knowledge Graph**，大约 1 亿+ 节点，10 亿+ 边。

**中间**是 RL Agent Ensemble。关键设计：
- 多个 agent 同时调查同一个异常，用 GRPO（Group Relative Policy Optimization）互相打分
- 如果 agents **agree**，confidence 上升
- 如果 agents **disagree**，自动 escalate 给人类——不是取平均值，而是让人来判断
- 所有 agent 都在 **read-only sandbox** 中运行——不能修改任何记录，不能触发任何执法行动

Reward function 是关键：
```
Reward = α·Threat_Confidence + β·Efficiency − γ·Privacy_Penalty
```
这里要坦诚地讲：**α（威胁置信度）是最弱的信号**，因为它来自历史案例的人类标注——如果过去的调查本身有偏见（比如不成比例地调查某些族群），RL 就会放大这个偏见。而 **γ（隐私惩罚）是最强、最客观的信号**——agent 有没有访问调查范围外的数据？是/否，binary。所以系统被设计成 **默认 under-investigate**（宁可漏掉也不误伤），这是一个 deliberate asymmetry。

**然后**是 Guardrail Layer（稍后详细讲）。

**再下面**是 Human-in-the-Loop Operator。

**最底层**是 Audit Trail——所有操作都被记录，oversight body 和 Riksdag（议会）可以审查。"

---

## RL 建模 (90-120s) — 为什么是 RL，怎么建模

"刚才讲了架构全貌，现在讲一个核心设计决策：**为什么把威胁搜索建模为强化学习问题**。

### 为什么是 RL 而不是其他方法？

首先，这个问题的本质是 **sequential decision making**——agent 在图上一步一步走，每一步选择'往哪个邻居走'或者'该不该提交证据'。这不是一个分类问题（给我一个实体，告诉我它是不是威胁），而是一连串决策组成的调查过程。

三个特性让它天然适合 RL：

1. **Delayed reward**：agent 走 20 步之后提交 evidence bundle，才知道这次调查做得好不好。中间每一步的价值需要从最终结果反向传播——这正是 RL 的 temporal credit assignment 擅长的。

2. **Exploration-exploitation tradeoff**：Knowledge graph 上一个 degree 50 的节点，5 hops 就有 3 亿可达节点。你不能穷举——必须学会在'继续深挖当前线索'和'尝试新方向'之间平衡。

3. **环境约束需要被内化**：privacy constraint 不是事后检查——agent 必须**在训练阶段就学会走窄路径**，主动避开无关的个人数据。这比 rule-based filter 更灵活，因为 agent 会学会哪些路径**值得冒隐私代价**去探索。

Supervised learning 做不到这些：你没有足够的'标准调查路径'标注数据，而且历史调查路径本身可能有偏见。

### MDP 建模：State → Action → Transition → Reward

现在讲具体怎么把它映射成 Markov Decision Process。

**State（观测空间）**：48 维向量，全部归一化到 [0, 1]。分四块：

- **当前节点特征** [0:6]：节点类型 one-hot（PERSON / COMPANY / TRANSACTION / ADDRESS）、交易金额、是否已在证据列表中。Agent 知道自己站在哪里。
- **邻居结构** [6:18]：按关系类别（FINANCIAL / CORPORATE / PERSONAL）统计的邻居数量、邻居节点类型分布、邻域交易金额均值和最大值、低置信度边的比例、数据来源多样性。Agent 知道周围有什么。
- **调查进度** [18:26]：已用步数、已访问节点比例、已收集证据数量、当前 clearance level、剩余 budget、已覆盖的 threat 节点比例。Agent 知道自己进展到哪里了。
- **历史摘要** [26:48]：访问过的节点按类型×来源机构的直方图、全图统计量。Agent 知道自己的调查'画像'。

关键设计选择：**agent 看不到原始节点 ID 和原始关系**——只有统计特征。这是 data minimization by design：即使 agent 的 observation 被泄漏，也不会暴露具体个人信息。

**Action（动作空间）**：`MultiDiscrete([3, 20])`，三个离散动作 + 一个参数：

- `explore_node(neighbor_idx)` — 移动到第 idx 个可见邻居。这是调查的主要动作——沿着图走。
- `request_clearance()` — 请求提升 clearance level，解锁 PERSONAL 类别的关系（默认只能看到 FINANCIAL 和 CORPORATE）。训练中模拟 80% 批准率，部署时需要真人批准。
- `submit_evidence_bundle()` — 结束调查，提交收集到的证据。这是一个**不可逆决策**——提交后 episode 结束。

为什么是这三个 action？因为它们对应真实调查中的三个核心决策：**跟线索、升权限、下结论**。Action space 的极简设计是刻意的——不给 agent 更多能力就是一种安全保证。

**Transition（状态转移）**：agent 选择 explore_node 后，当前位置移动到目标节点，visited 集合更新，evidence 列表增长。关键约束是 **Semantic Window**：

- Clearance 0 → 只能看到 FINANCIAL 和 CORPORATE 边
- Clearance 1 → 额外看到 PERSONAL 边

这意味着同一个图，不同 clearance level 下 agent 看到的**拓扑结构完全不同**——transition function 本身受 clearance 约束。

**Reward（奖励函数）**：这是整个建模最核心的部分。

```
Reward = α·Threat_Confidence + β·Efficiency − γ·Privacy_Penalty
α = 0.3,  β = 0.1,  γ = 1.0
```

注意 **γ >> α**——这不是调参的结果，是**价值判断的编码**。三个 term 的信号质量完全不同：

| Term | 信号质量 | 类比 |
|------|---------|------|
| γ Privacy Penalty | **强 / 客观** — agent 有没有碰调查范围外的数据？binary | 类似 Atlantis 的'编译是否通过' |
| β Efficiency | **中 / 客观** — 用了多少步、访问了多少节点 | 可测量，但噪声大 |
| α Threat Confidence | **弱 / 主观** — 来自历史人类标注 | 没有 ground truth，带偏见 |

具体奖励分配：
- 访问 threat 节点：+0.06（=α×0.2）
- 访问无关个人数据：**−0.3**（=γ×0.3）——惩罚是奖励的 **5 倍**
- 走低置信度 entity resolution 边：额外 −0.1
- 提交时：按 evidence 中 threat 节点的 precision × recall 计算 F1，×α×10
- 每步固定成本：−0.001（=β×0.01）
- 超出 50 步 budget：−0.5

这个奖励结构让 agent 学到的策略是：**精准打击、快速提交、绝不乱碰个人数据**。宁可漏掉一个真实威胁（−0 reward），也不碰一个无辜者的数据（−0.3 penalty）。

### Episode 结构

每个 episode 就是一次完整调查：
- **开始**：70% 概率从已知 threat seed 节点出发（curriculum learning——先学简单的），30% 随机出发
- **结束**：agent 选择 submit（主动结束）或耗尽 50 步 budget（被动截断，额外惩罚）
- **目标**：找到 threat cluster 中的节点，收集到 evidence bundle 中，然后提交

这跟 Atlantis 的 episode 结构很像——Atlantis 的 agent 从一个 seed vulnerability 出发，探索代码图，最终提交 patch。区别在于 Atlantis agent 提交后有自动化验证（编译+测试），我们没有——所以需要 guardrail layer 补偿。"

---

## Q1: Agent-Operator 沟通 (60s)

"第一个问题：agent 和 operator 之间的沟通怎么设计？

核心设计理念是 **anti-automation-bias**——防止操作员盲信 AI。

每个 agent 的输出是一个 structured evidence bundle，包含七个字段：
- **CLAIM**：具体的威胁假设，比如'Entity X shows patterns consistent with money laundering'
- **EVIDENCE[]**：支持这个假设的具体 KG 节点和边，每一条都有数据来源
- **ALTERNATIVE**：**mandatory**，必须给出最合理的良性解释——如果 agent 连一个合理的替代解释都想不出来，说明它可能 overfitting
- **CONFIDENCE**：不是一个数字，是一个 **interval**，比如 0.72 (0.58–0.85)
- **GAPS**：agent 自己承认它不知道什么
- **RISK_LEVEL**：注意这个不是 agent 自己报的——是 guardrail layer 独立评估的。agent 的 self-reported risk 被直接丢弃，因为你不能让被评估者自己给自己打分

关键 UX 设计：**evidence shown first, conclusion hidden**。操作员先看到证据，形成自己的初步判断，然后才看到 AI 的结论。这防止了 anchoring effect。

Risk-tiered routing：
- Low → 普通分析师处理
- Medium → 高级分析师，必须写书面推理
- High → 高级分析师 + **强制等待时间**——不能秒批
- Critical → **双人独立审批**"

---

## Q2: Guardrails (60s)

"第二个问题：实施哪些 guardrails？

我们设计了 **三层防护**：

**Layer 1 — Training-time**：通过 reward function 的 γ privacy penalty，在训练阶段就让 agent 学会走窄路径、不碰无关数据。加上 read-only sandbox 这个 structural guarantee。

**Layer 2 — Runtime**：六个自动检查，G1 到 G6：
- G1 Confidence Calibration：用 Platt scaling 重新校准置信度——LLM 原始 confidence 系统性偏高
- G2 Scope Boundary：检查 agent 的操作是否在授权范围内
- G3 Anti-Hallucination：这是从 Atlantis CRS 借来的——evidence 必须 cryptographically map 到真实数据库条目，agent 不能凭空捏造关系
- G4 Evidence Sufficiency：风险等级越高，要求的证据越多
- G5 Disproportion Detector：统计检查某个 demographic、行业、地区是否被不成比例地 flag——这是 bias check
- G6 Independent Risk Assessment：guardrail 层自己算 risk level，**丢弃 agent 的自我评估**

其中 G1-G4, G6 是 hard fail——不通过就 block；G5 是 soft flag。

**Layer 3 — Human-in-the-Loop**：刚才 Q1 讲过的 risk-tiered routing。

最重要的设计原则：**structurally non-bypassable, fail-closed**。没有 maintenance mode，没有 admin override，没有'紧急情况跳过检查'。任何 governance component 出故障，pipeline 就停——不会让未检查的 output 通过。"

---

## Q3: 可靠性 (45s)

"第三个问题：怎么保证结果可靠？

六个机制：

1. **Multi-agent cross-validation**：不是一个 agent 说了算。多个 agent 用不同的 LoRA adapter 和 prompt 策略独立调查同一个目标。意见一致 → confidence up；意见不一致 → 自动上报人类，附带完整的分歧分析。

2. **Confidence calibration**：LLM 天生 overconfident。Platt scaling 把 raw confidence 转成校准概率。每月监控 ECE（Expected Calibration Error），超标就 suspend 或 recalibrate。

3. **Anti-hallucination**：每一条 evidence 必须 map 到真实数据库条目。agent 不能发明不存在的关系。

4. **Bias detection**：每季度统计各 demographic group 的 flagging rate。如果 operator approval rate 持续 > 95%——说明在 rubber-stamping——触发 operator retraining。

5. **Red team testing**：部署前和定期进行对抗测试——注入已知的 positive 和 negative，测试 adversarial manipulation，测试 operator 是否真的在审查。

6. **Feedback loop**：调查后没有 action 的案例（false positive）反馈给 RL pipeline，减少同类 false positive。

一个坦诚的承认：跟 code vulnerability detection 不同——代码漏洞是 ground truth（漏洞存在或不存在，patch 编译或不编译），而 threat assessment 是 **fundamentally subjective**——所以系统不能 fully autonomous，需要定期审计 training signal 本身。"

---

## Q4: 伦理与政治 (90s) — 最重要的部分

"最后也是最重要的问题：伦理和政治风险。

先讲瑞典特殊的历史背景：

**IB affair (1973)**：瑞典军事情报局 IB 被曝光秘密建立了一个登记簿，跟踪工会成员和政治活动人士。这件事至今是瑞典公民自由讨论的 defining moment。

**FRA-lagen (2008)**：瑞典通过了 signals intelligence 法案，允许 FRA（瑞典国防无线电局）监控跨境通信。引发了巨大的公众抗议。

这两个先例告诉我们：在瑞典，任何涉及公民数据的 AI 系统都必须 **earn trust, not assume it**。

五个核心风险：

1. **False positives 的不对称代价**：在代码漏洞检测中，false positive 浪费的是算力；在这个系统中，false positive 意味着一个无辜的人被调查——对声誉和自由的伤害是 **irreversible** 的。所以系统设计成 under-investigate。

2. **Chilling effect**：光是知道这个系统存在，就可能让人自我审查——不敢跟某些人来往、不敢做某些合法交易。这不是技术能解决的，是 perception 问题。

3. **Discriminatory targeting**：历史调查数据本身可能有偏见。如果过去不成比例地调查了某些族群，RL 会学到这个 pattern 并放大它。G5 disproportion detector 可以检测，但不能根本解决——需要持续的人工审计。

4. **Mission creep**：今天说只用于反洗钱和反恐，明天政治压力可能让它扩展到 tax evasion、welfare fraud、甚至政治异见。我们的工程设计让 scope expansion 需要几个月的 re-engineering——不是改个配置就行——但政治压力可以 override 技术约束。

5. **Automation bias**：即使有 evidence-first UI，operator 时间久了也可能 rubber-stamp。95% 以上的 approval rate 触发 retraining，但 human behavior is harder to engineer than system behavior。

**公民会要求什么**：

1. **Transparency（透明）**：公开披露系统访问什么数据、做什么分析、以及汇总的 flagging rate 和结果
2. **Right to Know（知情权）**：被调查后 cleared 的人，在一定期限后必须被通知
3. **Right to Contest（申诉权）**：可以挑战 AI 参与的决策，可以看到（脱密版的）证据和推理
4. **Sunset Clause（落日条款）**：Riksdag 每 3 年审批一次，不是永久部署
5. **Independent Oversight（独立监督）**：一个有完全审计权限和停止运营权力的独立机构

**全球影响**：

- **Precedent effect**：瑞典如果做好了，树立全球正面标杆——看，民主国家可以负责任地使用这种系统。如果做砸了，就给威权国家提供了合法性：'瑞典都在做，我们也可以'。

- **CyberSecurity AB 的结构性利益冲突**：AB 同时服务多个国家。瑞典无法知道 AB 的其他客户是谁，也无法知道他们在查什么。这不是一个工程问题——这是一个 **structural conflict of interest**。所以架构设计成 AB 是 plugin, not dependency——随时可以断开连接，不影响核心能力。

最后一句话总结：'The question is not whether Sweden can build this system. The question is whether Sweden can build it in a way that its citizens would accept — and that future governments cannot easily abuse.'"

---

## English Presentation Script — RL Modeling (60-90s)

> 可以直接读。指着图讲。

"We propose using **reinforcement learning to optimize how LLM agents search** through a national security knowledge graph.

Here is how it works. We launch **multiple agents simultaneously**, each starting from a different point in the graph. At each step, an agent can only see a **small subgraph** — not the entire database. This is by design: data minimization.

Each agent then makes a decision. It can do one of three things:

- **Expand** — request more of the graph, follow a lead to a neighboring node.
- **Escalate** — if it finds something suspicious, submit an evidence bundle back to a human operator.
- Or **request clearance** — ask for permission to access more sensitive data, like personal relationships.

The human operator reviews the evidence, makes a judgment — was this a real threat, or a false alarm? — and that judgment **feeds back as a reward signal** to fine-tune the agent.

Now, we run multiple agents with **different strategies**. They compete through a method called GRPO — Group Relative Policy Optimization. If one agent finds the same threat in **fewer steps**, it gets a higher efficiency reward. If agents **agree**, confidence goes up. If they **disagree**, we don't average — we escalate to a human.

The reward function has three terms:

1. **Threat confidence** — did the human confirm this was a real threat? This is our weakest signal because it depends on subjective human judgment.
2. **Efficiency** — how many steps did the agent take? Faster is better.
3. **Privacy penalty** — did the agent try to access data outside its authorized scope? If yes, heavy penalty. This is our strongest, most objective signal.

The key design choice: the privacy penalty **massively outweighs** the threat reward. The system is deliberately biased toward **under-investigating rather than over-investigating** — because a false positive means investigating an innocent person.

For training, we use **LoRA — Low-Rank Adaptation**. Instead of retraining the entire model, we only update a small external adapter — less than one percent of the model's parameters. This means training can run on **consumer-grade GPUs**, on-premise, fully air-gapped. No data ever leaves the government network.

The result: agents that learn to **find threats fast, stay within scope, and never touch data they shouldn't**."

---

## 如果被提问 / Q&A 准备

**Q: 为什么用 RL 而不是传统规则系统？**
"规则系统在已知 pattern 上有效，但 multi-hop graph traversal 有组合爆炸问题——一个平均 degree 50 的节点，5 hops 就有 3 亿个可达节点。RL agents 学会了 prioritize promising paths，比穷举高效得多。但我们很坦诚：RL 的 reward signal 在这个 domain 比在代码漏洞检测中弱得多。"

**Q: Semantic window 怎么工作？**
"默认用 relationship-type filtering——financial crime investigation 只看 financial relationships，personal relationships 默认不可见，需要 request_clearance() 人工批准才能看到。这个选择有 tradeoff：比 fixed-hop boundary 更精准，但依赖预定义的 relationship ontology。家庭成员在被调查公司任职——这是 financial 还是 personal？边界不总是清楚的。"

**Q: GDPR 怎么处理？**
"三个层面：data minimization 通过 semantic window 实现——agent 看不到全部数据库；purpose limitation 通过 action space 实现——每个查询必须声明 investigation context；audit trail 满足 EU AI Act 的 high-risk system 要求。整个系统 air-gapped on-premise 运行，没有数据离开政府内网。"

**Q: 跟 Atlantis CRS 有什么关系？**
"Atlantis 是 DARPA AIxCC 竞赛中 Team Atlanta 的 Cyber Reasoning System，用 RL agents 自动发现和修复代码漏洞。我们借了它的 structural patterns——RL loop、sandboxed environment、multi-agent ensemble、anti-hallucination validation。但最关键的区别是 reward signal：代码漏洞是 objective ground truth（有就是有，没有就是没有），而 threat assessment 是 subjective——来自人类标注的历史案例。所以我们不能像 Atlantis 那样做 fully autonomous loop，governance layers 存在的原因就是 RL pipeline alone 无法承担在 Atlantis 中它能承担的重量。"

**Q: 如果 AB 的数据被投毒怎么办？**
"AB 的输出永远不直接合并进 sovereign KG——存在独立的隔离数据层。AB 的 threat assessment 被当作 hypothesis，必须用 sovereign 系统自己的数据和 agents 独立验证。两个系统一致 → confidence 上升；矛盾 → 深入审查。AB 是 enrichment layer，不是 foundation——如果问题不可控，正确的反应是断开连接。"

**Q: 这个系统跟中国的社会信用有什么区别？**
"四个根本区别：(1) Fail-closed design——governance failure 停止系统，不是放行；(2) 没有自动执法——系统只是 advisor，所有行动必须人类批准；(3) Sunset clause——3 年后 Riksdag 可以选择不续期；(4) Right to contest——公民可以挑战 AI 参与的决策。本质区别是 democratic accountability 被编码进了 architecture，不是事后附加的。"
