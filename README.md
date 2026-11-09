# diff-viva

**English** | [中文](README.zh-CN.md)

An agent skill that runs a short oral exam on a code change before someone merges or adopts it. It picks the riskiest places in the diff, asks the future owner one closed-book question at a time, marks the answers strictly with quotes, and issues a receipt: **OWNED**, **NOT_YET**, or **INTENT_MISMATCH** when the answers show the code does not do what its owner thinks.

## Why

Agent-written code arrives faster than people can absorb it. It compiles, the tests pass, and it merges, but nobody on the team can explain its failure paths. That gap between what the code does and what its owners understand keeps growing until the first incident.

Diff Viva closes the gap one change at a time, and catches bugs as a side effect: when the owner confidently describes behaviour that the code does not have, the conversation has found a defect before review or production did.

## Features

- **Anchors, not trivia.** Every question points to a file and line in this diff: new branches, error paths, I/O, concurrency, boundaries, magic constants, and deleted code.
- **Risk-aware.** Sensitive paths and lines (auth, billing, migrations, tokens, amounts) weigh more, and the tier sets how many anchors to ask: routine 3, sensitive 5, critical 8.
- **Five question families**, rotated across the viva: PREDICT, BREAK, TRACE, WHY, EDGE.
- **Examiner discipline.** One question per message, closed chat with open code, a private answer key written before asking, narrower follow-ups instead of giving the answer, and no flattery.
- **Strict marks with evidence.** SOLID, PARTIAL, WRONG, SKIP, or MISMATCH, each with the candidate's own words. A correct answer right after an explanation does not clear a heavy anchor.
- **Intent mismatch is a verdict.** It turns a misunderstanding into a bug report with evidence.
- **Stale guard.** The receipt hashes the changed lines, so a viva taken on an older diff shows up as STALE.
- **CI-friendly.** The receipt is Markdown for the PR description, and its exit code can gate a hook.
- **No dependencies.** One standard-library Python script, plus 25 tests.

## Installation

Requirements: Python 3.8+ for the helper script. The skill itself is plain Markdown and works without it.

**Claude Code**

```bash
git clone https://github.com/fangdididi/diff-viva ~/.claude/skills/diff-viva
```

**Codex / other agents that read a skills folder**

```bash
git clone https://github.com/fangdididi/diff-viva ~/.codex/skills/diff-viva
```

**Cursor**: clone into your project (for example `.cursor/skills/diff-viva`) and point a rule at `SKILL.md`, or ask the agent to read it before you merge.

**Chat assistants without a skills folder**: paste the body of `SKILL.md` into the chat or a custom instruction, then paste your diff.

## Usage

Ask your agent something like:

- "Viva this diff before I merge it."
- "Quiz me on what the agent just changed. Gate mode, I own it."
- "Make sure I understand this PR. Practice mode."

The agent agrees on the intent, owner, and mode, builds a deck, runs the questions, and shows the receipt.

Using the script directly:

```bash
git diff main...HEAD > change.diff
python3 scripts/diffviva.py deck change.diff --out viva.json \
  --intent "Cap partial refunds at the order total; retry gateway timeouts" --owner "@sam"
python3 scripts/diffviva.py ask viva.json
python3 scripts/diffviva.py mark viva.json A1 SOLID --quote "it raises RefundTooLarge when ..."
python3 scripts/diffviva.py receipt viva.json --diff change.diff --out viva-receipt.md
```

| Verdict | Exit code |
|---|---|
| OWNED / OWNED_WITH_NOTES | 0 |
| NOT_YET | 2 |
| INTENT_MISMATCH | 3 |
| STALE | 4 |
| INCOMPLETE | 5 |

## Example

`examples/sample.diff` caps refunds and adds a retry loop around a payment gateway. During the viva, the owner says that three timeouts make the function raise. They do not: the loop falls through, the refund is saved, and no money moves. The receipt in `examples/receipt-example.md` comes out `INTENT_MISMATCH`, and the fix is a one-line `else:` that raises, not another study session. `examples/viva-example.json` shows the recorded marks and quotes.

## File structure

```
diff-viva/
├── SKILL.md                    # skill instructions (English)
├── SKILL.zh-CN.md              # skill instructions (Chinese)
├── README.md                   # this file
├── README.zh-CN.md             # Chinese README
├── LICENSE                     # MIT
├── scripts/
│   └── diffviva.py             # deck / ask / mark / receipt
├── examples/
│   ├── sample.diff             # refund change used in the walkthrough
│   ├── viva-example.json       # marks recorded during the example viva
│   └── receipt-example.md      # the resulting INTENT_MISMATCH receipt
└── tests/
    └── test_diffviva.py        # python3 -m unittest discover -s tests
```

## License

MIT © fangdididi
