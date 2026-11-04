# P1 Coding Pipeline — Round-003 独立审计报告

**AUDIT_STATUS: COMPLETE**　　**代码结论: FAIL（窄幅）**　　**真实 21bao 集成: 不允许**

- 审计源码 Commit: `2fd65c1269dcb29391ffac1579745c1dddfe04f5`（父提交 `541c25a20334b9cb1c77fe7bb34a2e13965eaeeb`，tree `b6ab42d1cc0e2ad5613e69df0111064cd8fef36b`）
- 分支: `feature/p1-coding-pipeline-20261104`；目录: `experiments/hermes-coding-pipeline-p1/`
- 审计时间: 2026-11-04T17:15:00+08:00 → 2026-11-04T18:05:00+08:00（UTC+08:00）
- 方式: 只读源码 + 隔离目录原样测试 + 独立对抗探针；未连接真实 P0、远端 A2A、付费模型或现网配置。
- 本报告只新增 Round-003 审计文件，不修改 P1 源码、Soul、测试或 Round-001/002 报告。

## 1. 结论摘要

本轮复核 19 项（Round-001 未解决 7 项 + Round-002 新问题 12 项）：**FIXED 17、MITIGATED_FAIL_CLOSED 1、NOT_FIXED 1、REGRESSION 0、NOT_VERIFIED 0**。
整改质量显著提升：Round-002 的所有直接可复现向量均被关闭，64 项测试原样通过；R2-008 仍是已知的 P3 非阻断增强项。
本轮另发现 **3 项新问题：P0 0、P1 0、P2 2、P3 1**。其中 R3-001（Tester 新增 `tests/conftest.py` 可禁用既有考卷后仍到达 Gate 5.9 COMPLIANT）与 R3-002（删除 run 行/改 stage-role 不被事件链检测）属于实质缺陷，因此本轮判 **FAIL（窄幅）**；这不否定 18 项已修复结论。

## 2. 审计方法与证据边界

- 通过 GitHub tree/blob API 固定 52 个文件，逐个以 Git blob SHA-1 与大小复核；审计前后均 **52/52 匹配，0 错误**。
- 原项目测试原样运行：**64/64 passed，0 failures，0 errors**，分 8 批，JUnit 见 `testlogs/batch0..7.xml`。开发方“64 项通过”的声明被独立确认。
- 独立探针位于 `probe-copy/`：**19 个不重复用例 / 20 次执行，全部 exit 0**。探针断言“观察到某行为”，因此通过不等于产品验收。
- 另有 2 项补充检查：CRLF/clean-filter 仓库不被误判；4 连接 × 150 对 start/finish（600 runs）并发压测 0 异常、0 链错误。后者不证明不存在所有竞态。
- 所有 SQLite/run 行篡改探针均以“本地 state.sqlite 可写”为前提；Git 探针仅作用于一次性 worktree；未使用真实模型、P0 或远端节点。

## 3. 逐项复核（19 项）

| ID | 原严重度 | 本轮状态 | 代码证据（文件:行） | 独立验证 |
|---|---|---|---|---|
| P1-004 | P0 | FIXED | p1/gitops.py:21-41,44-78; p1/workflow.py:183-184,202-207 | test_hidden_index_flag_worker_cannot_reach_gate59[--assume-unchanged/--skip-worktree] |
| P1-006 | P1 | FIXED | p1/workflow.py:208-217,467-474; p1/audit.py:43-51 | test_tester_gate_a_cannot_delete_baseline_exam; test_tester_gate_b_cannot_weaken_gate_a_exam |
| P1-015 | P0 | FIXED | p1/workflow.py:666-679; p1/state.py:76-132 | test_resume_tampered_a2a_state_is_refused_without_sealing |
| P1-016 | P1 | FIXED | p1/state.py:99-132,141-148; p1/workflow.py:479-504 | test_run_details_and_stdout_rewrite_is_noncompliant |
| P1-017 | P1 | FIXED | p1/gitops.py:25-41,81-90 | test_hidden_index_flag_worker_cannot_reach_gate59 |
| P1-019 | P1 | FIXED | p1/workflow.py:150-163,640-643 | test_replay_after_remediation_commit_needs_reconciliation |
| P1-022 | P1 | FIXED | p1/workflow.py:348-362; p1/audit.py:54-57 | test_structured_noop_valid_passes_and_keyword_fake_fails; test_keyword_only_noop_is_rejected; test_noop_with_actionable_blind_finding_is_blocked |
| R2-001 | P1 | FIXED | p1/workflow.py:208-217,467-474; p1/audit.py:43-51; p1/gitops.py:97-109 | test_tester_gate_a_cannot_delete_baseline_exam; test_tester_gate_b_cannot_weaken_gate_a_exam |
| R2-002 | P1 | FIXED | p1/workflow.py:666-679 | test_resume_tampered_a2a_state_is_refused_without_sealing |
| R2-003 | P1 | FIXED | p1/state.py:99-132,141-148 | test_run_details_and_stdout_rewrite_is_noncompliant |
| R2-004 | P1 | FIXED | p1/workflow.py:348-362 | test_structured_noop_valid_passes_and_keyword_fake_fails |
| R2-005 | P2 | FIXED | p1/contracts.py:106-115,118-168; config/gate01.template.json:9 | test_soul_mutation_breaks_gate01_binding |
| R2-006 | P2 | MITIGATED_FAIL_CLOSED | p1/a2a.py:29-48,66-69,85-87 | test_a2a_collection_rejects_bad_report_and_roles |
| R2-007 | P2 | FIXED | p1/executor.py:49-53; p1/a2a.py:31-39 | test_executor_uses_frozen_adapter_not_task_pointer |
| R2-008 | P3 | NOT_FIXED | p1/executor.py:84,87-94 | 静态检查（未注入超大输出） |
| R2-009 | P3 | FIXED | p1/workflow.py:412-415 | test_a2a_terminal_diagnostic_is_journaled |
| R2-010 | P3 | FIXED | p1/workflow.py:71-78,378-383 | test_partial_initialization_is_cleaned_and_retryable; 开发者 test_round2_invalid_safety_rejected_at_initialization |
| R2-011 | P3 | FIXED | p1/workflow.py:100-110 | test_partial_initialization_is_cleaned_and_retryable |
| R2-012 | P3 | FIXED | p1/a2a.py:16-34 | test_direct_a2a_library_call_fails_closed |

### 3.1 仍未修复 / 部分关闭

**R2-008（P3 / NOT_FIXED，非阻断）** 超时与正常路径的 stdout/stderr 仍无大小上限。`executor.py:84,87-94` 使用 `capture_output=True` 与无上限 `atomic_write`；开发方已在整改文档中明确列为未修。建议在真实长时运行前改为流式读取、限长并记录 truncated 标志。该问题不影响本轮对逻辑门禁的判定。

**R2-006（P2 / MITIGATED_FAIL_CLOSED）** report 类型与 `blind_roles` 绑定已修复；但 adapter 原始 stdout/stderr 仍未保存为传输证据，真实 P0 身份/协议也未接入。integration 仍硬阻断，故只是正确 fail-closed，不是完整修复。

### 3.2 已修复项（17）

Round-001：P1-004、P1-006、P1-015、P1-016、P1-017、P1-019、P1-022。
Round-002：R2-001、R2-002、R2-003、R2-004、R2-005、R2-007、R2-009、R2-010、R2-011、R2-012。
每项均有本报告的独立探针或原回归测试作为证据；直接向量关闭不等于真实集成可信，见第 7 节。

## 4. 新增问题（3）

### R3-001 [P2] [code_defect] Tester 可新增 tests/conftest.py 等收集控制文件，禁用既有考卷后仍到 Gate 5.9 COMPLIANT

- 文件/行号：`p1/gitops.py:144-146 (test_path), p1/gitops.py:97-109 (add-only transition), p1/audit.py:43-51, p1/workflow.py:208-217`
- 证据：独立探针：Tester A 新增 tests/conftest.py（内容 collect_ignore_glob = ["test_*.py"]）并提交；test_commit_transition 视为合法新增，audit_role 因该路径不在 before 中而不报错；流水线到达 WAITING_GATE_5_9，verify_evidence=COMPLIANT。
- 影响：Tester 只需新增一个 conftest.py 即可让既有全部考卷在后续测试收集中被忽略；“Tester 只能新增、不得削弱考卷”的保护被绕开，且无需本地 DB 写权限。
- 复现：probe-copy/tests/test_round3_independent.py::test_defect_tester_conftest_can_disable_existing_exams（exit 0，断言复现）。输出：status=WAITING_GATE_5_9 conftest=True evidence=COMPLIANT。
- 最小修复建议：新增白名单限定为 tests/test_*.py（或根级 test_*.py）；显式拒绝 conftest.py、pytest.ini、tox.ini、setup.cfg、pyproject.toml、__init__.py、sitecustomize.py 等会影响收集/导入的文件；如确需辅助模块，走单独审批清单。

### R3-002 [P2] [code_defect] 删除 run 行或改写其 stage/role 不被事件链检测，证据核验仍 COMPLIANT

- 文件/行号：`p1/state.py:99-132 (audit_events), p1/state.py:141-148 (finish_run)`
- 证据：独立探针：Gate 5.9 后删除一条已完成 spec_reviewer run 行，并把另一 run 的 stage/role 改为 9/forged_role；audit_events=[]，verify_evidence=COMPLIANT。事件链仍保留被删除 run 的 dispatch/finish 事件，但校验只遍历现存 runs，未做事件→run 反向核对，也未比对 stage/role。
- 影响：有本地 DB 写权限者可抹去一次执行记录或伪造其阶段/角色，而不触发事件链错误；证据完整性保证不覆盖“删除”和“元数据替换”。
- 复现：probe-copy/tests/test_round3_independent.py::test_defect_deleted_run_row_and_role_metadata_not_detected（exit 0）。输出：issues=[] evidence=COMPLIANT。
- 最小修复建议：在 audit_events 中反向核对：每个 execution_dispatched/execution_finished 的 run_id 必须存在于 runs；run 的 stage/role 必须与 dispatch 事件一致；run 缺失即报错。

### R3-003 [P3] [hardening] run() 完整性预检失败只返回 BLOCKED，不落盘状态；status 仍显示旧状态

- 文件/行号：`p1/workflow.py:606-615`
- 证据：独立探针：篡改 5.0 任务行后调用 run()；返回 status=BLOCKED，但 p.status() 仍为 WAITING_EXTERNAL，事件数不变。
- 影响：CLI 退出码 11 与 status 命令显示的状态不一致，运维可能误判；该行为是为保留取证链而故意不写任务行，属可用性/一致性问题，不构成安全绕过。
- 复现：probe-copy/tests/test_round3_independent.py::test_observation_integrity_block_not_persisted（exit 0）。
- 最小修复建议：在只读 preflight 结果中明确区分“持久状态”和“本次预检阻断”，或写独立 forensic 日志；不要为状态一致性改写被篡改的任务行。

> 严重度说明沿用项目 `KNOWN_LIMITATIONS.md`：P0=Gate 0.2/5.9 绕过、伪造 PASS、假 Quorum、生产修改；P1=预算/汇合/角色模型错误、实质性证据破坏；P2=缺失校验、产物/角色来源错误、Windows 兼容性弱；P3=风格/可选增强（不阻断）。
> R3-001 为 P2：它绕开“Tester 只能新增测试”的完整性约束，但 Gate 5.9 仍需人工批准，真实测试收据本来也未接入。R3-002 为 P2：需本地 DB 写权限，且不改变已登记的 report/audit 文件。

## 5. 关键流程规则复核

| # | 检查项 | 结论 | 证据 |
|---|---|---|---|
| 1 | Gate 0.2 有效人工审批 + 冻结规格 | 结构 PASS；身份 NOT_VERIFIED | `workflow.py:588-604` 要求 actor/approval_id/spec SHA；`contracts.py:118-168` 原子冻结并绑定 Soul 清单。actor 仍是字符串。 |
| 2 | Phase 3/4 真正并行、同一 Commit、独立报告与审计 | PASS | `workflow.py:248-296` ThreadPoolExecutor；屏障探针两角色同时进入、同一 SHA、两条独立 audit 记录。 |
| 3 | Gate A 严格核对双审与 Tester 结果 | 结构 PASS；测试真实性 NOT_VERIFIED | 双审均 PASS 才进入 4.5（294-296）；Tester 要求 GATE_A_PASS/PASS。真实测试执行收据未接入。 |
| 4 | 5/5/2 预算与持久化 | PASS | `_retry_a` 5（298-302）、`_retry_b` 5（304-308）、`_violation` 2（150-154）；原回归 `test_local_loop_five_rounds_stops`、`test_gate_b_five_rounds_hard_stop`、`test_noncompliant_reviewer_retrace_max_two` 全部通过。 |
| 5 | Tester 考卷在整改过程中保持完整 | 直接向量 PASS；新增绕过 FAIL | 删除/改写既有或受保护考卷被拒；但新增 `conftest.py` 可禁用考卷（R3-001）。 |
| 6 | A2A 只走外部接口、拒绝未核实盲审 | PASS（真实协议 NOT_VERIFIED） | `run()` integration 硬阻断（616-620）；`call_adapter` 库级也阻断（a2a.py:29-34）；`validate_collection` 绑定 report/blind_roles 并保留 NOT_VERIFIED。 |
| 7 | 仲裁使用正确上下游案卷 | 结构 PASS；读取未验证 | `workflow.py:310-324` 固定 task/commit/spec/matrix/evidence 哈希；`audit.py:65-69` 要求 case SHA。 |
| 8 | Gate 5.9 只输出已登记且完整性通过的报告 | PASS | `export_report` 只读仲裁与最终报告两个登记名并逐字节核对（687-708）；篡改导出被拒。 |
| 9 | 模拟数据不得当作真实集成 | PASS（正常入口） | `run()` integration 直接 BLOCKED；`audit.py:28-34` 拒绝 fixture/simulated；库级 A2A 也已关闭。 |
| 10 | 中断恢复、Git 版本与事件记录一致性 | 基本 PASS；删除/元数据缺口 R3-002 | resume 先校验后写（666-679）；run details 绑定事件（state.py:99-148）；但 event→run 反向核对与 stage/role 绑定缺失。 |

## 6. Pro-Audit 边界

未发现 Pro-Audit 越权做技术裁决。`audit.py:12-15` 明确只检查角色、矩阵、权限、Commit、规格 SHA 与交付形状；`workflow.py` 的最终合规只汇总阶段顺序、预算与证据完整性。新增 R3-001 属于“测试新增白名单”的实现缺陷，不是 Pro-Audit 在评价测试质量。

## 7. 真实执行与离线模拟

- 64 项项目测试与 19 个探针全部为离线 fixture、本地 Git 与本地 stub；没有真实 Codex/OpenCode、模型、付费调用、P0 或远端节点。
- `integration` 在 `run()`、`invoke()` 与 `call_adapter()` 三处均失败关闭；因此所有 “COMPLIANT” 仅表示离线流程内部一致，不等于真实执行可信。
- 本轮不声称 P1 已可在 21bao 运行；真实集成事项见下节。

## 8. 仍未验证的真实集成事项

- 真实 Codex/OpenCode 包装器、模型与网关物证
- 真实 P0 协议、原始传输收据、返回角色/主机绑定
- P0 物理身份认证与防伪 Quorum
- 真实测试执行收据（Gate A/B）
- 真实人工 Gate 0.1/0.2/5.9 身份与审批链
- Windows E: 集成工作树、真实崩溃/孙进程/kill 行为
- 真实副作用 kill guard / 生产隔离
- 对拥有完整本地 DB/日志重写能力的特权攻击者的外部信任锚

## 9. 最终结论

**FAIL（窄幅）。** 19 项原问题中 17 项已实质修复，1 项（R2-008）为非阻断 P3 增强；但 R3-001 与 R3-002 仍是可复现的实质缺口：前者允许 Tester 通过新增收集控制文件禁用考卷并取得 COMPLIANT 案卷，后者允许本地 DB 写者删除/篡改 run 元数据而不触发事件链。两者修复成本低，建议开发方修复后针对新 Commit 开展 Round-004。
在真实 Harness/模型物证、测试执行收据、P0 协议与物理身份、人工审批身份接入前，P1 不得进入 21bao 真实运行。

审计仅覆盖上述固定 Commit；分支后续变化不属于本报告结论。
