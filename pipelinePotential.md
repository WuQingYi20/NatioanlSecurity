# Atlantis CRS Pipeline 深度分析

> AIxCC Team Atlanta 的 Cyber Reasoning System (Atlantis) — 自动化漏洞发现、分析与修补系统全面解析
>
> 文档版本 2.0 — 包含源码级追踪、工具链深度解析与完整架构图

---

## 目录

- [第一部分：项目总览与架构](#第一部分项目总览与架构)
- [第二部分：端到端漏洞发现 Pipeline](#第二部分端到端漏洞发现-pipeline)
- [第三部分：UniAFL 模糊器内核深度解析](#第三部分uniafl-模糊器内核深度解析)
- [第四部分：静态分析工具链深度解析](#第四部分静态分析工具链深度解析)
- [第五部分：P4 框架源码级追踪](#第五部分p4-框架源码级追踪)
- [第六部分：AI 强化学习训练 Pipeline](#第六部分ai-强化学习训练-pipeline)
- [第七部分：Fuzzing Harness 工程模式](#第七部分fuzzing-harness-工程模式)
- [第八部分：基础设施与部署架构](#第八部分基础设施与部署架构)
- [第九部分：可复用 Pipeline 提取](#第九部分可复用-pipeline-提取)
- [第十部分：关键设计模式总结](#第十部分关键设计模式总结)

---

## 第一部分：项目总览与架构

### 1.1 系统定位

Atlantis 是 AIxCC (AI Cyber Challenge, DARPA 主办) 竞赛中 Team Atlanta 开发的 **Cyber Reasoning System (CRS)**。核心理念：将漏洞发现与修复建模为 **强化学习 (RL) 问题**，使用 LLM 作为决策引擎。系统能够：

1. **发现漏洞** — Ensemble Fuzzing (6 策略) + 多工具静态分析
2. **分析漏洞** — SARIF 报告 + 调用图可达性 + LLM 语义匹配
3. **修补漏洞** — 4 节点 × 多 LLM Agent 并行补丁生成 + 三阶段验证
4. **训练模型** — GRPO 强化学习 + 课程学习 + LoRA 动态适配

### 1.2 整体架构图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Competition Framework                            │
│                    (HTTP Task / SARIF Broadcast)                          │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │ POST /v1/task/ (HTTP Basic Auth)
                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     CRS WebServer (FastAPI)                               │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────────┐       │
│  │  Task Server     │  │  CRS Manager     │  │  K8s Manager       │       │
│  │  (REST API +     │→ │  (Redis 状态机   │→ │  (AKS Node Pool    │       │
│  │   BasicAuth)     │  │   + 子进程派发)   │  │   + Pod Template)  │       │
│  └─────────────────┘  └──────────────────┘  └────────────────────┘       │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │ K8s Deploy cp-manager-{task_id}
                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      CP Manager (per Task)                                │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────────┐       │
│  │  VAPI Server     │  │  Build Pipeline  │  │  Node Launcher     │       │
│  │  (POV/Patch/     │  │  (multilang +    │  │  (按 harness 数量  │       │
│  │   SARIF 提交)    │  │   sanitizer +    │  │   动态创建节点)    │       │
│  │                  │  │   symcc 编译)    │  │                    │       │
│  └─────────────────┘  └──────────────────┘  └────────┬───────────┘       │
└──────────────────────────────────────────────┬────────┼──────────────────┘
                                               │        │
           ┌───────────────┬───────────────┬───┘        │
           ▼               ▼               ▼            ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ crs-multilang│ │  crs-sarif   │ │  crs-patch   │ │crs-userspace │
│              │ │              │ │              │ │              │
│ UniAFL (Rust)│ │ CodeQL +     │ │ Multi-LLM    │ │ 11 Kafka     │
│ Ensemble     │ │ Joern CPG +  │ │ Agent 补丁   │ │ 微服务       │
│ Fuzzing      │ │ SVF 指针 +   │ │ 4节点并行    │ │ Protobuf     │
│ (6 策略 MSA) │ │ Sootup JVM + │ │ 三阶段验证   │ │ 消息驱动     │
│              │ │ Tracer 动态  │ │              │ │              │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
       │                │                │                │
       └────────────────┴────────────────┴────────────────┘
              共享文件系统 (/tarball-fs/) + Redis + Kafka
```

### 1.3 核心技术栈

| 层次 | 技术 | 版本/细节 |
|------|------|-----------|
| **语言** | Python (编排/AI), Rust (UniAFL), C (Harness/Tracer) | Python ≥3.12, Rust + LibAFL 0.13.2 |
| **Web** | FastAPI | CRS WebServer, VAPI, SARIF API, Patch API |
| **容器** | Docker + ghcr.io/aixcc-finals/base-builder:v1.2.1 | 沙箱隔离, ccache 加速 |
| **编排** | Kubernetes AKS + Kustomize | 动态节点池, RBAC cluster-admin |
| **IaC** | Terraform (GCP GKE + Redis + VPC) | prevent_destroy, Cloud NAT |
| **消息** | Redis (状态机), Kafka + Protobuf (微服务) | Redis 6.x, BASIC tier |
| **LLM** | LiteLLM 1.72.4 (统一接口) | Claude 3.7, GPT-4o, o3, o4-mini, Gemini 2.5 Pro |
| **RL 训练** | TRL (GRPO) + vLLM ≥0.8.5 + PEFT ≥0.15.2 | LoRA rank=16, liger-kernel |
| **静态分析** | CodeQL, Joern (CPG), SVF (指针), Sootup (JVM) | 18 种 PTA 算法 |
| **动态分析** | UniAFL (LibAFL), SymCC/SymQEMU, Z3 | ASAN/UBSAN/MSAN |
| **代码搜索** | GNU Global (gtags), ast-grep-py | C++/Java/Solidity AST |
| **可观测性** | OpenTelemetry + Phoenix | OTLP gRPC, 60s span 窗口 |
| **实验追踪** | Weights & Biases (wandb) | GRPO 训练指标 |
| **网络** | Tailscale mesh | K8s egress 到竞赛服务器 |

### 1.4 完整项目结构

```
aixcc-afc-atlantis/
├── example-crs-webservice/
│   ├── crs_webserver/my_crs/
│   │   ├── task_server/main.py          # FastAPI 任务入口
│   │   └── crs_manager/crs_manager.py   # 任务调度 + Redis 状态机
│   ├── cp_manager/
│   │   ├── vapi_server/main.py          # per-CP REST API
│   │   └── cp_manager.py               # 编译 + 节点编排
│   ├── crs-multilang/
│   │   ├── bin/main.py                  # Fuzzing Python 编排
│   │   ├── bin/watchdog.py              # POV 监控
│   │   ├── bin/seed_share.py            # 语料库同步 (300s)
│   │   └── uniafl/src/                  # Rust 模糊器内核
│   │       ├── main.rs                  # 入口 (Fuzzing/Executor 模式)
│   │       ├── msa/mod.rs               # MSA 编排
│   │       ├── msa/fuzzer.rs            # Worker 线程主循环
│   │       ├── msa/scheduler.rs         # 加权语料库调度
│   │       ├── msa/stage/mlla.rs        # LLM 引导变异
│   │       ├── msa/stage/input_gen.rs   # 输入生成 Stage
│   │       ├── input_gen/manager.rs     # POSIX 共享内存 IPC
│   │       ├── input_gen/testlang/      # 结构化输入生成
│   │       ├── input_gen/dict/          # LLM 字典生成
│   │       └── concolic/               # SymCC/SymQEMU 约束求解
│   ├── crs-sarif/
│   │   ├── api/ssapi-server/main.py     # SARIF REST API
│   │   ├── crs_sarif/main.py            # 4 阶段初始化
│   │   ├── crs_sarif/services/analyser.py  # 多工具调用图
│   │   ├── crs_sarif/services/matcher.py   # LLM 语义匹配
│   │   └── sarif/sarif/validator/reachability/
│   │       ├── codeql.py                # CodeQL 调用图
│   │       ├── svf.py                   # SVF 指针分析 (8 模式)
│   │       ├── sootup.py               # Sootup JVM (18 算法)
│   │       └── joern.py                # Joern CPG 查询
│   ├── crs-patch/
│   │   └── packages/crs_patch/
│   │       ├── main.py                  # 补丁 API
│   │       ├── configs.json             # 4 节点 Agent 配置
│   │       └── services/
│   │           ├── patch_checker.py     # 三阶段验证
│   │           ├── patch_manager.py     # 回归测试管理
│   │           └── submitter.py         # VAPI 提交
│   └── crs-userspace/
│       ├── bootstrap/run.py             # Kafka 引导
│       └── microservices/               # 11 个微服务
│
├── example-crs-appendix/pcb/
│   ├── packages/
│   │   ├── p4/                          # ★ P4 核心框架 (740 行)
│   │   │   ├── p4/__init__.py           # 全部具体实现
│   │   │   └── p4_core/                 # 纯协议层
│   │   ├── python-trainer/              # GRPO + Curriculum
│   │   ├── python-oss-fuzz/             # Docker 沙箱
│   │   ├── python-oss-fuzz-vulnerability/ # 漏洞元数据
│   │   ├── python-llm/                  # LiteLLM 包装
│   │   └── python-docker-extension/     # Docker 工具库
│   └── projects/binutils/              # Harness 示例
│
└── k8s/                                 # Kubernetes 配置
    ├── base/crs-webservice/             # Kustomize + OTEL
    └── base/tailscale-connections/      # 网络出口
```

---

## 第二部分：端到端漏洞发现 Pipeline

### 2.1 任务接收与调度

**关键文件：** `crs_webserver/my_crs/task_server/main.py`, `crs_manager/crs_manager.py`

```
Competition Framework
    │
    │  POST /v1/task/ (HTTP Basic Auth: CRS_KEY_ID/CRS_KEY_TOKEN)
    ▼
Task Server (FastAPI)
    │  端点: GET /status/, POST /v1/task/, DELETE /v1/task/{id}/, POST /v1/sarif/
    │
    │  CRSManager.invoke_process_task(task)
    ▼
Redis 存储: msg_{message_id} → Task JSON
    │
    │  fork subprocess: python3 -m crs_manager process_task {msg_id}
    ▼
CRS Manager 子进程
    ├── 创建 /tarball-fs/{task_id}/、写入 metadata.json
    ├── 验证 harnesses_included 标志 (无 harness → 跳过)
    ├── 创建 TaskStatus → Redis (task_{task_id}, state=Running)
    ├── invoke_cancel_task(deadline) → 到时取消
    ├── K8s.create_or_reuse_cp_node_pool(task_detail)
    └── K8s.deploy_from_template("cp-manager-node", node_pool, ...)
```

**Redis 状态追踪 Key：**

| Key 模式 | 内容 | 生命周期 |
|----------|------|----------|
| `msg_{message_id}` | Task/SARIF JSON | 接收 → 处理完 |
| `task_{task_id}` | TaskStatus (state, cp_manager_service) | 整个任务周期 |
| `running/pending/failed/succeeded/errored/canceled` | 计数器 | 全局统计 |
| `since` | 重置时间戳 | DELETE /status/ 重置 |

### 2.2 挑战项目管理

**关键文件：** `cp_manager/cp_manager.py`, `cp_manager/vapi_server/main.py`

**CP Manager 并行启动流程：**

```
CPManager.launch()  [检查 launched-{TASK_ID} Redis key 防重入]
    │
    ├── Thread 1: __build()                            Thread 2: __launch_nodes()
    │   ├── __download()                                   ├── __launch_crs_multilang()
    │   │   下载 repo.tar.gz                               │   1 节点/harness
    │   │   下载 oss-fuzz.tar.gz                           │
    │   │   下载 diff.tar.gz (delta 模式)                  ├── __launch_crs_sarif()
    │   │                                                  │   1 节点
    │   ├── __build_multilang()                            │
    │   │   /app/bin/crs-multilang.py build                ├── __launch_crs_patch()
    │   │   target, tar-dir, out-dir, focus, registry      │   5 节点
    │   │                                                  │
    │   ├── __build_all_sanitizers()                       ├── __launch_crs_userspace()
    │   │   逐 sanitizer 编译                              │   1-4 节点 (非 JVM)
    │   │   DELTA 模式: HEAD + BASE 双版本                 │
    │   │                                                  └── __launch_crs_java()
    │   └── __build_symcc()                                    (JVM 专用)
    │       符号执行编译
    │
    └── 等待全部线程完成
```

**vCPU 预算分配算法：**

```python
# cp_manager.py: __calculate_node_size()
total_budget = QUOTA_PER_CP                          # 总 vCPU 时间预算
running_hours = (deadline - now).total_seconds() / 3600

cp_mgr_spend = 3 * vcpu_count * running_hours        # CP-Manager + sarif + multilang_cp
patch_spend  = 5 * vcpu_count * running_hours         # 5 个 Patch 节点

remaining = total_budget - cp_mgr_spend - patch_spend

# 按 harness 数量选择节点规格 (降级策略)
for size in [128, 96, 64, 48, 32, 16, 8, 4]:
    if size * harness_count * running_hours <= remaining:
        return f"Standard_D{size}ds_v6"
```

### 2.3 漏洞发现：Ensemble Fuzzing

**关键文件：** `crs-multilang/bin/main.py`, `uniafl/src/msa/mod.rs`

```
AnyCRS("CRS-Multilang", AnyHR, conf, cp).run(True)
    │
    ├── 配置发现: 扫描 LLVMFuzzerTestOneInput / fuzzerTestOneInput 入口
    ├── LLVM symbolizer 定位源文件
    ├── 运行 dummy seeds 收集覆盖率
    │
    │  启动三个后台进程:
    ├── watchdog.py  (每 600s 检查 corpus/coverage/pov 状态)
    ├── seed_share.py (每 300s 双向同步语料库)
    └── jazzer_cleaner.py (JVM 清理)
    │
    │  setarch x86_64 -R uniafl --config <config.json>
    ▼
UniAFL MSA Pipeline (Rust)
    │
    │  N 个 Worker 线程 (每 CPU 核心 1 个, CPU 亲和性绑定)
    │  每个 Worker 无限循环执行 Stage 序列:
    │
    ├── TestStage                    → 随机测试输入
    ├── InputGenStage (TestLang)     → Workers [0, N/4)    结构化输入
    ├── InputGenStage (Concolic)     → Workers [N/4, N/2)  SymCC/Z3 约束求解
    ├── InputGenStage (Dict)         → Workers [N/2, 3N/4) LLM 字典变异
    ├── GivenFuzzerStage             → 所有 Workers        原生 libFuzzer
    ├── MllaStage                    → 所有 Workers        LLM 脚本执行
    └── SeedShareStage               → 所有 Workers        跨实例种子导入
    │
    │  每个 Stage 执行后:
    ├── 运行输入 → 检查覆盖率 (normal + testlang)
    ├── 有新覆盖 → 添加到 corpus + 更新 scheduler 权重
    ├── 触发 crash → POV 验证 → 保存到 pov_dir → 提交
    └── 循环
```

**语料库共享 (`seed_share.py`)：**

```python
# 每 300 秒同步一次
def sync(self):
    self.copy_ours_to_share()                    # 导出本地发现
    self.copy_coverage_to_share()                # 共享 .cov 文件
    self.copy_share_to_ours("crs-java")          # 导入 Java 发现
    self.copy_share_to_ours("crs-userspace")     # 导入微服务发现
    self.copy_share_to_ours("crs-sarif")         # 导入静态分析 POC

# 共享目录: share_dir/crs-multilang/{harness_name}/
# 覆盖率目录: share_dir/coverage_shared_dir/{harness_name}/
```

### 2.4 漏洞发现：静态分析

**关键文件：** `crs-sarif/crs_sarif/main.py`, `crs_sarif/services/analyser.py`

**4 阶段初始化流水线：**

```
Phase 1: CodeQL → 等待 CODEQL_DONE → 初始化 CodeQLReachabilityAnalyser → 生成调用图
Phase 2: Joern  → 等待 Joern CPG 构建 → 初始化 SarifServerManager
Phase 3: 辅助   → C/C++: SVFReachabilityAnalyser (8 模式, 4 Worker 并行)
               → Java: SootupReachabilityAnalyser (CHA/RTA/PTA, 18 种算法)
               → 合并辅助调用图到主 CodeQL 图
Phase 4: POC   → C/C++ 仅: blobgen + Joern CPG → LLM 生成概念验证
```

**动态调用图更新 (每 180 秒)：**

```python
# analyser.py: update_callgraphs()
def update_callgraphs(self):
    for trace_file in glob(call_trace_shared_dir / "*.edges"):
        edges = parse_relations(trace_file)    # Relations_C 或 Relations_Java
        for graph in self.callgraphs.values():
            graph.update_callgraph_batch(edges)  # batch 更新
        os.remove(trace_file)                    # 处理完删除

    self.update_analysis_results()   # 重新分析所有 SARIF
    self.broadcast_analysis_result() # 广播更新到 VAPI
```

**调用图数据结构：**

```python
# 基于 NetworkX DiGraph
class CallGraph:
    graph: nx.DiGraph

    # 节点: Function(file, function_name, class, method_descriptor, start_line, end_line)
    # 边类型:
    #   STRONG (直接调用) → 高置信度 (HIGH)
    #   WEAK   (间接/多态) → 低置信度 (LOW)
    # 调用类型: DIRECT, INDIRECT, POLYMORPHIC, DYNAMIC
```

**SARIF 匹配 Agent：**
- LLM: Claude 3.7 Sonnet
- 框架: LangGraph 状态机
- 流程: MatchingNode → RetrieverNode (源码上下文) → MATCHED/NOT_MATCHED/UNCERTAIN

### 2.5 补丁生成

**关键文件：** `crs-patch/packages/crs_patch/main.py`, `configs.json`

**4 节点多 Agent 架构：**

```json
// configs.json — 每节点运行不同 LLM Agent 组合
{
  "node-1": ["claude_3_7", "claude_copy"],
  "node-2": ["martian_o4_mini", "multi_retrieval_o4_mini"],
  "node-3": ["vincent_gemini_2_5_pro", "aider_gemini_2_5_pro", "eraser"],
  "node-4": ["prism_o4_mini", "aider_gpt_4o", "swe_o3_mini"]
}
```

**Agent 类型：**

| Agent | 架构 | LLM |
|-------|------|-----|
| Claude Code | 直接代码生成 | Claude 3.7 |
| Multi-Retrieval | LangGraph + AST-grep retriever + Docker evaluator | o4-mini |
| Aider | 代码编辑器模式 | GPT-4o / Gemini 2.5 Pro |
| Eraser | 漏洞删除专用 | 各种 |
| Martian | Fault Localization + LLM | o4-mini |
| Prism | 多模型 ensemble | o4-mini |
| Vincent | 工作流 Agent | Gemini 2.5 Pro |
| SWE | Software Engineering Agent | o3-mini |

**三阶段验证流水线：**

```python
# patch_checker.py
Stage 1: git apply --check                    # 补丁可应用性
Stage 2: build_cr.sh (OSS-Fuzz 编译)          # 编译通过
         模式: LIBFUZZER/LIBAFL/AFL/UBSAN/MSAN...
         重试: 最多 100 次, 间隔 10s
Stage 3: run_pov.sh (POV 重放)                # 漏洞不再触发
         超时: 600s
         成功: 返回码 ≠ 202 (202=漏洞仍触发)

# patch_manager.py — 回归测试
新补丁需对所有历史 POV 重新验证
返回 patched_again_pov_ids (同时修复的 POV 列表)
```

### 2.6 微服务架构 (crs-userspace)

**关键文件：** `crs-userspace/bootstrap/run.py`

```
Bootstrap → Hello 同步 (600s) → Kafka Topic 创建 → CPConfig Protobuf 广播
    │
    ▼
Controller (编排调度)
    ├── 构建优先级: CONFIG_GEN → LIBFUZZER/LIBAFL/AFL → LIBFUZZER_SBCC → DIRECTED
    ├── 核心分配: 0-4 cores (取决于 NODE_CPU_CORES)
    │
    ├→ Harness Builder → Fuzzer Manager → Seeds Collector → Seed Ensembler
    ├→ C LLM (代码分析)
    ├→ OSV Analyzer (开源漏洞匹配)
    ├→ Directed Fuzzing (SARIF 导向)
    ├→ Crash Collector (崩溃去重)
    ├→ Harness Reachability (可达性分析)
    └→ Telemetry Logger (OTEL 聚合)
```

---

## 第三部分：UniAFL 模糊器内核深度解析

### 3.1 Rust 架构总览

**依赖 (`Cargo.toml`)：**

```toml
# 核心模糊框架
libafl = "0.13.2"
libafl_bolts = "0.13.2"

# IPC 与并发
shared_memory = "0.12"        # POSIX 共享内存
nix = "0.26"                  # POSIX 原语 (sem_open, sem_wait)
dashmap = "6.1.0"             # 无锁 HashMap
tokio = "1.41.0"              # 异步运行时

# 符号执行
z3 = { path = "../libs/z3.rs/z3" }
z3-sys = { path = "../libs/z3.rs/z3-sys" }

# 二进制分析
goblin = "0.7"                # ELF/PE/Mach-O 解析
addr2line = "0.17.0"          # DWARF 调试信息
gimli = "0.26.1"              # DWARF 解析
proc-maps = "0.4.0"          # /proc/pid/maps 解析
```

### 3.2 入口与双模式

```rust
// main.rs
#[derive(Parser)]
struct Args {
    config: String,            // JSON 配置路径
    executor_mode: bool,       // 单文件执行模式
}

// Fuzzing 模式: msa::start_fuzz_loop(&conf)
// Executor 模式: msa::execute_one_by_one(&conf)  → 从 stdin 读取文件逐个执行
```

### 3.3 MSA 编排核心 (`msa/mod.rs`)

```rust
pub fn start_fuzz_loop(config_path: &PathBuf) {
    // 1. 加载配置 (corpus_dir, pov_dir, workdir, core_ids)
    // 2. 初始化 MsaManager (共享内存)
    // 3. 创建 UniState (corpus, solutions, scheduler, observers)
    // 4. 构建 Stage 管线 (有序):
    let stages = vec![
        Box::new(TestStage),
        Box::new(InputGenStage::<MockPool>::new()),     // 基线
        Box::new(InputGenStage::<ConcolicPool>::new()), // SymCC/Z3
        Box::new(InputGenStage::<TestLangPool>::new()), // 结构化输入
        Box::new(InputGenStage::<DictPool>::new()),     // LLM 字典
        Box::new(GivenFuzzerStage),                     // 原生 libFuzzer
        Box::new(MllaStage),                            // LLM 脚本
        Box::new(SeedShareStage),                       // 种子共享
    ];
    // 5. MsaFuzzer::run() → 每核心一个 Worker 线程
}
```

### 3.4 Worker 线程模型 (`msa/fuzzer.rs`)

```rust
pub fn run_worker(&self, worker_idx: i32) {
    set_affinity(worker_idx);              // CPU 亲和性绑定
    let mut executor = create_executor();  // Harness 接口

    // 初始种子加载
    if worker_idx == 0 {
        self.add_dummy_seeds();            // Bootstrap 空种子
    }

    // 无限循环, 按 Stage 过滤器分配
    stages.filtered_perform_all_forever(
        &msa_mgr, &state, worker_idx, &executor,
        |stage| InputGenStage::stage_filter(worker_cnt, worker_idx, stage.name())
    );
}

// Worker 分配策略 (≥4 核心时):
// TestLang:  cores [0, N/4)       → 第一象限
// Concolic:  cores [N/4, N/2)     → 第二象限
// Dict:      cores [N/2, 3N/4)    → 第三象限
// 其他 Stage: 所有 cores           → 全覆盖
```

### 3.5 共享内存 IPC (`input_gen/manager.rs`)

```rust
// C FFI 接口 (libmanager.so)
extern "C" {
    fn init_mgr(name: *const i8, create: bool) -> *const c_void;
    fn alloc_input(mgr: *const c_void, worker_idx: i32) -> i32;
    fn get_input_buffer(mgr: *const c_void, idx: i32) -> *mut u8;
    fn get_cov_buffer(mgr: *const c_void, idx: i32) -> *mut CovAddr;
    fn get_crash_log(mgr: *const c_void, idx: i32) -> *mut u8;
    fn set_mode(mgr: *const c_void, worker_idx: i32, mode: i32, testlang: bool);
}

// 共享内存布局:
// [SharedData × N workers]  每个 12 字节 (status + cmd + result)
//
// POSIX 信号量 (per-worker):
//   {harness}_{name}_{worker_idx}.start  → 工作可用信号
//   {harness}_{name}_{worker_idx}.end    → 工作完成信号

// 同步协议:
// Fuzzer 端:  set_cmd(cmd) → sem_post(start) → sem_wait(end) → get_result()
// Worker 端:  sem_wait(start) → 执行工作 → set_result() → sem_post(end)
// 超时: 600 秒硬杀进程
```

**Input Buffer 管理：**

```rust
#[repr(C)]
struct InputMetadata {
    input_size: i32,
    result: i32,           // OK/Crash/Timeout/OOM
    cov_size: i32,
    crash_size: i32,
    id: i64,               // 父 corpus ID
    new_normal_feature: i64,
    fname: [c_char; 16],
}

// 自适应 batch 大小:
fn calculate_input_per_worker(ms_per_exec: u32) -> u32 {
    // 10ms/exec → 50 inputs/batch
    // 0ms/exec  → 256 inputs/batch (最大)
    if ms_per_exec == 0 { 256 }
    else { ((1000 / ms_per_exec / 2).max(1) * 2).min(256) }
}
```

### 3.6 加权语料库调度 (`msa/scheduler.rs`)

```rust
// 种子评分函数
fn calculate_score_one(match_cov: &MatchResult) -> (usize, bool) {
    const VULN_WEIGHT: usize = 8;           // 漏洞相关覆盖
    const KEY_WEIGHT: usize = 4;            // 关键函数覆盖
    const DIFF_LINE_RANGE_WEIGHT: usize = 4; // diff 行范围
    const DIFF_FILE_WEIGHT: usize = 2;      // diff 文件
    const SHOULD_BE_TAKEN_WEIGHT: usize = 1; // 应探索

    let mut score = 0;
    if match_cov.vuln.func_name { score += VULN_WEIGHT; }
    if match_cov.vuln.line      { score += VULN_WEIGHT; }
    for m in &match_cov.keys {
        score += KEY_WEIGHT * m.weight;
    }
    // ...
    (score, is_vuln)
}

// 选择策略:
// Normal stage: 25% interesting corpus, 75% 加权 corpus
// TestLang stage: 90% testlang corpus, 10% fallback
// 选择: O(log n) 二分查找累积权重
```

### 3.7 MLLA LLM 引导变异 (`msa/stage/mlla.rs`)

```rust
struct MllaScript {
    name: String,              // "mlla.gen.{md5}" 或 "mlla.mut.{md5}"
    path: String,              // Python 脚本路径
    src_func: Option<LinePos>, // 源函数覆盖位置
    dst_func: Option<LinePos>, // 目标函数覆盖位置
}

// 脚本加载: .py + .json (元数据) + .done (完成标记)
// MD5 哈希去重, rename 后删除 .done

// Generator 选择 (75% 按覆盖率, 25% 随机):
fn pick_generator_by_acc_cov(&self, state, rand) -> Option<&MllaScript> {
    // 保留 src_func 尚未被累积覆盖的 generator
    self.generator.iter().filter(|gen| {
        match state.acc_cov_in_src_range(gen.src_func) {
            Some(true) => false,  // 已覆盖 → 跳过
            _ => true,
        }
    }).random()
}

// 执行: timeout 10s python run_mlla_gen.py <script> <num_blobs>
// 环境变量: CUR_WORKER, HARNESS_NAME, MANAGER_LIB_PATH
```

### 3.8 Concolic 执行 (`concolic/`)

```rust
pub trait ConcolicExecutor<T, S: SingleStepSession> {
    fn execute(&mut self, input_id: InputID, input: &[u8]) -> Result<T>;
    fn execute_single_step(&mut self, input_id: InputID, input: &[u8]) -> Result<S>;
    fn single_step(&mut self, session: &mut S) -> Result<SingleStepResult<T>>;
}

// 两种实现:
// SymCCExecutor:   源码级符号执行 (编译期插桩)
// SymQEMUExecutor: 二进制级符号执行 (QEMU 模拟)
// 后端: Z3 SMT 求解器
// 超时: executor_timeout_ms = 30000 (30s)
```

---

## 第四部分：静态分析工具链深度解析

### 4.1 CodeQL

**角色：** 主分析器，支持 C/C++/Java/JVM

```python
# codeql.py
class CodeQLReachabilityAnalyser(BaseReachabilityAnalyser):
    # 查询类型:
    # get_call_graph()                    → 完整程序调用图
    # get_call_graph_conditional()        → 条件调用图
    # get_call_graph_only_from_harnesses() → 从 harness 出发 (大型程序 fallback)
    # get_all_functions()                 → 所有可调用函数
    # get_direct_call_graph()             → 仅直接调用

    # 执行: QL 查询, 超时 1200 秒
    # 输出: STRONG/WEAK 边的调用图
```

### 4.2 SVF (Static Value-Flow Analysis)

**角色：** C/C++ 辅助分析器, 指针分析

```python
# svf.py
class SVFReachabilityAnalyser(BaseReachabilityAnalyser):
    # 8 种指针分析模式:
    modes = ["ander", "nander", "sander", "sfrander",
             "steens", "fspta", "vfspta", "type"]

    # 输入: DOT 图文件 call_graph_{mode}_{harness}.dot
    # 并行: 4 workers 处理多 harness
    # 输出: 合并的调用图 → 补充 CodeQL 结果
```

### 4.3 Sootup

**角色：** Java/JVM 辅助分析器

```python
# sootup.py
class SootupReachabilityAnalyser(BaseReachabilityAnalyser):
    # 3 大类:
    # CHA (Class Hierarchy Analysis)
    # RTA (Rapid Type Analysis)
    # PTA (Points-To Analysis) → 18 种算法变体:
    #   object-sensitive, type-sensitive, hybrid,
    #   zipper variants, select-heuristic variants

    # 执行: java -jar sootup-reachability.jar
    # 输入: cpmeta*.json (class paths, source paths)
```

### 4.4 Joern

**角色：** 代码属性图 (CPG) 分析

```python
# joern.py
class JoernReachabilityAnalyser:
    # 查询模式:
    # line-reachableBy   → 行级可达性
    # func-reachableBy   → 函数级可达性
    # callgraph          → 调用图提取
    # backward           → 反向数据流分析

    # 用于: LLM POC 生成 (blobgen), 精细可达性判断
```

### 4.5 Tracer

**角色：** 运行时动态调用追踪

```
tracer-c (Docker: sarif-tracer-c):
    输入: corpus/{harness_name}/ 下的 seedfiles
    执行: 对每个 seed 运行插桩二进制
    输出: .edges JSON (函数调用关系)

tracer-java (Docker: sarif-tracer-java):
    类似, JVM 专用

→ analyser.py 每 180 秒读取 .edges, batch 更新调用图
→ 运行时数据补充静态分析盲区
```

### 4.6 工具协同流程

```
                    CodeQL DB
                       │
                       ▼
              CodeQL 调用图 (主图)
                  ╱        ╲
              STRONG       WEAK
               边           边
                  ╲        ╱
                   合并到
                   ┌─┴─┐
              ┌────┤主图├────┐
              │    └────┘    │
              ▼              ▼
    SVF DOT 图 (C++)    Sootup 调用图 (Java)
    8 模式 × N harness  CHA + RTA + 18 PTA
              │              │
              └──── 合并 ────┘
                     │
                     ▼
           统一 NetworkX DiGraph
                     │
              ┌──────┼──────┐
              ▼      ▼      ▼
           Tracer  Joern   LLM
           .edges  CPG查询  匹配
           (180s)          Agent
              │      │      │
              └──合并─┘      │
                     │       │
                     ▼       ▼
            可达性分析结果  语义匹配结果
                     │       │
                     └── SARIF 报告 + 置信度 ──→ VAPI 广播
```

---

## 第五部分：P4 框架源码级追踪

### 5.1 文档模型 (`p4/__init__.py:33-118`)

```python
# BaseDocument — 带注释标记的文档基类
class BaseDocument(BaseModel):
    value: str

    def annotated(self, patterns: list[BasePattern], opening_tag, closing_tag):
        """用 <cc>...</cc> 标签包裹 Pattern 匹配的代码片段"""
        # 1. 收集所有 Fragment 并按位置排序
        fragments = sorted([f for p in patterns for f in p.match(self.value)],
                          key=lambda x: x.start_position)
        # 2. 贪心过滤重叠 (O(n log n))
        filtered = [f for f in fragments if f.start_position >= current_end]
        # 3. 插入标签 (跟踪偏移量)
        # 4. 去重相邻标签
        return self.__class__(value=annotated_value)

# FileDocument — 可编辑的源码文件
class FileDocument(BaseDocument):
    relative_path: Path          # 相对于项目根
    source_directory: Path       # 项目根目录

    def as_markdown(self):
        return f"### {self.relative_path}\n\n```\n{self.value.strip()}\n```"

# TextDocument — 不可编辑文本 (如 crash log)
class TextDocument(BaseDocument):
    def as_markdown(self):
        return f"## (Uneditable)\n\n```\n{self.value.strip()}\n```"

Document = TextDocument | FileDocument
Symbol = NewType("Symbol", str)   # 类型安全的符号名包装
```

### 5.2 符号解析工具链 (`p4/__init__.py:126-226`)

```python
# GNU Global 符号定位
def _symbol_locations(name: str, context: GlobalCommandContext):
    stdout = subprocess.check_output(
        [context["global_executable"], "-x", name],
        cwd=context["source_directory"]
    ).decode("utf-8", errors="ignore")

    for match in re.finditer(r"(\w+)\s+(\d+)\s+([\w\/.-]+)\s+", stdout):
        relative_path = Path(match.group(3))
        row = int(match.group(2)) - 1  # 转为 0-indexed

        # 过滤 fuzzer 路径 (防止解析 harness 而非目标代码)
        if any(d in relative_path.parts
               for d in ["aflplusplus", "libfuzzer", "fuzztest", "fuzz"]):
            continue
        yield (relative_path, row)

# C++ 函数定义提取工具
class CppFunctionDefinitionTool(BaseTool):
    def run(self, x: Symbol, context: GlobalCommandContext) -> set[Document]:
        func_name = x.split(".")[-1].split("(")[0].split("<")[0].split("::")[-1]
        result = set()
        for path, row in _symbol_locations(func_name, context):
            text = (context["source_directory"] / path).read_text()
            root = SgRoot(text, "cpp").root()  # ast-grep C++ 解析
            for node in root.find_all(kind="function_definition"):
                if node.range().start.line <= row <= node.range().end.line:
                    result.add(FileDocument(value=node.text(),
                                           relative_path=path,
                                           source_directory=context["source_directory"]))
        return result

# 类似: CppTypeDefinitionTool → kind="type_definition"
# 类似: JavaMethodDeclarationTool → SgRoot(text, "java"), kind="method_declaration"
```

### 5.3 AIxCC 环境 (`p4/__init__.py:229-287`)

```python
class AIxCCEnvironment[Context](BaseEnvironment[set[Document], set[Symbol], Context]):
    def __init__(self, tools: list[BaseTool], episode_length: int,
                 scope_builder: Callable[[Context], Scope]):
        self._tools = tools
        self._episode_length = episode_length
        self._scope_builder = scope_builder

    def reset(self, context: Context) -> set[Document]:
        """从 crash log 提取栈帧作为初始观测"""
        crash_log = self._scope_builder(context)["initial_crash_log"]
        frames = re.findall(r"^    #\d+ 0x[0-9a-f]+ in .*$",
                           crash_log, re.MULTILINE)
        if frames:
            return {TextDocument(value="\n".join(frames))}
        return {TextDocument(value=crash_log)}

    def _step(self, action: set[Symbol], observation: set[Document], context):
        """并行工具执行: 每个 (symbol, tool) 组合并行运行"""
        scope = self._scope_builder(context)
        documents = {
            document
            for documents in Parallel(n_jobs=-1, backend="threading")(
                delayed(tool.run_or_none)(symbol, scope)
                for symbol, tool in product(action, self._tools)
            )
            if documents is not None
            for document in documents
        } | observation  # 累积: 新文档 ∪ 已有观测

        terminated = self._current_step >= self._episode_length
        return documents, terminated, False
```

**关键设计：**
- `product(action, self._tools)` — 笛卡尔积: 每个符号尝试所有工具
- `tool.run_or_none()` — 失败静默返回 None, 不中断 pipeline
- `| observation` — 观测累积, 环境有"记忆"

### 5.4 Eraser 策略 (`p4/__init__.py:368-449`)

```python
class BaseEraserPolicy(BaseChatPolicy[set[Document], set[Symbol]]):
    def prompt_from_observation(self, observation, previous_observation):
        # 1. 用 Pattern 注释文档: <cc>vulnerable_function</cc>
        annotated = {doc.annotated(self._patterns, "<cc>", "</cc>")
                     for doc in observation}
        # 2. 构建 Markdown prompt
        return [{"role": "user",
                 "content": f"# Instruction\n{self._system_message}\n---\n"
                           f"# Contents\n" +
                           "\n\n".join(doc.as_markdown() for doc in annotated)}]

    def action_from_completion(self, completion, prompt):
        # 从 "## Relevant Symbols" 后提取 `backtick` 中的符号
        values = re.finditer(r"\`([^\`]+)\`",
                            completion["content"].split("## Relevant Symbols")[-1])
        # 反幻觉验证: 确认符号存在于原始 prompt 中
        return {Symbol(v) for v in values
                if f"<cc>{v}</cc>" in prompt[-1]["content"]}
```

### 5.5 虚拟文件系统 (`p4/__init__.py:452-518`)

```python
class _VirtualFileSystem:
    """内存覆盖层: 安全代码修改, 不写磁盘"""
    def __init__(self, source_directory: Path):
        self._overlay: dict[Path, str] = {}   # relative_path → 修改内容

    def write_text(self, path, data):
        self._overlay[self.resolve(path)] = data

    def read_text(self, path):
        rp = self.resolve(path)
        if rp in self._overlay: return self._overlay[rp]  # 修改版
        return (self._source_directory / rp).read_text()   # 原始版

    def resolve(self, path):
        """路径安全: 防止目录遍历攻击"""
        if path.is_absolute():
            if not path.is_relative_to(self._source_directory):
                raise ValueError("路径不在源码目录内")
            return path.relative_to(self._source_directory)
        return path

    @property
    def diff(self) -> str | None:
        """生成 git 兼容的 unified diff"""
        return "".join(difflib.unified_diff(before, after,
                       fromfile=f"a/{p}", tofile=f"b/{p}")
                       for p, content in self._overlay.items())
```

### 5.6 ReAct Agent (`p4/__init__.py:521-631`)

```python
def generate_patch_using_langchain(documents, source_directory, chat_model):
    fs = _VirtualFileSystem(source_directory)

    @tool
    def target(): """返回待修复的目标代码"""

    @tool
    def context(): """返回参考上下文 (crash log 等)"""

    @tool
    def cat(file_path: str): """查看文件 (反映 VFS 编辑)"""

    @tool
    def edit(file_path: str, search: str, replace: str):
        """替换文件内容 — 强制唯一性"""
        before = fs.read_text(path)
        if search not in before: raise ValueError("搜索文本未找到")
        if before.count(search) > 1: raise ValueError("搜索文本不唯一")
        fs.write_text(path, before.replace(search, replace))

    @tool
    def explain(reasoning: str): """LLM 解释修复推理"""

    agent = create_react_agent(model=chat_model,
                               tools=[target, context, cat, edit, explain])
    agent.invoke({
        "messages": [HumanMessage(
            "Role: Security Expert with Full Discretionary Power\n"
            "Mission: Audit every supplied source file...\n"
            "Procedure: 1) target → 2) context → 3) explain → 4) edit → 5) cat → repeat"
        )]
    }, {"recursion_limit": 128})  # 最多 128 次工具调用

    return fs.relative_patches, fs.diff
```

### 5.7 LoRA 动态适配 (`p4/__init__.py:634-739`)

```python
class BaseClient[T](Protocol):
    """动态 LoRA 适配客户端: 根据漏洞上下文微调 LLM"""

    @contextmanager
    def enabled(self, id, crash_log, patterns, tools, context):
        # 1. 从 crash log 提取符号
        fragments = {f for p in patterns for f in p.match(crash_log)}
        symbols = {Symbol(f.value) for f in fragments}

        # 2. 解析符号到源码
        documents = {d for s in symbols for t in tools
                     for d in (t.run_or_none(s, context) or set())}
        text = "\n".join(d.value for d in documents)

        # 3. 训练 LoRA 适配器 (HTTP API)
        adapter_path = self.adapt(id=id, text=text,
            block_size=256, learning_rate=1e-8,  # 极小学习率防遗忘
            num_train_epochs=64, lora_rank=16, lora_alpha=16, lora_dropout=0.1)

        # 4. 加载到 vLLM → POST /load_lora_adapter
        self.load_lora_adapter(lora_name=id, lora_path=adapter_path)

        try:
            yield self._as(id=id)  # 返回适配后的客户端
        finally:
            self.unload_lora_adapter(lora_name=id)  # 清理
```

### 5.8 Pattern 实现全览

| Pattern | 语言 | AST 节点 / 正则 | 用途 |
|---------|------|------------------|------|
| `CppCallPattern` | C++ | `call_expression` | 提取函数调用 |
| `CppTypeIdentifierPattern` | C++ | `type_identifier` | 提取类型引用 |
| `JavaInvocationPattern` | Java | `method_invocation` | 提取方法调用 |
| `JazzerFunctionSignaturePattern` | Java | `\tat (.*)\(` | Jazzer 栈帧签名 |
| `SanitizerFunctionSignaturePattern` | C++ | `#\d+ 0x[a-f0-9]+ in (.+) \/` | Sanitizer 栈帧签名 |

**短路优化：** 每个 regex Pattern 先检查标记字符 (`"    #"`, `"\tat "`) 是否存在, 避免对非栈帧文本执行正则。

---

## 第六部分：AI 强化学习训练 Pipeline

### 6.1 训练框架依赖

```toml
# python-trainer/pyproject.toml
trl[grpo]            # HuggingFace TRL (GRPO 实现)
vllm >= 0.8.5.post1  # 快速推理引擎
peft >= 0.15.2       # LoRA/QLoRA 参数高效微调
liger-kernel >= 0.5.8 # 优化 GPU 内核
wandb >= 0.19.9      # 实验追踪
scikit-learn >= 1.6.1 # ML 工具
```

### 6.2 GRPO 训练器 (`trainer/grpo/actors.py`)

```python
class GrpoTrainer[Observation, Action, Context](GRPOTrainer):
    """扩展 TRL GRPO: 支持多步 episode 环境交互"""

    def _generate_and_score_completions(self, inputs):
        # 1. 构建 Context
        contexts = self.contexts_builder(inputs, self)

        # 2. 重置环境 → 初始观测
        observations = [self.environment.reset(ctx) for ctx in contexts]
        histories = [[] for _ in contexts]  # 对话历史

        # 3. 迭代循环
        while not all_done:
            # 3a. Policy → Prompt
            prompts = [policy.prompt_from_observation(obs, prev_obs)
                      for obs, prev_obs in zip(observations, prev_observations)]
            # 追加到对话历史
            for h, p in zip(histories, prompts): h.extend(p)

            # 3b. TRL 父类生成 token
            completions = super()._generate_and_score_completions(histories)

            # 3c. 解析 Action
            actions = [policy.action_from_completion(c, p)
                      for c, p in zip(completions, prompts)]

            # 3d. 并行环境执行 (joblib threading)
            results = Parallel(n_jobs=-1, backend="threading")(
                delayed(env.step)(action, obs, ctx)
                for action, obs, ctx in zip(actions, observations, contexts)
            )

            # 3e. 收集奖励
            for i, (new_obs, terminated, truncated) in enumerate(results):
                observations[i] = new_obs
                rewards[i].append(env.compute_rewards(...))

        # 4. 奖励处理
        # 每函数平均: mean(non-None rewards)
        # 加权组合: Σ(reward_i × weight_i)
        # 优势: (reward - mean) / (std + 1e-4)

        # 5. Checkpointing
        if compilable_reward > last_best: save_model()
        if compilable_reward == 1.0 and step > 16: stop()
        if combined_reward > 0.8: stop()
```

### 6.3 课程学习 (`trainer/curriculum/actors.py`)

```python
class CurriculumTrainer:
    def train(self):
        for epoch in range(self._epochs):
            for index, data in enumerate(self._scheduler.as_dataset()):
                # [可选] 适应阶段: 在窄分布上微调
                if self._adaptation:
                    train_ds, eval_ds = self._adaptation_dataset_builder(data)
                    self._adaptation_trainer.train_dataset = train_ds
                    self._adaptation_trainer.train()
                    torch.cuda.empty_cache()

                # 主训练阶段: 重复 N 步
                dataset = Dataset.from_list([data] * self._steps(index))
                self._main_trainer.train_dataset = dataset
                self._main_trainer.train()
```

### 6.4 Docker 沙箱 (`python-oss-fuzz/`)

```python
# sandbox/actors.py: SandboxManager
class SandboxManager:
    def register(self, project, context):
        """首次注册: 编译 + 生成 gtags + 初始 crash 重现"""
        with temporary_container(builder_image) as builder:
            builder.exec_run(["compile"], environment={
                "CFLAGS": "$CFLAGS -O0",   # 禁优化 (保留符号)
                "PATH": "/ccache/bin:$PATH"  # ccache 加速
            })
            load_directory_from_container(builder, root_dir, "/out")
            load_directory_from_container(builder, root_dir, "/ccache/cache")

        # 生成 GNU Global 索引
        subprocess.run(["gtags"], cwd=source_directory)

        # 验证 crash 可重现
        sandbox = Sandbox(root_dir, builder_image, runner_image, context)
        sandbox.reproduce()

    def use(self, context):
        """使用: 复制缓存 → 临时目录 → 返回 Sandbox"""
        temp_dir = shutil.copytree(self.cache_directory, tempfile.mkdtemp())
        return Sandbox(temp_dir, ...)

# sandbox/models.py: Sandbox
class Sandbox(BaseSandbox):
    def build(self):
        """在 Builder 容器中编译 (挂载 /src, /ccache, /out)"""

    def reproduce(self):
        """在 Runner 容器中重现 (挂载 /out, /testcase)"""
        # 执行: reproduce {harness} -runs=100
        # Runner: ghcr.io/aixcc-finals/base-runner:v1.1.0
```

### 6.5 漏洞元数据 (`python-oss-fuzz-vulnerability/`)

```
project/vulnerabilities/
├── vuln_1/
│   ├── index.json     ← { name, harness, sanitizer, error_token, base_commit }
│   ├── crash.log      ← Sanitizer 崩溃输出
│   └── proof.bin      ← 触发漏洞的二进制输入
│
└── vuln_2/...

源码定位: sources/{base_commit}/src/{project_name}/
```

### 6.6 LLM 抽象层 (`python-llm/`)

```python
# llm/api/actors.py
class LlmApiManager:
    def __init__(self, model: str, api_key: Callable, base_url: Callable):
        self._model = model
        self._api_key = api_key    # 惰性求值 (运行时加载)
        self._base_url = base_url

    @staticmethod
    def from_dotenv(model, key_of_api_key="LITELLM_API_KEY",
                    key_of_base_url="LITELLM_API_BASE"):
        """从 .env 文件加载配置"""

    def langchain_chat_model(self):
        return ChatLiteLLM(model=self._model,
                          api_key=self._api_key(),
                          api_base=self._base_url())
```

---

## 第七部分：Fuzzing Harness 工程模式

### 7.1 构建系统 (`build.sh`, 189 行)

```bash
# Sanitizer 特殊处理
if [ "$SANITIZER" = undefined ]; then
    export CFLAGS="$CFLAGS -fno-sanitize=unsigned-integer-overflow"
fi

# Configure binutils (禁用不需要的组件)
./configure --disable-gdb --disable-gdbserver --disable-libbacktrace \
            --disable-gas --disable-ld --enable-targets=all

# 多架构 Fuzzer 编译 (ARM, MIPS, i386, x86_64...)
LINK_LIBS="-Wl,--start-group ${LIBS} -Wl,--end-group"
for arch in bfd_arch_arm bfd_arch_mips bfd_arch_i386 ...; do
    $CC $CFLAGS -D${arch^^} fuzz_disas_ext.c $LINK_LIBS -o $OUT/fuzz_disas_ext-${arch}
done
```

### 7.2 文件型 Fuzzer 模式

```c
// fuzz_bfd.c
int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size) {
    bfd_init();
    char *tmpf = bufferToFile(filename, Data, Size);  // 内存 → 临时文件
    bfd *abfd = bfd_openr(tmpf, target);
    bfd_check_format(abfd, bfd_archive);
    bfd_close(abfd);
    remove(tmpf);
    return 0;
}
```

### 7.3 全局状态隔离 (关键技术)

```c
// fuzz_objdump.c — 重置 15+ 全局变量
static void objdump_reset() {
    dump_section_contents = true;
    dump_section_headers = true;
    dump_private_headers = true;
    dump_ar_hdrs = true;
    with_source_code = false;
    dump_dwarf_section_info = true;
    dwarf_select_sections_all();
    #ifdef OBJDUMP_SAFE
    disassemble = true;         // 安全模式: 避免 bfd_fatal → exit()
    dump_reloc_info = true;
    #endif
}

int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size) {
    bufferToFile(filename, Data, Size);
    objdump_reset();            // ★ 关键: 每次输入前重置全局状态
    display_file(filename);
    unlink(filename);
    return 0;
}
```

### 7.4 架构过滤

```c
// fuzz_readelf.c
#ifdef READELF_TARGETED
check_architecture(filename, READELF_TARGETED);  // 仅分析目标架构
#endif
// 启用 13+ 分析标志: do_syms, do_reloc, do_unwind, do_dynamic, ...
```

### 7.5 Harness 工程模式总结

| 模式 | 代码 | 目的 |
|------|------|------|
| 临时文件 | `bufferToFile()` + `unlink()` | 内存缓冲区 → 文件输入 |
| 全局状态重置 | `objdump_reset()` | 隔离多次模糊测试输入 |
| 架构过滤 | `#ifdef READELF_TARGETED` | 减少无效输入噪音 |
| 安全模式宏 | `#ifdef OBJDUMP_SAFE` | 避免 `exit()` 杀死 Fuzzer |
| 函数重定向 | `-Dmain=old_main` | 嵌入 Fuzzing 循环 |
| 多架构编译 | `for arch in ...` | 每架构独立 Fuzzer 二进制 |

---

## 第八部分：基础设施与部署架构

### 8.1 Kubernetes 配置

```yaml
# k8s/base/crs-webservice/kustomization.yaml
namespace: crs-webservice
resources: [account.yaml, deployment.yaml, secrets.yaml,
            service.yaml, ingress.yaml, opentelemetry.yaml]

# RBAC: cluster-admin (完全控制, 用于动态创建节点池)
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
roleRef:
  kind: ClusterRole
  name: cluster-admin
subjects:
  - kind: ServiceAccount
    name: k8s-full-control
    namespace: crs-webservice

# 服务暴露:
# crs-webapp: 80 (HTTP) + 6379 (Redis)
# p3:         8000-8001
# otel:       4317 (gRPC)
```

### 8.2 Terraform (GCP)

```hcl
# GKE 私有集群
resource "google_container_cluster" "primary" {
    name = "clusterfuzz-cronjobs-gke"
    private_cluster_config {
        enable_private_endpoint = false
        enable_private_nodes    = true
        master_ipv4_cidr_block  = "172.16.0.32/28"
    }
}

# Redis 实例
resource "google_redis_instance" "memorystore_redis_instance" {
    tier           = "BASIC"
    memory_size_gb = 1
    redis_version  = "REDIS_6_X"
    lifecycle { prevent_destroy = true }
}

# Cloud NAT (出站网络)
resource "google_compute_router_nat" "nat_config" {
    source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
    nat_ip_allocate_option             = "AUTO_ONLY"
}
```

### 8.3 Tailscale 网络

```yaml
# k8s/base/tailscale-connections/
# 通过 Tailscale mesh 连接到竞赛服务器
apiVersion: v1
kind: Service
metadata:
  name: competition-echo-egress
  annotations:
    tailscale.com/tailnet-fqdn: "echo.tail7e9b4c.ts.net"
spec:
  type: ExternalName
```

### 8.4 OpenTelemetry 配置

```yaml
# OTEL Collector Sidecar 配置
receivers:
  otlp:
    protocols:
      grpc: { endpoint: 0.0.0.0:4317 }
      http: { endpoint: 0.0.0.0:4318 }

processors:
  resource:
    attributes:
      - key: k8s.pod.name
        value: ${K8S_POD_NAME}
        action: upsert
  memory_limiter:
    limit_percentage: 75
    spike_limit_percentage: 25
  batch:
    send_batch_size: 1000
    timeout: 1s

exporters:
  otlp:
    endpoint: ${AIXCC_OTEL_EXPORTER_OTLP_ENDPOINT}
    retry_on_failure: { max_elapsed_time: 300s }
    sending_queue: { queue_size: 5000 }

service:
  pipelines:
    logs:   { receivers: [otlp], processors: [memory_limiter, resource, batch], exporters: [otlp] }
    traces: { receivers: [otlp], processors: [memory_limiter, resource, batch], exporters: [otlp] }
```

**Python OTEL Handler (`libCRS/otel.py`)：**

```python
class OpenTelemetryHandler(logging.Handler):
    OTEL_TIME_WINDOW = 60  # 60 秒 span 生命周期

    ACTION_CATEGORIES = [
        "static_analysis", "dynamic_analysis", "fuzzing",
        "program_analysis", "building", "input_generation",
        "patch_generation", "testing", "scoring_submission"
    ]

    def emit(self, record):
        # 60 秒窗口: 超时则关闭旧 span, 创建新 span
        if time.time() - self.span_created > 60:
            self.current_span.end()
            self.current_span = self.tracer.start_span(self.service_name)
            # 设置属性: crs.action.category, crs.action.name, crs.action.harness

        # 日志 → span event
        self.current_span.add_event(name="log", attributes=record.__dict__)

    # loguru 桥接: loguru → logging.LogRecord → OTEL span event
```

### 8.5 Docker Extension 工具库

```python
# container/context_managers.py
@contextmanager
def temporary_container(image):
    """创建临时容器, 自动清理"""
    container = client.containers.run(
        command=["tail", "-f", "/dev/null"],
        image=image, detach=True,
        shm_size="2g"  # 防 OOM
    )
    try: yield container
    finally: container.remove(force=True)

@contextmanager
def file_injected_container(container, content, container_path):
    """原子文件注入: TAR 序列化 → put_archive → 自动回滚"""

# container/functions.py
def load_directory_from_container(container, root_dir, container_path):
    """从容器提取目录: get_archive → TAR 解包"""

def overwrite_directory_in_container(container, source_dir, container_path):
    """原子目录替换: TAR 打包 → put_archive"""
```

---

## 第九部分：可复用 Pipeline 提取

| Pipeline | 用途 | 核心机制 | 关键文件 | 相关工具 |
|----------|------|----------|----------|----------|
| **Ensemble Fuzzing** | 多策略并行漏洞发现 | MSA Stage 序列 + 共享内存 IPC + 加权调度 | `uniafl/src/msa/` | LibAFL 0.13.2, POSIX shmem, Z3 |
| **LLM-Guided Fuzzing** | LLM 生成/变异输入 | MLLA 脚本 + DictGen 常量提取 + 覆盖率驱动选择 | `msa/stage/mlla.rs`, `input_gen/dict/` | LiteLLM, Python FFI |
| **Static+Dynamic 融合** | 多工具调用图分析 | CodeQL+SVF+Sootup+Joern → NetworkX → Tracer 动态更新 | `crs_sarif/services/analyser.py` | CodeQL, Joern CPG, SVF, Sootup |
| **RL 训练漏洞修复** | GRPO 强化学习 | 多步 episode + 加权奖励 + 课程学习 + LoRA 适配 | `trainer/grpo/actors.py` | TRL, vLLM, PEFT, wandb |
| **自动补丁生成** | 多 LLM 并行补丁 | 4 节点 × 多 Agent + 三阶段验证 + 回归测试 | `crs_patch/` | Claude/GPT-4o/o3/Gemini, AST-grep |
| **ReAct Agent 修复** | LLM 交互式代码修复 | VFS 覆盖层 + 5 工具 + 128 步递归限制 | `p4/__init__.py:521-631` | LangGraph, ast-grep |
| **Docker 沙箱** | 隔离编译/测试 | 不可变缓存 + 临时副本 + ccache + TAR 原子操作 | `python-oss-fuzz/`, `python-docker-extension/` | Docker SDK, ccache |
| **Harness 工程** | Fuzzing target 模板 | 全局状态隔离 + 架构过滤 + 安全宏 | `pcb/projects/binutils/fuzz_*.c` | ASAN/UBSAN/MSAN |
| **P4 协议栈** | 通用 RL 漏洞修复 | Pattern→Policy→Environment→Sandbox 四层解耦 | `p4_core/` | ast-grep, GNU Global |
| **LoRA 动态适配** | 漏洞上下文微调 | 符号提取→源码收集→LoRA 训练→vLLM 加载 | `p4/__init__.py:634-739` | vLLM, PEFT |

---

## 第十部分：关键设计模式总结

### 1. 协议驱动架构 (P4 Protocol)

```python
# 四层通过 Python Protocol (PEP 544) 完全解耦
BasePattern.match(str) → set[Fragment]           # 7 行
BaseChatPolicy.act(obs) → action                 # 31 行
BaseEnvironment.step/reset                       # 复杂但通用
BaseSandbox.build/reproduce                      # 17 行

# 任何一层可独立替换:
# Pattern: C++ → Solidity (改一个 ast-grep 语言字符串)
# Sandbox: Docker → Foundry (改 build/reproduce 命令)
# Policy:  "Security Expert" → "Smart Contract Auditor" (改 prompt)
```

### 2. 预算感知调度

```
总 vCPU 预算 = QUOTA_PER_CP
├── 按优先级分配: CP-Manager > Patch > Multilang > Userspace
├── 节点规格降级: 128 → 96 → 64 → 48 → 32 → 16 → 8 → 4
├── LLM token 预算: 每节点独立 LLM key
└── 运行时长估算: deadline - now → running_hours
```

### 3. Redis 状态机

```
Task:   pending → running → succeeded/failed/errored/canceled
POV:    submitted → pending → accepted/rejected
Patch:  submitted → pending → passed/failed/errored/duplicated
SARIF:  submitted → pending → matched/unmatched/failed

防重入: launched-{TASK_ID} key
```

### 4. 多模型多策略融合

```
Fuzzing 层: 6 种输入生成策略 + 跨 CRS 种子共享
Patch 层:   4 节点 × 多 Agent (8+ 种) × 多 LLM (5+ 种)
SARIF 层:   CodeQL + SVF + Sootup + Joern + Tracer + LLM
RL 训练层:  多奖励函数加权 + 课程学习渐进
```

### 5. 验证优先

```
POV:   Sanitizer 触发 → Crash log 确认 → 可达性 → 二次验证
Patch: git apply → 编译 → POV 不触发 → 全量 POV 回归
SARIF: 格式校验 → 位置验证 → 调用图可达 → LLM 语义匹配
LLM:   反幻觉 (符号必须存在于原始 prompt) → edit 唯一性约束
```

### 6. 容错弹性

```python
# BaseRunnable.run_or_none() — 整个系统的弹性骨架
# 10 个工具并行, 3 个失败, 7 个成功 → pipeline 继续
# 无需 try/except, 无需 fallback

# LoRA 加载失败 → yield None → 退化到基础模型
# Tracer 超时 → 跳过动态更新 → 仅用静态调用图
# MLLA 脚本超时 (10s) → 跳过该脚本 → 下一个
```

### 7. 零拷贝 IPC

```rust
// POSIX 共享内存: 直接内存映射, 无序列化开销
let buffer = get_input_buffer(mgr_ptr, idx);  // 直接指针
// POSIX 信号量: 原子阻塞, 无 busy-wait
sem_wait(start); /* 执行 */ sem_post(end);
// 超时监控: 600s 硬杀 (防止死锁)
```

---

## 附录：工具链与依赖清单

### A. 静态分析工具

| 工具 | 语言支持 | 输入 | 输出 | 用途 |
|------|----------|------|------|------|
| **CodeQL** | C/C++/Java | 源码 → CodeQL DB | 调用图 (QL 查询) | 主分析, 1200s 超时 |
| **Joern** | C/C++ | 源码 → CPG | 可达性/数据流 (Scala 查询) | 细粒度分析, POC 生成 |
| **SVF** | C/C++ | LLVM IR → DOT | 指针调用图 (8 模式) | 间接调用分析 |
| **Sootup** | Java/JVM | Class path | 方法可达性 (18 PTA 变体) | 多态调度分析 |
| **Tracer** | C/C++/Java | Corpus seeds | .edges JSON | 运行时调用追踪 |
| **GNU Global** | C/C++/Java | 源码 → GTAGS | 符号位置 | P4 符号解析 |
| **ast-grep** | C++/Java/Solidity | 源码 | AST 节点 | Pattern 匹配, 函数提取 |

### B. 动态分析工具

| 工具 | 层级 | 机制 | 用途 |
|------|------|------|------|
| **UniAFL** | 应用级 | LibAFL + MSA 多策略 | 主 Fuzzer |
| **SymCC** | 源码级 | 编译期符号插桩 | Concolic 执行 |
| **SymQEMU** | 二进制级 | QEMU 模拟 + 符号追踪 | 无源码 Concolic |
| **Z3** | SMT 求解 | 约束满足 | 路径约束求解 |
| **ASAN** | 运行时 | 影子内存 | 越界/释放后使用检测 |
| **UBSAN** | 运行时 | 编译器检查 | 未定义行为检测 |
| **MSAN** | 运行时 | 影子内存 | 未初始化内存读取 |

### C. LLM 与 AI 工具

| 工具 | 版本 | 用途 |
|------|------|------|
| **LiteLLM** | 1.72.4 | 统一 LLM API 接口 |
| **LangGraph** | - | ReAct Agent + 状态机工作流 |
| **LangChain** | - | 工具集成 + Chat 模型 |
| **TRL** | grpo | GRPO 强化学习训练 |
| **vLLM** | ≥0.8.5 | 快速推理 + LoRA 热加载 |
| **PEFT** | ≥0.15.2 | LoRA 参数高效微调 |
| **wandb** | ≥0.19.9 | 实验追踪与可视化 |
| **liger-kernel** | ≥0.5.8 | 优化 GPU 内核 |

### D. 基础设施工具

| 工具 | 用途 |
|------|------|
| **Docker** | 沙箱隔离 (Builder + Runner 双容器) |
| **Kubernetes AKS** | 动态节点池 + Pod 编排 |
| **Kustomize** | K8s 配置管理 |
| **Terraform** | GCP 基础设施即代码 |
| **Redis** | 状态机 + 消息暂存 |
| **Kafka** | 微服务消息总线 (Protobuf) |
| **Tailscale** | 安全网络出口 (mesh VPN) |
| **OpenTelemetry** | 分布式追踪 (OTLP gRPC) |
| **ccache** | 编译缓存加速 |
| **Filebeat** | 日志收集 |
