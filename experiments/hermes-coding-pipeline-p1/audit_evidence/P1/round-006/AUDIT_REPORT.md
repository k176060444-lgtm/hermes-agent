# Hermes Coding Pipeline P1 — Round-006 独立审计报告

- 审计状态：**COMPLETE**
- 代码结论：**CONDITIONAL（有条件通过）**
- 仓库：`k176060444-lgtm/hermes-agent` / 分支 `feature/p1-coding-pipeline-20261104`
- 固定审计源码 Commit：`a69d04084c72dae437fc79f1fb9eaed8152d1644`（parent = Round-005 报告 Commit `9eb543de791a98f7bad4b5ebf1fd1b2aa6836df9`，tree `c784034eca01ed299a3178649d2b8b8f27f662be`）
- 审计执行环境：21bao（Windows 10 本机隔离 scratch，离线）；Python 3.11.15，git 2.54.0，PowerShell 5.1
- 审计担当：独立审计 Agent（Round-006）
- 日期：2026-11-04（中国标准时间）

## 一、方法与完整性

1. 按固定 Commit 的 Git tree 取回 P1 目录全部 **74 个文件**（上轮 67，+7），逐文件比对 Git blob SHA：**测试前 74/74 一致，测试后 74/74 一致，0 不匹配**——被审源码全程未被修改。
2. 原项目测试在快照上原样执行（14 批），无任何夹具或产品测试改动。
3. 独立对抗探针在 `probe-copy` 隔离副本执行（51 用例 × 7 组，全部 exit 0）；Windows NTFS 取证仅作用于审计方新建的一次性 scratch 目录（用完即删），未触碰任何真实 Hermes/P1 任务目录或系统策略。
4. 未调用真实付费模型，未连接 5bao/9bao/rustyhand，未修改现网配置。

## 二、开发方声明的独立复核

开发方声明 Linux 上"107 passed, 1 skipped"。**21bao Windows 实测：108 collected / 104 passed / 0 failed / 4 skipped**——4 个 skip 全部合法（3 项 R4-001 POSIX-mode 测试 + 1 项按 R5-003 修复正确跳过 NT 的制表符文件名测试）。R5-004 的 Windows DACL 正/负向测试在本机**真实执行且 PASS**（未跳过），`test_r2_008` 两项、`test_r5_001/002/005` 全部执行通过。

## 三、Round-005 问题逐项复核

### R5-001（信任检查面）→ **FIXED**

- `p1/trust.py:100-112`：检查面 = home、`state.sqlite`、存在（或为符号链接）的 `state.sqlite-wal`/`-shm`、存在的 `snapshots/logs/artifacts/audit_evidence` 目录；缺失/链接 fail-closed。
- 探针 r6b_trust（Windows 真实进程）：枚举 spy 实测 `inspected=['.', 'snapshots', 'state.sqlite', 'state.sqlite-shm', 'state.sqlite-wal']`（Store 打开后 WAL/SHM 存在即被纳入）；父目录仍不检查（与整改文档声明一致）。
- 探针 r6a（真实 NTFS，一次性目录）：受控私有 DACL 全通过（正向）；给 **logs 证据目录**加一个 Everyone ACE → `REJECTED: NTFS task state grants access to other principals`（子对象独立 ACL 能拦截，WAL 情形与开发方测试一致）。
- 残留观察另立 R6-002（P3），不构成阻断。

### R5-002（执行元数据完整性）→ **FIXED（P1 范围内），真实产生路径 NOT_VERIFIED**

- `p1/executor.py:170-172,190`：`capture.json` 落盘并返回 `capture_sha256`；`p1/workflow.py:266-273` 将 capture 文件名+摘要绑定进 `logs`/`invocation` 两套 details 并经 `finish_run` 入哈希链事件；`p1/workflow.py:535-552`：integration run 对 capture 做三重 SHA 复核（磁盘 vs logs-info vs invocation）+ capture 内 stdout/stderr 摘要引用 + `timed_out`/`output_limit_exceeded` 语义拒收。
- 探针（r6a）：
  - **完全链自洽**的 COMPLETED run，capture 写 `timed_out:true` → `audit_events=[]`（哈希/事件全一致）但 `verify_evidence NON_COMPLIANT: invalid role capture receipt`，Gate 5.9 导出抛 `evidence invalid`——语义检查独立生效。
  - stdout.bin 注入内容 + 同步改写 details/capture 全部摘要（不重写事件）→ 事件链捕获 `run 9: run details or output differs from journal`，NON_COMPLIANT、导出拒绝。
  - 因超时/中断留在 RUNNING 的调用 → `status=NEEDS_RECONCILIATION`（persisted 保留）、`verify_evidence NON_COMPLIANT`、导出关闭——**已完成调用与待对账调用正确区分，未完成永不 COMPLIANT**。
  - 篡改/删除 capture → 开发方 `test_r5_002`（Windows 实跑 PASS）与本审计 r6a 双重确认。
- 边界声明：以上验证经合成登记路径；真实 integration run 迄今不可能存在（被 R5-005 gate 拒绝），故 capture 绑定在真实执行流中属 **NOT_VERIFIED（Stage-2）**。`timeout.json` 仍为诊断性（开发文档明示），可接受：超时路径设计上不 finalize run。

### R5-003（Windows 文件名兼容）→ **FIXED**

- `tests/test_remediation_round4.py:40-60`：制表符用例改名 `test_r4_002_posix_tab_filename` + `skipif(nt)`；新增 `test_空 格.py`（空格+中文）用例。
- Windows 实测：改名后的空格/中文用例 **PASS**（batch12），tab 用例正确 SKIP，全套 0 failed。本审计回归电池（r6b_paths 19 例）复验中文/空格/`#`/`()`/引号/子目录路径全部放行、8 类非法变更全部拒绝、Unicode 考卷保护端到端有效。

### R5-004（Windows ACL 测试覆盖）→ **FIXED**

- `tests/test_remediation_round5.py:98-144`：真实 NTFS DACL 正/负向测试，`skipif(os.name!='nt')`（Windows 执行、Linux 跳过，方向正确）；仅操作 pytest 一次性 tmp 目录的 `Set-Acl`，不触碰真实任务/系统。
- **在 21bao 本机实际执行并 PASS**（batch13，未跳过）：正向（私有受控 DACL 被接受）+ 负向（WAL 加 Everyone ACE 被拒）。本审计另行扩充 logs 目录 ACE 负向（r6a）。

### R5-005（Orchestrator/Agent 身份隔离）→ **MITIGATED_FAIL_CLOSED（不判 FIXED）**

- `p1/executor.py:124-129`：旧 flag 检查之后**无条件** `raise InvocationError("NOT_VERIFIED: no authenticated separate-identity Agent runner is installed")`，位于 adapter 解析与 Popen 之前。
- 探针 r6b_gate：`TRUSTED_INTEGRATION_EXECUTION_VERIFIED` 强制 True + 完整合规 adapter（绝对路径、`explicitly_authorized:true`、甚至附加 `isolated:true` 布尔）→ invoke 仍拒绝，`logs/907.*` 零副作用；直调 `call_adapter` 仍 `ContractError NOT_VERIFIED`。
- 但逐项核对用户要求的四个问题：①普通本地子进程**确实**继承 Orchestrator 身份（代码注释与实测一致）；②旧 flag 误开仍被独立 gate 拒绝——成立；③**不存在**真实独立身份执行器、无 token SID 认证、无独立签名权威——代码全文无 runas/LogonUser/SID 比对机制；④无法证明 Agent 不可访问状态库（同身份进程必然可访问）。按纪律判 **MITIGATED_FAIL_CLOSED**，开发方在 README/KNOWN_LIMITATIONS 中的自我分类诚实一致。独立身份部署与 21bao 实际进程隔离 **NOT_VERIFIED**。

### R2-006（携带）→ **MITIGATED_FAIL_CLOSED / NOT_VERIFIED 不变**：真实 A2A 线路收据与物理身份认证仍缺失；P1 未替代三节点盲审。

## 四、新增问题

| ID | 严重度 | 类别 | 摘要 |
|----|--------|------|------|
| **R6-001** | **P2** | 实际可运维性缺口（integration 生命周期） | trust.py 对**每个**被检路径硬性要求 `AreAccessRulesProtected=True`，但自然部署序列"保护 home → SQLite 自动创建 state.sqlite/-wal/-shm"产生的子文件必然携带**继承 ACE**（icacls 显示仅 `KK:(I)(F)`，无任何外来主体，有效权限完全私有）→ `validate_private_task_home` 永久拒绝，即使人工逐子文件保护后，SQLite 正常重启（clean close 删除 -wal → reopen 重建继承副本）再次拒绝。实测链：step1 自然创建 REJECTED（"NTFS ACL inherits permissions: state.sqlite"）；step2 手工逐文件保护 ACCEPTED；step3 checkpoint 复用文件仍 ACCEPTED；wal_churn 删除重建 REJECTED。机制 fail-closed（安全方向正确），但意味着当前检查面在真实 Windows 生命周期下**不可满足**，且文档未提供可执行的 provisioning 程序。当前无实害（integration 全关），属 Stage-2 阻断项。文件：trust.py:67-68,100-112。最小修复：仅对 home 顶层要求禁继承；子对象改为"有效 Allow 主体 ⊆ {me, SYSTEM, Administrators} 且继承源为受保护 home"，或提供 provisioning 工具并声明 WAL 生命周期语义。 |
| **R6-002** | P3 | 范围观察 | `logs/` 等目录**内部**单文件的独立 DACL 未被逐个枚举（r6a 探针：给 `logs/1.stdout.bin` 加 Everyone ACE，validate ACCEPTED）。缓解：文件在受保护私有目录内由继承获得私有 ACL，非 TCB 主体无 WRITE_DAC/所有权可改；内容已被 capture/run 摘要绑定。不阻断。 |

## 五、整体回归（0 回归）

r6b 六组 46 例复验：五入口 integration fail-closed（BLOCKED、0 dispatch、事件 1→1、持久化不重写）；ACL 查询脚本只读（无 Set-Acl/icacls 动词）；缺失路径拒绝；Phase 3/4 真实并行同 Commit（Barrier 双角色、单一 reviewed_commit）；Gate 0.2 行篡改 BLOCKED；Tester 考卷保护（含 conftest 端到端阻断）；run 删除/变更/重复 finish 链检测；5/5/2 预算跨进程持久化（round_a 2→5 FAILED exit 10）；Pro-Audit 边界（劣质技术报告 COMPLIANT / 错 commit NON_COMPLIANT）；直调 A2A NOT_VERIFIED；假 no-op 拒绝；Gate 5.9 最终报告篡改拒绝、还原后 SIMULATION ONLY 正常导出；离线路径 `Store._event` 追加伪造仍可行（offline 声明为非证据案卷，边界不变）。

## 六、真实集成放行判断

- `TRUSTED_INTEGRATION_EXECUTION_VERIFIED=False` + executor.py:129 独立 gate 双保险：真实执行**代码级禁用**，fail-closed 正确。
- 保持 NOT_VERIFIED：独立身份执行器/token SID 认证（R5-005）、21bao 真实 ACL provisioning 与账户隔离（R4-001 前提）、Windows 后代进程树终止、真实 Harness/模型/测试收据、人工审批身份、P0 物理身份、远端 A2A 收据、E: 工作树、生产 kill guard。
- **不得宣称 P1 可在 21bao 正式运行**；本轮 CONDITIONAL 仅指离线语义整改有效、fail-closed 全面、无流程回归。R6-001 须在启用真实执行前解决，否则真实任务一启动即被自己的信任检查永久阻断。

## 七、判定汇总

| 项目 | 状态 |
|------|------|
| R5-001 | FIXED |
| R5-002 | FIXED（离线可验证范围；真实产生路径 NOT_VERIFIED 至 Stage-2） |
| R5-003 | FIXED |
| R5-004 | FIXED（Windows 实执行 PASS） |
| R5-005 | MITIGATED_FAIL_CLOSED |
| R2-006 | MITIGATED_FAIL_CLOSED（携带） |
| 新增 | R6-001 P2、R6-002 P3 |
| 回归 | 0 |
| 开发方测试（Windows 实测） | 104 passed / 0 failed / 4 skipped（均合法 POSIX-only） |
| 独立探针 | 51 例全部 exit 0 + 2 项 WAL 生命周期取证脚本 |
| 源码完整性 | 74/74 blob 前后一致 |
