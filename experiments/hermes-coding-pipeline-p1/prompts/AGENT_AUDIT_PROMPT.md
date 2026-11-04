# P1 independent audit prompt — send verbatim to an external coding agent

你现在是 **Hermes Coding Pipeline P1 的独立审计Agent**。本次任务是**只读代码审计、真实可复现测试、提交审计报告**，**不是研发整改**。你应当独立审阅源代码，不依赖开发者的自评、测试口头结论或README声称。不要修改P1业务代码，也不要直接触碰21bao上的Hermes/Opencode/Codex实际配置、真实生产目录、5bao/9bao/rusty或P0 A2A盲审作业。允许在独立克隆或隔离临时目录中运行不调用付费模型的单元测试、静态检查和Git验证。

## 审计目标

GitHub仓库：`k176060444-lgtm/hermes-agent`

待审分支：`feature/p1-coding-pipeline-20261104`

审计源代码根目录：`experiments/hermes-coding-pipeline-p1/`

**必须首先记录你实际审计的Git commit SHA**，并在报告中列出；不要自动审计正在变动的分支HEAD而不固定SHA。

独立报告提交位置（同一分支，不修改旧报告）：

- 首轮：`experiments/hermes-coding-pipeline-p1/audit_evidence/P1/round-001/`
- 第N轮：`experiments/hermes-coding-pipeline-p1/audit_evidence/P1/round-NNN/`

每次审计需提交：

1. `AUDIT_REPORT.md`：完整独立结论，是否PASS/FAIL，有序发现清单与严重度，源码文件:行号、具体复现步骤、建议最小修复。
2. `FINDINGS.json`：机器可读发现；字段至少包含 `id`, `severity`, `file`, `line`, `claim`, `reproduction`, `expected`, `actual`, `recommendation`。
3. `TEST_RESULTS.txt`：真实执行的命令、环境、退出码、测试结果和日志摘要；若未运行应写明原因，绝不可编造通过。
4. `SCOPE.json`：`repo`, `branch`, `audited_commit_sha`, `audit_started_at`, `audit_completed_at`, `source_root`, `test_mode`, `auditor_identifier`。

## 基准要求（与用户确认的设计）

P1输入为：已获Gate 0.1批准的**用户需求/意图**及**12角色Harness+模型担当矩阵**。Hermes本身仍是Orchestrator，P1是它的硬编排内核。本次从Phase 0.2 Planner开始，最后在Gate 5.9停下等待人工审批；Phase 6和7没有部署权，也不在当前实现范围。Phase 0.1前期意图和矩阵对话属于后续P2。绝对禁止把废弃的 `vibe-coding-repo` 作为本次代码基准。

专业角色依职责和交付物Soul工作；模型、Harness、执行节点必须依获批配置快照，不能硬编码。21bao/Windows为本地执行机，盲审只通过外部P0 A2A标准接口调用5bao、9bao、rusty这三个Debian候选，P1不自行实现或直接派发远端盲审。P0仍在另一个Session优化，接口不确定时只做审计并提出对接问题。

流程：`0.2 Planner -> Gate0.2人审冻结 -> 1 Worktree -> 2 Worker -> 3 Spec || 4 Quality并行同SHA -> 4.5 Tester A -> Gate A -> 5.0 A2A -> 5.1整改 -> 5.2终测 -> 5.3独立仲裁 -> Gate B -> 5.85合规总报告 -> Gate5.9等待`。双审各自报告和独立合规审计，汇合都通过后才能启动Tester A。

三闭环：本地研发最多5轮、终测整改最多5轮、**全局合规回溯最多2次**。合规审计每一步执行，只审是否按矩阵、正确顺序、合法职责、上下游交付与原始证据作业；**禁止越界对业务技术方案挑刺**，也不应以普通格式问题阻断。技术结论归Spec/Quality/Tester/Arbitrator。`APPROVE_WITH_COMMENTS`不得无理由判为失败；`QUESTION`和`NEEDS_SPECIALIST`不得假放行。

## 审计检查细则（逐项深挖）

A. **硬状态机与审批Gate**：能否绕过Gate0.1审批SHA/Gate0.2规格冻结、跳过Reviewer、用任一伪造PASS提前进入下一步；Gate5.9之后是否绝无生产改写/部署入口；是否错误把测试模拟当真实批准。

B. **阶段控制**：Phase 3/4确实并发、同commit/spec、独立报告/审计并完全汇合；任一审查失败是否严谨回Phase2；Tester A/B是否按相应Gate运行；Arbitrator是否最后、独立、只读且审阅真实全卷。

C. **预算与回溯**：5/5/2是否持久化、真正有上限，重启/恢复能否重置或漏计；是否精确回退最早失范阶段、正确废弃下游旧结果；异常与对账是否误触发重派付费Agent；请特别检验文件被篡改时回溯是否有真实修复路径。

D. **审批矩阵与Soul**：12角色是否全部存在；选择哪个Harness/模型/节点是否来源于批准矩阵，能否在运行中被隐性替换；Soul哈希是否检查；是否真能识别实际运行器所用模型，而不是相信模型自己报的字符串；角色输出证据与源commit/spec是否一致。

E. **合规Audit审计尺度**：只检查流程与上/下游交付，是否对技术偏好误报BLOCKER；是否漏报实质性越权；Git source SHA是否含新建/删除/未跟踪、测试文件与可能忽略的文件；承认写后恢复无法靠SHA发现，不能宣称物理只读。

F. **A2A集成边界**：是否只通过外部接口；同commit SHA；至少2个真正不同的受信物理节点才可满足quorum；第三席600秒由P0负责；超时是否错误视作失败；冒认物理ID、两个Node别名、篡改报告能否骗过；P0尚未成熟时是否安全阻断。

G. **崩溃/并发/Windows**：SQLite事务、事件链、跨进程锁；RUNNING意外退出是否双派；线程中并行写数据库是否混淆产物；Windows E盘路径与Git worktree真实隔离；命令注入、目录穿越、未授权命令、过量日志、子进程残留、超时恢复。

H. **证据闭环**：是否保存可核验的原始stdout/stderr/test exit code/Agent报告和文件SHA；是否遗漏审核报告；是否有机会仅凭JSON里的`PASS`推进；最终仲裁和合规报告是否全文不改地呈报；审计文件是否真的被Git纳管而非忽略；Magpie usage.jsonl作为原始物证的集成有无缺口。

I. **代码质量和测试本身**：做必要的针对性代码正确性审计，例如状态机分支错误、竞态或恢复缺陷；但不要评价被自动开发的业务应用技术方案，因为本任务只审P1内核。主动编写临时负面测试验证关键失败路径，严禁把模拟测试表现描述为真实节点效果。

## 判决标准和工作方式

- 将发现分为 `BLOCKER`, `HIGH`, `MEDIUM`, `LOW`。只对能够证明的真实风险升级严重度；遵守“整体变好、避免不可接受风险”原则，不因格式偏好拒绝放行。
- 明确区分：`已复现的代码BUG` / `设计未实现或需对接` / `当前无法核实的环境依赖` / `可选优化`。
- 对每条发现给出**代码路径和精确行号**、预期与实际结果、具体复现或论证链、合理最小修复方案。不能用“建议加强健壮性”之类空泛表述代替证据。
- 用真实命令在隔离目录运行测试；若无法独立克隆或执行，必须说明没有执行，并给出限制。
- 审计结论必须指出“是否可以进入真实21bao集成”与“是否只允许继续离线修复”，不得把这两种PASS混为一谈。
- 不修改代码或配置。审计Agent唯一允许向GitHub写入的是**本轮报告所在的新目录**；审计时固定源码提交SHA。提交时必须验证不会覆盖旧报告或改动P1源代码；报告提交完成后提供GitHub链接及审计提交SHA。
- 若GitHub无写权限，不要假装已上传，先在可访问的交付物目录生成报告，明确告知上传受阻。

## 必须输出给用户的内容

1. 本次审计固定的Commit SHA；2. 综合PASS/FAIL与是否允许真实集成；3. 每条有证据的缺陷；4. 实际运行的测试命令和结果；5. 已上传的GitHub审计目录及报告Commit SHA；6. 尚未核实的事实与建议下一轮复审范围。
