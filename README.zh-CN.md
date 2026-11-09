# diff-viva（改动答辩）

[English](README.md) | **中文**

一个智能体技能：在有人合并或接手一段代码改动之前，先进行一场简短的“答辩”。它从 diff 中挑出风险最高的位置，向这段代码未来的负责人一次只问一个闭卷问题，严格打分并引用原话，最后给出回执：**OWNED**（已拥有）、**NOT_YET**（还没到位），或 **INTENT_MISMATCH**（回答表明代码并没有按负责人以为的方式运行）。

## 为什么需要它

智能体写代码的速度远超人能消化的速度。能编译、测试通过、顺利合并，可团队里没人说得清它的失败路径。“代码在做什么”和“负责人理解了什么”之间的差距会不断扩大，直到第一次事故。

Diff Viva 一次一个改动地缩小这个差距，还顺带抓 bug：当负责人信心满满地描述了一个代码并不具备的行为时，这场对话就在评审和生产环境之前发现了缺陷。

## 功能特点

- **问锚点，不问冷知识。** 每个问题都指向本次 diff 的某个文件和行：新增分支、错误路径、I/O、并发、边界、魔法常量、被删除的代码。
- **按风险分级。** 敏感路径和敏感行（鉴权、计费、迁移、令牌、金额）权重更高；档位决定要问几个锚点：routine 3 个、sensitive 5 个、critical 8 个。
- **五种问题类型**轮换使用：PREDICT 预测、BREAK 破坏、TRACE 追踪、WHY 取舍、EDGE 边界。
- **考官纪律。** 一条消息一个问题；对话闭卷、代码开卷；提问前先私下写好答案要点；答错时缩小追问而不是直接给答案；不吹捧。
- **严格打分，附带证据。** SOLID、PARTIAL、WRONG、SKIP、MISMATCH，每个分数都引用答辩人原话。讲解后马上答对，不能单独通过高权重锚点。
- **“意图不符”是正式结论。** 把一次误解变成一份带证据的 bug 报告。
- **过期保护。** 回执对改动行做哈希，基于旧 diff 的答辩会显示为 STALE。
- **适配 CI。** 回执是可以贴进 PR 描述的 Markdown，退出码可用于钩子拦截。
- **零依赖。** 一个只用标准库的 Python 脚本，附 25 个测试。

## 安装

要求：辅助脚本需要 Python 3.8+。技能本身是纯 Markdown，没有脚本也能用。

**Claude Code**

```bash
git clone https://github.com/fangdididi/diff-viva ~/.claude/skills/diff-viva
```

**Codex / 其他读取 skills 目录的智能体**

```bash
git clone https://github.com/fangdididi/diff-viva ~/.codex/skills/diff-viva
```

**Cursor**：克隆到项目里（例如 `.cursor/skills/diff-viva`），用一条规则指向 `SKILL.md`；或者在合并前让智能体先读它。

**没有 skills 目录的聊天助手**：把 `SKILL.md` 的正文粘贴到对话或自定义指令里，再贴上你的 diff。

## 使用方法

对智能体说：

- “合并前给这个 diff 做个答辩。”
- “就智能体刚改的东西考考我。关卡模式，代码归我负责。”
- “确认我真的看懂了这个 PR。练习模式。”

智能体会先确认意图、负责人和模式，生成题组，逐题提问，最后展示回执。

直接使用脚本：

```bash
git diff main...HEAD > change.diff
python3 scripts/diffviva.py deck change.diff --out viva.json \
  --intent "部分退款累计不超过订单总额；网关超时自动重试" --owner "@sam"
python3 scripts/diffviva.py ask viva.json
python3 scripts/diffviva.py mark viva.json A1 SOLID --quote "新金额加上已退金额超过总额时会抛 RefundTooLarge"
python3 scripts/diffviva.py receipt viva.json --diff change.diff --out viva-receipt.md
```

| 结论 | 退出码 |
|---|---|
| OWNED / OWNED_WITH_NOTES | 0 |
| NOT_YET | 2 |
| INTENT_MISMATCH | 3 |
| STALE | 4 |
| INCOMPLETE | 5 |

## 示例

`examples/sample.diff` 给退款加了上限，并在支付网关调用外包了一层重试循环。答辩中，负责人说三次超时后函数会抛异常。其实不会：循环直接走完，退款照样被保存，钱却没有退出去。`examples/receipt-example.md` 中的回执结论是 `INTENT_MISMATCH`，修复只需一行会抛异常的 `else:`，而不是再上一节课。`examples/viva-example.json` 记录了每个分数和引用。

## 文件结构

```
diff-viva/
├── SKILL.md                    # 技能说明（英文）
├── SKILL.zh-CN.md              # 技能说明（中文）
├── README.md                   # 英文 README
├── README.zh-CN.md             # 本文件
├── LICENSE                     # MIT
├── scripts/
│   └── diffviva.py             # deck / ask / mark / receipt
├── examples/
│   ├── sample.diff             # 示例中使用的退款改动
│   ├── viva-example.json       # 示例答辩记录的分数
│   └── receipt-example.md      # 得出的 INTENT_MISMATCH 回执
└── tests/
    └── test_diffviva.py        # python3 -m unittest discover -s tests
```

## 许可证

MIT © fangdididi
