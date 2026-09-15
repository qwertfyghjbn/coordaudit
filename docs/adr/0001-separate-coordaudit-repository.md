# 0001. CoordAudit 作为独立项目

## 状态

Accepted

## 决策

将 CoordAudit 的 runtime、专用 pilot benchmark、hidden evaluator、测试、运行证据与研究设计迁入独立仓库。

## 理由

CoordAudit 归因的是 runtime coordination adapter；原仓库中已收口的 `Architecture Attribution Experiment` 归因的是 static-tool constraint strength。二者共享安全审计背景，但不是同一实验线，不能共享结果身份或版本冻结域。

独立仓库使 harness、prompt、tool schema、coordination adapter、budget、grader 和 benchmark digest 能以一个 commit 冻结。原 benchmark corpus 仍作为来源仓库，通过 remote、commit、case ID 和 hash 记录 provenance。

## 后果

- 新项目不运行时读取原仓库 sibling `datasets/` 目录。
- 原仓库保留 `datasets/`、canonical results、OpenAnt/DeepAudit/IRIS 资产，以及旧 Architecture Attribution 报告和 artifacts。
- 首次迁移保持 Python package 布局，避免把路径迁移与 runtime 重构混为一个处理。
