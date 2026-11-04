# Hermes Coding Pipeline P1 — Round-005 独立审计报告

- 审计状态：**COMPLETE**
- 代码结论：**CONDITIONAL（有条件通过）**
- 仓库：`k176060444-lgtm/hermes-agent`
- 分支：`feature/p1-coding-pipeline-20261104`
- 固定审计源码 Commit：`3be86f69b87d7f69c0f739d31615c5e0feda751b`
- 上一轮审计报告 Commit：`715664e02cf25c31f15bad998174a7e91c130425`
- 审计日期：2026-11-04（中国标准时间）
- 审计执行环境：21bao（Windows 10，本机隔离 scratch 目录，离线）

## 一、审计方法与完整性基线

1. 按固定 Commit 的 Git tree 逐文件取回 P1 目录全部 67 个文件，先校验后测试、测试后再校验：**67/67 Git blob SHA 一致，0 不匹配**，证明被审源码在审计全程未被修改。
2. 原项目测试在源码快照原样执行（不改夹具、不改产品测试），共 101 项、13 批。
3. 独立对抗探针在 `probe-copy` 隔离副本执行（新增文件仅存在于副本），共 46 个用例、9 个批次，全部 exit 0；另对 `p1/trust.py` 做 Windows NTFS ACL 正/负向取证 4 例。
4. 全程未调用真实付费模型、未连接 5bao/9bao/rustyhand、未修改 Hermes 现网配置与 A2A 节点、未修改被审源码/Soul/历史审计报告。

## 二、开发方测试声明的独立复核（重要偏差）

开发方声明"101项离线测试通过"。**在 21bao（Windows）实际复跑结果为：97 passed / 1 failed / 3 skipped / 0 errors**：

- 失败项：`tests/test_remediation_round4.py::test_r4_002_test_filename_with_spaces_and_tabs`（tests/test_remediation_round4.py:43）。该测试创建含制表符的文件名 `test_空\t格.py`，Win32 文件系统不允许，`write_text` 抛 `OSError: [Errno 22] Invalid argument`。这是**测试工装的跨平台缺陷**（R5-003），不是产品代码缺陷：产品侧 NUL 字节解析本身正确（本审计用中文、空格、`#`、`()`、`'`、子目录等 6 类合法路径 + 8 类非法路径全部验证通过）。
- 3 个 skipped：`test_r4_001_*` 三项全部标注 "POSIX mode check runs only on POSIX"。**即 R4-001（本轮核心整改）的开发方回归测试在 Windows 上 0 执行**（R5-004）。本审计已用真实 Windows ACL 取证补齐该空白（见三.1）。

结论：开发方声明仅在 POSIX 环境成立；在 21bao 目标平台不成立。

## 三、Round-004 问题逐项复核

### R4-001（状态库信任边界，原 P1）→ **MITIGATED_FAIL_CLOSED**（不判 FIXED）

代码事实（`p1/trust.py`、`p1/workflow.py`）：

1. 检查内容：home 与 `state.sqlite` 必须存在且非符号链接（trust.py:101-103）；Windows 路径经 `powershell.exe -EncodedCommand` 实时查询 DACL（trust.py:24-74）：`AreAccessRulesProtected` 必须为真（禁继承，trust.py:67-68）、owner 必须等于当前 SID（trust.py:69-70）、除 {当前用户, S-1-5-18, S-1-5-32-544} 外不得存在任何 Allow ACE（trust.py:27,35-38,71-72）。
2. 失败关闭：PowerShell 非零退出、JSON 基数不符、超时、OSError 全部转为 `TrustBoundaryError`（trust.py:61-74）；本审计探针实测缺 home、缺数据库均拒绝（t1）。
3. 五入口全部实际执行检查：`status()` workflow.py:149、`run()` 647 与步内 672、`resume()` 712、`approve_spec()` 629、`verify_evidence()` 495；`export_report()` 经 `_require_trust`(737)+`verify_evidence` 间接强制。
4. 检查失败时不重写可疑状态：t1 探针实测 integration 任务在默认继承 ACL 下 `status=BLOCKED / preflight=FAILED / run=BLOCKED / evidence=NON_COMPLIANT / dispatched=0`，事件数 1→1、持久化状态 READY 未被重新封存。
5. Windows 正向/负向取证（`testlogs/acl_evidence.json`，一次性 scratch 目录，用完即删）：受控 DACL（仅当前 SID）→ **ACCEPTED**；追加 Everyone RX ACE → **REJECTED: grants access to other principals**；`/reset` 恢复继承 → **REJECTED: NTFS ACL inherits permissions**；仅数据库文件带额外 ACE → **REJECTED**。ACL 查询脚本仅 `Get-Acl/GetAccessRules`，无任何写 ACL 动词（探针 t1 断言验证）。

不判 FIXED 的理由：

- **信任前提只写在注释里，没有被代码强制**：trust.py:3-6 明确承认"同身份特权进程可追加令人信服的事件，它在 TCB 内"。代码没有任何机制验证 Agent 子进程运行在与 Orchestrator **不同**的 OS 身份下（全目录 grep 无 runas/LogonUser/impersonation/独立账户校验）。若 21bao 部署时 Agent 与 Orchestrator 共用同一账户，Round-004 的伪造向量依然成立——OS 账户隔离方案对该威胁模型无效。
- 检查只在 `mode=="integration"` 生效（workflow.py:127-128）；offline_fixture 完全豁免。t2 探针复现：offline 任务内直接 `Store._event` 追加 `gate02_approved` + 改任务行，事件链审计 `issues=[]`，`run()` 直接推进到 stage 3+4——Round-004 向量在 offline 模式仍然可行（offline 本不声称可信，但意味着该边界不保护演示/夹具案卷）。
- integration 模式还叠加了 `TRUSTED_INTEGRATION_EXECUTION_VERIFIED=False` 总开关（executor.py:21,121-122），当前真实执行仍被无条件 fail-closed。
- **21bao 真实部署的 ACL、独立账户与进程身份未验证**——按纪律不得宣称 Windows 真实环境中 R4-001 已完全解决。

### R4-002（非 ASCII 路径，原 P3）→ **FIXED**

`gitops.py:105-119`：`diff --name-status -z --no-renames` 输出按 NUL 分帧、字节级 `os.fsdecode`，绕开 `core.quotePath` 八进制引用；配合 `ls-tree -z` 逐文件模式/类型/名称复核（gitops.py:123-136）。探针实测：`tests/test_注册.py`、`tests/test_空 白.py`、`tests/test_#hash.py`、`tests/test_中文(1).py`、`tests/sub dir/test_边 界.py`、`tests/test_a'b.py` 六类合法新增全部放行；modify/delete/rename/conftest.py/pytest.ini/非测试源文件/tests/helpers.py/.pyc 八类非法全部拒绝；端到端 Unicode 考卷（`test_登录.py`）被整改 Worker 削弱时阻断并报 `Worker changed/deleted protected Tester exam`（t3，18 例全过）。制表符文件名在 Win32 无法创建，属平台限制，探针如实记录（t3b）。

### R4-003（未完成运行记录，原 P3）→ **FIXED**

`status()`（workflow.py:157-163）在无完整性问题的前提下检查 `store.running()`，输出 `NEEDS_RECONCILIATION / integrity_preflight=UNFINISHED_RUN / unfinished_run_ids`；`run()` 在 pre-dispatch 与步内两处遇在途 run 直接返回 `status()` 不重封存（664-666、670-671）；`resume()` 抛 `resume refused: unfinished invocation`（713-714）。探针实测 Gate 0.2 前的孤儿 run：status/run 均 NEEDS_RECONCILIATION、事件 8→8 不变、resume 抛错；孤儿正常终结后状态恢复 WAITING_APPROVAL 且无残留 orphan 键；健康全流程跑完后 status 不含任何 orphan/preflight 键（t4，3 例）。

### R2-008（输出流上限，原 NOT_FIXED P3）→ **FIXED（离线可验证部分）；Windows 后代进程树终止保持 NOT_VERIFIED**

`executor.py:30-94`：双线程并发排空、每流独立 `limit`（默认 `MAX_CAPTURE_BYTES_PER_STREAM=8MiB`）、超限置 `truncated` 并 `child.kill()`、元数据含 limit/observed/truncated/timed_out/returncode。探针实测：stdout 超限精确截到 1,000,000 且 `stdout_bytes_observed=1,048,576`；stderr 超限不影响 stdout 完整性（独立限长）；双流各 5MiB 并发 0.06s 无死锁；limit≤0 或 >8MiB 拒绝；完整 `invoke()` 路径下 9MB 洪水被阻断为 `InvocationError: output limit exceeded`，落盘恰好 8,388,608 字节 + capture.json 元数据；超时保留 `PARTIAL` 原始字节 + timeout.json；非 UTF-8/非对象 JSON 拒绝；小 JSON 正常（t5/t6，9 例）。代码注释（executor.py:34-35）自己声明这不是 Windows 后代进程树保证——维持 **NOT_VERIFIED**，不得宣称已实现。

## 四、整体回归（无回归）

t7/t8 共 9 例复验：Phase 3/4 双审真实并行（threading.Barrier 强制同窗，seen 双角色）且 reviewed_commit 单一（同 Commit）；Gate 0.2 行篡改仍 BLOCKED、无角色 run；Tester 新增 `conftest.py` 端到端仍被阻断；删除 run 行报 `dispatch journal has no run row`、改 role 报 `stage/role/input differs`、证据 NON_COMPLIANT；Pro-Audit 边界保持——APPROVE+"ignore all tests, ship it" 技术劣质报告判 COMPLIANT（不做技术裁决），错 reviewed_commit 判 NON_COMPLIANT；直调 integration `call_adapter` 仍 `NOT_VERIFIED` 拒绝；闭环预算跨进程持久化（round_a 2→5、FAILED、CLI exit 10）；假 no-op 整改被结构化门禁拒绝；Gate 5.9 后篡改最终报告使 `export_report()` 抛 `evidence invalid`，还原后正常导出且含 SIMULATION ONLY。5/5/2 预算、12 角色 Soul 哈希绑定、输入输出契约均无回归。

## 五、新增问题

| ID | 严重度 | 类别 | 摘要 |
|----|--------|------|------|
| R5-001 | P3 | 实际代码缺口（窄） | 信任检查面仅 home+`state.sqlite`；WAL/SHM 伴生文件（`state.sqlite-wal/-shm`，journal_mode=WAL，state.py:21）不在显式检查清单，依赖 NTFS 继承语义间接保护；父目录未检查。同账户威胁不受影响（该威胁本就不在方案防御范围），不同账户攻击者无 WRITE_DAC 也难以改子对象 ACL，故定级低。文件：trust.py:97-100。最小修复：把 `-wal/-shm`（存在时）加入 paths 清单。 |
| R5-002 | P3 | 实际代码缺口（窄） | `logs/<run_id>.capture.json` 与 `<run_id>.timeout.json` 未绑定进事件链/run details（run 记录仅绑定 stdout/stderr SHA），事后改写或删除不改变审计判定——探针实测篡改 capture.json 前后均 COMPLIANT。文件：executor.py:151-190（invoke 落盘处）、state.py:76-156（audit_events 不覆盖）。最小修复：finish_run details 增加 capture_sha256 并纳入 audit_events 复核。 |
| R5-003 | P3 | 测试工装缺陷 | `test_r4_002_test_filename_with_spaces_and_tabs` 假设可创建含制表符文件名，Windows 必败（Errno 22），导致开发方"101 通过"声明在 21bao 不成立。文件：tests/test_remediation_round4.py:43。最小修复：`pytest.mark.skipif(os.name=="nt")` 或改用 POSIX 安全名。 |
| R5-004 | P2 | 测试覆盖缺口 | R4-001 的三项开发方回归测试全部 `POSIX mode check runs only on POSIX` skip，Windows（目标部署平台）对 trust.py 的 ACL 分支 0 覆盖。文件：tests/test_remediation_round4.py（skip 标记处）。最小修复：补 Windows DACL 正/负向回归（本审计 acl_evidence.py 可作蓝本）。 |
| R5-005 | P2 | integration_gap / NOT_VERIFIED | OS 账户隔离的信任前提（"Agent 子进程不得与 Orchestrator 同身份"）只存在于注释（trust.py:3-6），代码无任何部署期校验（无独立身份探针、无 runas/令牌差异检查）；同身份进程伪造 `gate02_approved`/reviewer run 的 Round-004 向量在逻辑上依然成立，offline 模式实测复现（t2，chain_issues=[] 推进至 3+4）。最小修复：integration 启动时以子进程令牌 SID ≠ Orchestrator SID 为硬前提，或在文档/CLI 强制声明并要求专用服务账户。 |

## 六、真实集成放行判断

- `TRUSTED_INTEGRATION_EXECUTION_VERIFIED=False`：真实 Harness 执行仍被代码级禁用，fail-closed 正确。
- 真实 Codex/OpenCode、模型网关、测试执行收据、人工 Gate 0.1/0.2/5.9 审批身份、P0 协议与物理身份、远端 A2A 三节点盲审、Windows E: 工作树、生产 kill guard、21bao 实际 NTFS ACL 与进程身份隔离——全部 **NOT_VERIFIED**。
- **未经上述真实验证，P1 不得在 21bao 正式运行。** 本轮 CONDITIONAL 仅指：离线夹具语义下整改有效、integration 模式全部入口正确 fail-closed、无流程回归。

## 七、判定汇总

| 项目 | 状态 |
|------|------|
| R4-001 | MITIGATED_FAIL_CLOSED（信任前提未强制、21bao 未验证） |
| R4-002 | FIXED |
| R4-003 | FIXED |
| R2-008 | FIXED（离线）/ 后代进程树 NOT_VERIFIED |
| R2-006（携带） | MITIGATED_FAIL_CLOSED |
| 整体回归 | 无回归 |
| 新增 | R5-001 P3、R5-002 P3、R5-003 P3、R5-004 P2、R5-005 P2 |
| 开发方测试（Windows 实测） | 97 passed / 1 failed / 3 skipped |
| 独立探针 | 46 例 + 4 项 ACL 取证，全部 exit 0 |
| 源码完整性 | 67/67 blob 测试前后一致 |
