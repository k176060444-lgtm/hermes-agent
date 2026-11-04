# Stage-2B-1 实施报告 — 可信执行适配层（只读开发，未部署）

基线：`feature/p1-coding-pipeline-20261104` HEAD `38c76de3f7e8b47951b01d430806fffe10fe1cdc`
（parent = Round-007 审计报告 `bc9b6cba…`；`38c76de` 本身是 R7-001 位置耦合修复，经审阅无放松）。
开发分支：`feature/p1-stage2b-20261104`。平台：21bao Windows 10 LTSC 19044，Python 3.11.15，git 2.54.0。

## 一、本轮交付内容

### A. 可信 Runner 协议 + 离线客户端 — `p1/runner.py`（VERIFIED_LOCAL：机制在本机实测）
- 固定字段 launch request（task/run/role/harness/model/soul/matrix/spec/intent/commit/worktree/input/idempotency/frozen_harness/request digest），`validate_launch_request` 摘要自校验；任何字段篡改即拒。
- `validate_receipt`：receipt 与 request 交叉绑定（task/run/idempotency/exe digest）；`UNKNOWN` 状态**只许对账**；schema 对 `isolated:true` 一类自报布尔**读取但不赋权**（测试固证）。
- 编排侧实测函数：`orchestrator_sid()`、`live_process_token(pid)`（ctypes OpenProcessToken/GetTokenInformation，TokenUser 枚举值为 1，TOKEN_GROUPS 内联数组解析）、`live_process_image(pid)`。本进程实测成功（KK SID + 14 组，含 Administrators——正是 agentx 必须分离的反证）。
- `verify_execution_identity`：receipt 与 manifest pin、与**活体令牌**三方一致；agent SID==编排者 SID → 拒；携带 Administrators → 拒；可执行体摘要偏离冻结快照 → 拒。
- `verify_ledger_inaccessible`：台账根 DACL 实测；agent 主体/Everyone/Authenticated Users 出现在 Allow 即拒（Administrators 不判为泄漏——trust.py 已声明 TCB 前提，且成员资格由上一关单独拦截）。
- `RunnerClient`：无 manifest → `runner_health()` 不可用 → `launch()` 抛 `RunnerUnavailableError`；**传输层故意未实现**（"runner transport not implemented in Stage-2B-1 by design"）。`poll()` 三态 NOT_DISPATCHED/DISPATCHED/RECEIPT/NO_RUNNER，任何歧义只回读不落判。

### B. Harness 适配层 — `p1/harness/{__init__,codex,opencode}.py`
- 版本冻结：`snapshot_entry`（绝对路径 + exe sha256 + version + capabilities + probe sha）；`verify_frozen` **从磁盘重测摘要**，exe/版本/能力漂移三连阻断。
- 能力检测：`detect_capabilities` 从 --version/--help/exec --help（codex）与 --version/--help/run --help（opencode）文本判定；`require_capabilities` 缺一即阻断重批。模型、sandbox、extra argv 一律取自获批矩阵条目；argv 构建器零默认模型（测试断言 argv 不含任何内置名称）。
- 事件解析（合成样本）：codex JSONL / opencode parts JSON；不可解析与非对象行分别标 `unparseable/unknown`，**不静默丢弃**；session_id 与 rollout_path / sessionID 提取，opencode 终局证据需 `export <sessionID>`。
- 收据语义红线：`extract_command_evidence` 全部 `trusted=False, source="cli-event-self-report"`；仅 `merge_runner_records` 在命令与退出码与 Runner 记录**完全一致**时升级 `trusted=True`；矛盾标 `contradiction`，无记录保持不信任。"CLI 说命令成功了" ≠ "可信 Runner 记录了退出码"。
- OpenCode agent 定义：`render_agent_markdown`（subagent 模式 + 矩阵模型 + permission 表 + `auto` 永拒自批 + Soul 正文），输出确定性可哈希；真实 CLI 的 agent 文件格式**待 Stage-2B-2 活体验证**（NOT_VERIFIED）。

### C. Hermes 插件草案（未安装）— `integrations/hermes/p1_orchestrator/`
- 7 工具面：p1_init/p1_run/p1_status/p1_reconcile/p1_approve_spec/p1_audit/p1_export，对齐 `python -m p1` CLI 子命令。
- 防呆：`p1_repo_dir` 必须显式绝对路径且含 P1 包，否则全部拒绝；approve-spec 强制 `provenance{platform,chat_id,message_ref}`，approval_id 生成 `hermes-unverified:` 前缀指针并标 `identity_verified=False` —— 昵称字符串不构成审批凭据，会话级身份绑定是 Stage-2B-2 验收项。
- 本轮不复制进任何 live profile，不注册 Gateway（授权边界）。

### D. Windows 独立身份机制设计 — `p1/winjobs.py` + 文档 §三（见 PROVISIONING_PLAN）
- Job Object 封装（KILL_ON_JOB_CLOSE + TerminateJobObject + process_alive）**本机实测杀死两代进程树** —— R2-008/后代进程阻断项从 NOT_VERIFIED 推进为"机制 VERIFIED_LOCAL，真实 Runner 接线 NOT_VERIFIED"。

### E. 测试
- 新增 `tests/test_stage2b1_{runner,harness,plugin}.py` 共 48 用例；全套 **161 passed / 5 skipped / 0 failed（21bao Windows 实跑）**。
- 基线修复：`tests/test_remediation_round5.py` stub 签名适配 `protected_root` kwarg（`38c76de` 在 Windows 上引入 1 个失败，Linux 不可见；本轮修复使其复绿——测试工装修复，非产品语义变更）。
- 夹具披露：本轮开发中修复过 3 处审计侧/开发侧测试缺陷（ctypes TokenUser 枚举值误用 20→1、TOKEN_GROUPS 内联数组误按指针解析、FakeRun 模式匹配顺序），均非产品语义问题；修正后全部重跑取证。

## 二、设计约束验证状态（Stage-2A §四 6 条）

| 约束 | 状态 |
|---|---|
| Agent 实际身份 ≠ KK | 机制已实现并本机实测（live token 对比）；无真实 Agent 进程可测 → 执行入口 BLOCKED 保持 |
| Agent 非 Administrators 成员 | `verify_execution_identity` 组检查实现；单测覆盖 |
| Agent 无台账读写 | `verify_ledger_inaccessible` DACL 实测实现 + 单测；真实 ACL provisioning 属 Stage-2B-2（BLOCKED 待批） |
| Agent 仅触工作树与输入 | 设计上 worktree=矩阵路径、home 不在 agent ACL；argv 构建器仅注入 worktree；活体拒访验证未做（NOT_VERIFIED） |
| Agent 不持有 Hermes/用户全量凭据 | 设计原则写入 PROVISIONING_PLAN（agentx 独立 CODEX_HOME/XDG，凭据最小化）；未实施 |
| 无信任收据一律阻断 | executor.py:129 原 gate 未动 + RunnerClient.launch 无 manifest 必拒 + UNKNOWN 只许对账 —— 三层保持 |

## 三、明确未完成（NOT_VERIFIED / BLOCKED）

1. Runner 服务本体（exe、传输、spool 权限模型）——未创建、未注册（授权边界）。
2. executor→runner 接线：`invoke()` 仍在原 gate raise；适配层是纯库，**没有任何真实派发路径**。
3. Codex/OpenCode 真实事件 schema 与 agent 文件格式：仅按 0.166.0/1.19.3 帮助文本静态判定 + 合成流解析；活体一次调用（计费）需 KK 批准。
4. 真实测试执行收据端到端：依赖 1/2/3。
5. P0（R2-006）：接口证据为零，维持 BLOCKED；本层未触碰远端。
6. 审批会话身份密码学绑定（KNOWN_LIMITATIONS #2）：插件只做 provenance 指针，验证器留待 Stage-2B-2。
7. E: 工作树生产语义、Hermes Gateway 重启对账端到端联调（本轮仅台账层模拟验证）。

## 四、变更文件清单

新增：`p1/runner.py`、`p1/winjobs.py`、`p1/harness/{__init__,codex,opencode}.py`、`integrations/hermes/p1_orchestrator/{plugin.yaml,__init__.py,README.md}`、`tests/test_stage2b1_{runner,harness,plugin}.py`、`docs/STAGE2B_1_IMPLEMENTATION.md`、`docs/STAGE2B_2_PROVISIONING_PLAN.md`。
修改：`tests/test_remediation_round5.py`（stub 签名 1 行）、`README.md`（状态行）。
未动：`p1/workflow.py`、`p1/executor.py`、`p1/state.py`、`p1/trust.py`、全部历史审计报告、任何 live Hermes 配置。
