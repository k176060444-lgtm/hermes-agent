# Step 2: paste this prompt into a fresh ChatGPT session for 21bao integration

我们继续 **Hermes Coding Pipeline P1的第二步：21bao真实Agent配置与系统对接**。第一步已经由另一个Session完成P1硬编排内核源码，并发布到GitHub待审。请不要重做P1状态机，更不要把废弃的vibe-coding-repo拿来作为代码依据。请先只读检查源码、审计结论和当前21bao环境；在我明确批准之前绝不直接修改实际Hermes/Codex/OpenCode配置、启动付费模型、修改任何生产目录。

P1源码：GitHub `k176060444-lgtm/hermes-agent`，分支 `feature/p1-coding-pipeline-20261104`，目录 `experiments/hermes-coding-pipeline-p1/`。

独立审计报告：`experiments/hermes-coding-pipeline-p1/audit_evidence/P1/round-XXX/`。请先检查最新已审的确切commit、缺陷修复状态，确认源代码是否已经通过独立审计；若仍有BLOCKER，先只读报告并要求修复，不要进行实际集成。

## 系统边界

- **Hermes就是Orchestrator**：负责与我理解意图、确认目标，管理已经获批的角色矩阵，触发P1，并通知我进度和异常。P1是给Hermes用的程序化硬状态机，不另造一个聊天Orchestrator。
- **P2暂不实施**：我与Hermes前期意图对齐、默认矩阵呈报与人工修改将来由P2固化。P1目前只接收两份已批准产物（用户需求、12角色Harness+模型矩阵）以及Gate0.1审批依据。
- **P1范围**：Phase0.2 Planner开始，Gate0.2仍需我人工冻结规格，后续自动依序执行至Gate5.9呈报完整仲裁及合规报告并等待我上线批准。P1严禁触碰Phase6生产部署和Phase7清理。
- **实际节点**：21bao为Windows主机，Planner/Worker/Spec/Quality/TesterA/Worker整改/TesterB/Arbitrator/Pro-Audit都在21bao上。5bao、9bao、rusty为Debian三盲审候选，A2A逻辑由另外的P0 Session开发；此Session只实现经审计的P0接口适配，不修改P0或远端节点。
- **阶段审查变更**：Phase3 Spec与Phase4 Quality**并发执行**，同一个Git Commit和TASK_SPEC SHA，独立报告和合规审计，双审汇合后才进入Tester Gate A。
- **Agent Soul**：12角色职责、输入/输出与行为边界应作为Codex/OpenCode各自适用的本地Agent/Soul配置（加载方式依实际已装版本验证），Hermes只按任务批准矩阵调用对应角色、Harness和模型。矩阵从配置文件读取且冻结，不能硬编码主备模型。权限以Soul规则及Git/SHA事后审计为轻量设计，不主张P1必须开发复杂的操作系统级隔离，但必须承认无法检测写后恢复等剩余风险。
- **合规审计**：每个Phase完成后检查批准矩阵、职责和前后版本、原始日志、必要上下游交付，不审业务代码技术优劣，不因为小排版问题阻断。Pro-Audit最终汇总在Phase5.85。闭环预算：5 / 5 / 2，全局持久化，不能重启重置。
- **A2A**：P1只调用外部盲审器；至少2台真正不同物理节点有效报告，第三席最多额外等600秒。缺真实身份和commit绑定证据必须阻断，不得模拟放行。

## 本次请先完成的只读盘点

1. 21bao当前Windows系统、Hermes版本和真实安装目录（以实际读到的为准）、是否存在同名多个Hermes profile、Gateway是如何启动和受控的；不要仅依据过去记忆。
2. Codex、OpenCode各自CLI路径、版本、权限模型、原生Agent/Soul加载方式、模型选择方式、当前已授权模型（不输出凭据）。
3. 是否能在两个Harness之间按同一Approved Role Matrix调用指定模型；每个角色如何无冲突存储Soul，是否可以从P1 `souls/*.md`生成对应原生配置；对`reviewed_commit`、TASK_SPEC SHA的真实传递方式。
4. 每个Harness的非交互执行、真实输出/原始工具日志、退出码与会话ID、取消/超时和重启对账能力；针对Windows PowerShell/Git worktree/E盘盘符的可靠参数处理。
5. Hermes如何调用P1命令（可选择薄插件或本地受控Tool）；阶段进度/审批如何返回Hermes；不能在Hermes本身重启后丢失后台任务。
6. P0盲审外部接口是否已有经过验收的稳定版本；如果没有，明确列出需要另一个Session确认的接口字段与来源，不要自行编造。
7. 检查P1当前实现`docs/KNOWN_LIMITATIONS.md`，识别哪些缺陷必须在接入前修复，哪些属于可后续优化。

请输出**只读调研报告 + 可实施的具体对接方案 + 配置差异草案 + 风险清单 + 详细离线/真实验收步骤**，在我审批后才允许实机修改配置及启用真实执行。不要提前替我选择模型，不要直接部署，不要调用付费模型测试。
