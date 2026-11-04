# Hermes Coding Pipeline P1 — Round-007 独立审计报告

- 审计状态：**COMPLETE**
- 代码结论：**CONDITIONAL（有条件通过；离线/信任语义整改全部落地，真实集成仍未验收）**
- 仓库：`k176060444-lgtm/hermes-agent` / 分支 `feature/p1-coding-pipeline-20261104`
- 固定审计源码 Commit：`cda5f4873c253d5926c86d84b7ada138427b9bc7`（parent = Round-006 报告 Commit `6d301638043f61c68e3f76aeafa94b01b30229ba`，tree `3b3dee4967a59d21ddd428389d939aa2bf8fe76e`）
- 审计执行环境：21bao（Windows 10 本机隔离 scratch，离线）；Python 3.11.15、git 2.54.0、PowerShell 5.1
- 日期：2026-11-04（中国标准时间）

## 一、方法与完整性

1. 按固定 Commit 的 Git tree 取回 P1 目录全部 **81 个文件**（上轮 74，+7）；逐文件 Git blob 校验**测试前后均 81/81 一致、0 不匹配**。
2. 本轮产品代码净变更仅 `p1/trust.py`（+README/KNOWN_LIMITATIONS 文档、+`tests/test_remediation_round6.py`）——executor/workflow/state 未动。
3. 原项目测试在快照上原样执行（15 批 114 项），Windows 全套件 **0 失败**。
4. 独立对抗探针 63 例 × 8 组（R6-001 独立复现 12 例 + 携带回归 51 例）全部 exit 0。所有 Set-Acl/icacls/owner 变更只作用于 pytest tmp_path 或审计方新建一次性目录，用后即删；未触碰真实 Hermes/P1 任务目录、系统策略、远端节点。
5. 未调用真实付费模型，未连接 5bao/9bao/rustyhand。

## 二、R6-001（本轮核心）：Windows SQLite WAL 生命周期 → **FIXED**

**实现核验**（`p1/trust.py:66-81`）：`_windows_validate` 仅要求第 0 条记录（任务根，`paths[0]` 恒为 home，由 `validate_private_task_home:113` 保证）`AreAccessRulesProtected=True`；**每个**对象（含继承而来的子文件）仍强制 owner==当前 SID、有效 Allow 主体（`GetAccessRules($true,$true)` 展开继承后）⊆ {当前 SID, S-1-5-18, S-1-5-32-544}；新增记录 path 逐位比对（trust.py:67-68）防记录错序混检；任何 PS 非零/坏 JSON/基数不符/超时 → fail-closed（trust.py:61-83）。无任何 ACL 写操作，查询脚本仍只读（上轮 spy 断言复验通过）。

**审计方真实 Windows 独立复现**（不采信开发方声明，r7 组）：

| 场景 | 结果 |
|------|------|
| 仅保护根（Purge+禁继承+me (OI)(CI)F）→ SQLite journal_mode=WAL 自然创建 db/-wal/-shm（icacls 实录子文件携带 `(I)` 继承副本、仅 KK 一个主体）→ `validate_private_task_home` | **ACCEPTED**（R6-001 复现点：上轮同场景永久 REJECTED） |
| clean close → reopen → 写数据（WAL 存续/重建两种分支均覆盖）→ 再次 validate | **ACCEPTED throughout**，生命周期可运行 |
| 给 -wal 加 Everyone Read | **REJECTED** 'grants access to other principals' |
| 给 -shm 加 Everyone Read | **REJECTED** |
| 给 -wal 加 AuthenticatedUsers（S-1-5-11） | **REJECTED** |
| logs 证据子目录带自身 Everyone ACE | **REJECTED** |
| 根目录 `icacls /reset` 恢复继承 | **REJECTED** 'NTFS task root inherits permissions'（根检查仍是硬闸） |
| 子库文件真实改 owner（SetOwner 另一 SID，本机成功执行） | **REJECTED** 'not owned by current identity' |
| -wal 替换为符号链接 | **REJECTED** 'private task state path missing or linked'（先于 ACL 查询） |
| PS 响应缺项/换序/坏 JSON/非零退出 | 全部 **fail-closed** |

**未放宽验证**：允许清单 {me, SYSTEM, Administrators} 与上轮完全一致（trust.py:27），本轮仅放宽"子对象禁继承标志"这一项**不可满足的形式要求**，所有实质主体/属主判定原样保留；Everyone、AuthenticatedUsers 等真实未授权主体在子对象上仍被拒（实测 3 组）。Administrators/SYSTEM ACE 被接受属**沿用的已声明 TCB 前提**（README:111-118、KNOWN_LIMITATIONS:56-71 均如实标注），非本轮新增放宽，随 R5-005 一并披露。

**开发方指定测试**：`tests/test_remediation_round6.py` 6 项全部在 21bao Windows **真实执行且 PASS**，其中 `test_r6_001_real_windows_sqlite_wal_recreation_under_protected_root`（time=1.281s，非 skip）与审计方独立复现互相印证。Linux 结果（开发方 112/2）未被引用为 Windows 证据。

## 三、其他问题复核

- **R6-002** → **维持已记录范围观察（documented NOT_FIXED，可选增强）**：`logs/` 目录**内部**单文件带自身 Everyone ACE 不被枚举（r7 复测与上轮一致）；缓解链不变——非 TCB 主体既无法穿越受保护私有目录、也无 WRITE_DAC/所有权改动子文件 ACL，内容已被 capture/run 三重哈希绑定。开发方在 ROUND_006_REMEDIATION.md:13 明示未修，文档未谎报。按实际影响维持 P3 informational，**不升级不降级**。
- **R5-005** → **MITIGATED_FAIL_CLOSED 不变**：executor.py:129 无条件独立 gate 复验（r6b_gate：旧 flag 强开 + 完全合规 adapter + `isolated:true` 布尔 → 仍拒绝、零副作用）；真实独立身份执行器/token SID 认证仍不存在，offline `Store._event` 伪造在夹具模式仍可行（声明非证据）。
- **R2-006** → **MITIGATED_FAIL_CLOSED 不变**：直调 A2A 仍 NOT_VERIFIED 拒绝；无 P0 线路/物理身份收据。
- **R4-001**（携带母项）：五个入口 trust 检查、fail-closed、不重写可疑状态——复验通过（r6b_trust：BLOCKED、0 dispatch、事件 1→1、persisted 保留）。

## 四、整体回归（0 回归）

51 例回归全绿：Phase 3/4 Barrier 真实并行且 reviewed_commit 唯一；Gate 0.2 行篡改 BLOCKED；conftest 端到端阻断；Tester 考卷保护（Unicode 考卷被整改 Worker 削弱 → NON_COMPLIANT）；run 行删除/role 篡改被链捕获；5/5/2 预算跨进程持久化（2→5、FAILED、CLI exit 10）；假 no-op 拒绝；Pro-Audit 边界（劣质技术报告 COMPLIANT / 错 commit NON_COMPLIANT）；capture 绑定回归（伪造 timed_out 收据、同步 stdout 交换、RUNNING 在途区分）全部保持；路径电池（中文/空格/#/()/引号放行，8 类非法拒绝）；孤儿 run reconciliation 三态；流上限 7 例；离线路径边界。

## 五、新增问题

| ID | 严重度 | 类别 | 摘要 |
|----|--------|------|------|
| R7-001 | P3（informational，非阻断） | 实现耦合观察 | "根"的判定依赖 `index==0` 位置语义（trust.py:76）：正确性由两条现有防线兜住——生产入口 `validate_private_task_home` 固定 `paths[0]=home`（trust.py:113）+ 逐位 path 比对（trust.py:67）；但若未来有人直接以其它顺序调用 `_windows_validate`，根检查会退化为子对象规则。最小建议：把 root 作为显式参数传入或在 PS 响应里核对专用标记。 |

## 六、真实集成放行判断

- integration 仍双重 fail-closed（`TRUSTED_INTEGRATION_EXECUTION_VERIFIED=False` + executor.py:129 无条件 gate）；本轮无任何实际 Coding Agent 被调用。
- 保持 NOT_VERIFIED：独立身份执行器与 SID 认证（R5-005）、21bao 生产环境账户/ACL 实际 provisioning、真实 Harness/模型/测试收据、人工 Gate 0.1/0.2/5.9 审批身份、P0 协议与物理身份、远端三节点 A2A、Windows 后代进程树终止、E: 工作树与生产 kill guard。
- **未经上述验收，禁止宣称 P1 可在 21bao 正式运行。** 本轮 CONDITIONAL 的含义：R6-001 在真实 Windows 上已修复并双重验证（信任边界首次具备可部署性），全部回归保持，无任何新增阻断缺陷。

## 七、判定汇总

| 项目 | 状态 |
|------|------|
| R6-001 | **FIXED**（21bao 真实 NTFS/SQLite 生命周期独立复现通过） |
| R6-002 | 已记录范围观察（documented NOT_FIXED，P3 informational，不升级） |
| R5-005 | MITIGATED_FAIL_CLOSED |
| R4-001 | MITIGATED_FAIL_CLOSED（可部署性部分随 R6-001 落地） |
| R2-006 | MITIGATED_FAIL_CLOSED（携带） |
| 新增 | R7-001 P3 informational |
| 回归 | 0 |
| 项目套件（Windows 实测） | 114 collected / **110 passed / 0 failed / 4 skipped**（skip 全部为合法 POSIX-only 或按平台正确跳过的 tab 文件名用例） |
| 指定测试 | test_remediation_round6.py 6/6 真实执行 PASS（含 Windows WAL 生命周期用例） |
| 独立探针 | 63 例 × 8 组全部 exit 0 |
| 源码完整性 | 81/81 blob 测试前后一致 |
| 夹具披露 | 审计方 2 处探针缺陷（sqlite3 `with` 未关连接锁住 WAL；rc1 消息文本预期），修正后重跑取证；产品代码全程零修改 |
