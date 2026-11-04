# Stage-2B-2 部署预案 — Windows 独立身份 Runner、ACL 与凭据（全部待批准，未执行）

状态：**PROPOSED**。本文只是计划与验收标准；本轮未创建账户、未注册服务、未修改任何现有目录 ACL、未运行真实模型。每一步执行前需要 KK 单独批准。

## 0. 前置核查（执行日当天，只读）

```
whoami /groups                    # 确认 KK 令牌含 Administrators（已知 VERIFIED_LOCAL）
net user                          # 确认 agentx 不存在
Get-ScheduledTask | ? TaskName -match 'Hermes|Magpie'   # 现存任务基线快照
icacls C:\Users\KK\AppData\Local\hermes                 # 基线 ACL（见 §2 实测记录）
python -m p1 … runner-health（未来 CLI）                 # manifest 缺失 → 必须报不可用
```
回退锚点：记录以上输出快照 + `E:\Hermes_Backups` 冷备 P1 分支 commit。

## 1. Agent 账户（agentx）

- `net user agentx <随机26位密码> /add`；**不**加入任何特权组（Users 默认成员即可）。
- 密码管理：DPAPI 密封存于 KK 凭据库（KK 手动录入 Runner 服务配置一次）；仓库与任务台账零明文、零哈希可逆材料。
- 登录形态：Runner 服务持凭据以 `CreateProcessWithLogonW(LOGON_WITH_PROFILE)` 生成 agentx 令牌子进程；agentx 不交互登录。
- 验收：`live_process_token(<agentx pid>).user_sid == agentx SID`；`group_sids` 不含 `S-1-5-32-544`；`verify_execution_identity` 通过而 `orchestrator_sid()` 不等价。

## 2. ACL 矩阵（实测基线 → 目标）

实测基线（VERIFIED_LOCAL，本轮）：`C:\Users\KK` = `BUILTIN\Administrators:(OI)(CI)(F)` + `KK:(OI)(CI)(F)`，无 Users/Authenticated 条目；`E:\HermesStorage` 含 `Authenticated Users:(I)(M)` 与 `Users:(I)(RX)` —— **E: 现状不可直接当台账**。

| 路径 | 属主 | 目标 DACL（保护根=禁继承） | agentx 有效权 | 目的 |
|---|---|---|---|---|
| `C:\Users\KK\AppData\Local\hermes\p1\tasks\<task>`（台账根） | KK | KK (OI)(CI)F；SYSTEM/Admin (OI)(CI)F（继承链保留，声明为 TCB）；**无任何 Other/AU/Users** | 无（C:\Users\KK 链不含 agentx ACE） | state.sqlite/日志/artifacts/snapshots 独占 |
| `…\<task>\snapshots,logs,artifacts,audit_evidence` | KK | 自然继承根（Round-007 语义：子对象继承私有 ACE 被接受，外来 Allow 即拒） | 无 | 台账内部件同域 |
| `E:\P1-worktrees\<task>`（工作树） | KK 创建，授予 `agentx:(OI)(CI)(M)`，禁继承去除 AU/Users/Everyone | agentx M + KK F | 读写 | Agent 唯一可写域 |
| Runner spool inbox（`…\p1\spool\in`） | KK | KK (OI)(CI)(F)；agentx:(OI)(CI)(RX) | 只读 | P1→Runner 请求（无敏感凭据，仅绑定摘要） |
| Runner spool outbox（`…\p1\spool\out`） | KK | KK (OI)(CI)(F)；**agentx 无 ACE** | 无 | Runner(KK 侧服务身份)写收据；Agent 无法伪造落盘点 |
| `D:\codex`、`D:\opencode`、Harness exe | KK | 现状 RX 可读（agentx 需读+执行：追加 `agentx:(I)(RX)` 于两个安装目录或复制镜像） | R+X | 启动器；不被 agentx 改写（无 W） |
| `C:\Users\agentx\.codex` / `.config\opencode` | agentx | agentx F + SYSTEM/Admin（OS 默认） | 私有 | Agent 侧凭据镜像（见 §4） |

验收（逐条实跑）：`verify_ledger_inaccessible(home, agentx_sid, agentx_groups)` 通过；给台账任一对象加 agentx ACE → `verify_execution_identity` 必须拒；`icacls <worktree>` agentx Modify 生效；outbox 内 agentx 令牌 `Set-Content` 实测失败。

## 3. Runner 服务

- 形态：计划任务（同现有 Hermes_Gateway 模式，KK 身份常驻）+ `HERMES_SUPERVISED_CHILD` 看门狗；可执行体为独立签核的小 exe 或钉死 SHA 的 `python -m p1.runnerd`（放独立目录 `C:\Users\KK\AppData\Local\hermes\p1\runner\`）。
- 职责：轮询 inbox 请求 → 校验 request 摘要与 manifest pin → `CreateProcessWithLogonW(agentx)` 启动 harness argv（矩阵冻结）→ 每 run 一个 Job Object（`p1/winjobs.Job`，KILL_ON_JOB_CLOSE；超时 `terminate()`）→ 管道原始 stdout/stderr 由 **Runner(KK 身份)** 写 outbox/台账 logs → 生成 receipt（含 live 令牌复测结果、pid、job id、argv 摘要、capture 元数据）。
- 失败关闭：manifest 缺失/摘要不符/agentx 不存在/令牌实测==KK → 拒绝派发；崩溃后 `reconcile` 只读，UNKNOWN 不重派（P1 既有语义 + poll 三态）。
- Runner 自身的 exe 摘要写入 `runner_manifest.json` 并被任务快照引用，变更即阻断。

## 4. 凭据管理

- Agent 只持有其角色所需模型访问：agentx 的 `CODEX_HOME=C:\Users\KK…` → 改为 `C:\Users\agentx\.codex`，内放**不含 Hermes/QQ/P0 材料**的 codex `config.toml` + Magpie 访问 header（值由 KK 线下写入，任何报告/日志/仓库不落值）。OpenCode 同理（`OPENCODE_CONFIG_DIR` 指向 agentx 私有）。
- 环境注入由 Runner 在 CreateProcessWithLogonW 时按矩阵构造最小 env（禁继承 Hermes 全量环境）。
- 残余风险（如实声明）：KK 属 Administrators，可 TAKE OWNERSHIP 读 agentx 文件；这属声明 TCB，不构成对远端/模型侧的额外防线。

## 5. 活体验收清单（Runner 就位后、任何计费调用前）

1. `runner-health` 可用且 SID 对撞检查全绿。
2. codex 0.166.0（或当时实际版本）`exec --json` 真实小事件样本：schema 与 `p1/harness/codex.py` 归一化一致，session_id/rollout 路径可取；`--output-schema` 行为实测。
3. opencode agent 文件被 `opencode agent list` 识别，`run --format json` 事件与解析一致，`export` 可用。
4. 超时：Job 内挂起子进程树在 timeout 秒全灭（复用 test_stage2b1_runner 的活体模式）。
5. 取消/重启：kill Runner 后 P1 status == NEEDS_RECONCILIATION；恢复后 reconcile 不重派。
6. 台账不可达：agentx 内实测 `Get-Content <ledger home>\state.sqlite` ACCESS_DENIED。
7. 矩阵外模型/CLI 漂移：改版本号或换 exe → `verify_frozen` 阻断。
8. 单次最小计费探针（须 KK 明示批准并报预估费用）：一个角色一次 hello 级任务，全链收据入台账 → 交独立 Qwen-Flash 审计。

## 6. 回退

`Disable-ScheduledTask` Runner → 杀服务进程 → `net user agentx /delete`（工作树/台账保留取证）→ inbox/outbox ACL 恢复快照 → executor gate 从未开放，P1 语义不受影响。任何一步出问题：停止，台账转 NEEDS_RECONCILIATION，不回滚已发生计费调用（对账流程处理）。

## 7. 仍为硬阻断（顺序依赖）

P0 接口证据（R2-006 八项确认）→ 未解决前 Phase 5.0 永远 fail-closed；审批身份密码学绑定；E: 生产工作树与副作用 kill guard；Phase 6/7 不在路线图内。
