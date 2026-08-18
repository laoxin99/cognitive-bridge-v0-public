# 元力智脑 / YuanAI

> LLM 打开可能，元力智脑校准方向。

## 视频入口

两分钟英文介绍： [Why Is AI Becoming More Dangerous — and Why Intelligence May Begin Before Language?](https://youtu.be/4LL3pKtgA4Q)

## 从这里开始

如果第一次来到这里，建议按下面顺序查看：

1. [先看视频：AI 为何更危险？](https://youtu.be/4LL3pKtgA4Q) — 用两分钟了解问题背景。
2. [运行离线 demo](#运行) — 按命令复现一次路径改道。
3. [查看最小证据](MINIMUM_EVIDENCE.md) — 对照输入、输出和 replay 结果。
4. [查看公开边界](OPEN_SOURCE_BOUNDARY.md) — 了解本包公开与未公开的内容。
5. [返回元力智脑主页](https://laoxin99.github.io/index-zh.html) — 查看背景、入口和后续研究方向。
6. [提交问题或反馈](../../issues/new) — 请尽量附上复现命令、输出和环境。

这是一个面向机制型智能的公开研究入口。当前公开包聚焦一个可复核的最小问题：

```text
当反馈让原路径失效时，系统能否在既定目标和边界内重新选择路径，继续完成验收？
```

## CognitiveBridge-v0 做什么

CognitiveBridge-v0 是一个离线机制演示：外部模型或思想流只提供结构化候选，机制层负责边界检查、选择、反馈改道、低权限承接和回放校验。

```text
候选生成
→ 边界检查
→ 初始选择 B
→ 反馈暴露证据缺口
→ B 标记为偏离
→ 重选 C
→ 再次验收通过
→ 记录与 replay 校验
```

机器可核验的核心结果：

```text
selected_path = B
feedback = workflow_action_mapping_missing
path_status_B = deviated
revision_type = reselection
selected_path = C
validation_after_revision = passed
replay_verified = True
```

## 已验证范围

```text
离线 fixture 可运行
候选与边界检查
低权限 sink
反馈驱动的路径改道
改道后再次验收
JSONL 事件记录
确定性 replay hash 校验
```

## 运行

```powershell
python examples/run_path_revision_demo.py
python -m pytest tests -q -p no:cacheprovider
python -m compileall cognitive_bridge_v0
```

## 当前明确不声称

```text
不接入真实 LLM provider
不调用网络或 API key
不导入 V14 主链
不修改 ReactionCore
不写入 SystemState
不执行外部动作
不自主设定最终目标
不代表 AGI 已实现
不代表生产级 AI 安全方案
```

## 公开研究位置

这不是把智脑包装成已经完成的 AGI，而是先公开一个可以运行、测试和复核的机制原型。长期研究方向是：在既定目标、边界和反馈中，把方向判断、路径修正与受控执行转化为可检查的工程结构。
