---
name: diff-viva
description: Oral exam on a code change before you merge or adopt it. Use when someone is about to own code they did not fully write (agent output, a teammate's branch, a vendored patch) and says "quiz me on this diff", "make sure I understand this before I merge", "comprehension check", or "viva this PR". Picks risky anchors from the diff, asks one closed-book question at a time, marks answers strictly, and issues an OWNED / NOT_YET / INTENT_MISMATCH receipt. Not for finding bugs line by line, and not for learning a topic from scratch.
---

# Diff Viva

**Language:** English | [中文](SKILL.zh-CN.md)

## What this is

Agents now write code faster than people can absorb it. Tests go green, the
change merges, and two weeks later nobody can say why a retry loop sleeps for
`2 ** attempt` seconds or what happens when the gateway times out three times
in a row. The code is shipped but not *owned*.

A viva is an oral exam: the candidate defends their own work in front of an
examiner. Diff Viva turns you, the agent, into a fair but strict examiner for
one specific change. You read the diff, choose the few places where a
misunderstanding would hurt most, and ask the future owner questions only a
person who understands those places can answer. The result is a short receipt
that says whether the person now owns the change, which parts are still
borrowed, and, most valuably, whether their answers revealed that the code does
not do what they think it does.

That last case is the hidden payoff. When an owner confidently predicts
behaviour the code does not have, you have found a bug through a conversation,
before any reviewer or user did.

## When to use it

Use it when:

- a person is about to merge or adopt code an agent wrote for them;
- someone inherits a teammate's branch and must maintain it;
- a team wants a lightweight "explain it before you ship it" step for sensitive
  changes (auth, money, migrations, concurrency);
- the user asks to be quizzed on, examined on, or walked through a diff in a way
  that checks them rather than lectures them.

Do not use it when:

- the user wants a bug hunt or review comments (do a code review instead);
- the user wants to learn a whole technology from zero (run a tutoring session);
- the change is docs, formatting, or generated lockfiles only. Say so and stop.

## Ground rules for the examiner

1. **Ask about this diff, never about trivia.** Every question points at a file
   and line in the change. "What does `Decimal` do?" is trivia. "What does
   `refund_view` return for a non-staff user who posts a valid amount, and does
   `issue_refund` still run?" is a viva question.
2. **One question per message.** End the message at the question mark. No hint,
   no "for example", no encouraging preamble that leaks the answer.
3. **Closed chat, open code.** The candidate may read the code, run it, and use a
   debugger. They may not scroll up to an explanation you or another agent gave
   earlier. Real ownership is being able to work it out from the code.
4. **Write your own answer key first.** Before asking, read the surrounding code
   and write down, privately, what a correct answer must contain. If you cannot
   answer your own question from the code, it is a bad question; replace it.
5. **Mark strictly, quote always.** Every mark cites the candidate's own words.
   Never credit an insight they did not express.
6. **Wrong means narrower, not answered.** On a wrong or vague answer, ask a
   smaller question that exposes the gap. Only after two narrower tries do you
   explain, and then you must re-ask the same idea later from a different angle.
7. **No flattery, no shaming.** "Not yet. If the third retry also times out,
   which line runs next?" is the tone.

## Question families

Each anchor gets one family. Rotate them so the viva is not five versions of
"what does this line do".

| Family | Shape of the question | Good for |
|---|---|---|
| PREDICT | "Given input X, what happens / what is returned?" | branches, loops, guards |
| BREAK | "If this line were deleted, or this call failed, what goes wrong and who notices?" | error handling, deletions, concurrency |
| TRACE | "Where does this value come from, and where does it go after this call?" | I/O, state, external calls |
| WHY | "Why this choice over the obvious alternative (name it)?" | constants, timeouts, design decisions |
| EDGE | "What is the smallest input that takes the other path?" | boundaries, off-by-one, empty cases |

## Step by step

### 1. Agree the viva card

Ask, in one message, for three things and write them down:

- **Intent:** one sentence on what the change is supposed to do.
- **Owner:** who will be paged when this breaks.
- **Mode:** `practice` (marks are advice) or `gate` (the receipt blocks merge).

If the intent is missing or vague, stop and get it. Intent is what turns a
wrong answer into a possible bug.

### 2. Build the deck

Get the diff (`git diff main...HEAD`, the PR diff, or a pasted patch). If the
helper script is available:

```bash
python3 scripts/diffviva.py deck change.diff --out viva.json \
  --intent "Cap partial refunds at the order total; retry gateway timeouts" \
  --owner "@sam"
```

It parses the diff, finds anchors (new branches, error paths, I/O, concurrency,
boundaries, constants, deletions), weights them up on sensitive paths and lines
(auth, billing, migrations, tokens, amounts), spreads them across files, and
writes `viva.json`. The tier sets the number of anchors: routine 3, sensitive
5, critical 8. Override with `--tier` or `--count`.

Without the script, do the same by hand: list candidate lines, keep the
riskiest few, and spread them across files.

Then read the code around each anchor, not just the diff, and write the real
question plus your private answer key.

### 3. Run the viva

Loop until every anchor has a final mark:

1. `python3 scripts/diffviva.py ask viva.json` shows the next open anchor and the
   attempt number.
2. Ask the question for that anchor. Stop and wait.
3. Compare the answer with your key and record a mark:

```bash
python3 scripts/diffviva.py mark viva.json A3 PARTIAL \
  --quote "it retries a few times then gives up"
```

Marks:

- **SOLID**: correct and specific, in their own words.
- **PARTIAL**: on the right track but missing the part your key says matters.
- **WRONG**: incorrect, or a confident guess.
- **SKIP**: the candidate declined. Record it honestly.
- **MISMATCH**: the answer matches the stated *intent* but not the *code*. The
  person believes the code does something it does not. Pause the viva and show
  them the evidence (run it, or point at the lines).

If you explained the idea before a correct answer, add `--after-explain`. A
correct answer straight after an explanation is recall, not understanding, so
it does not clear a heavy anchor on its own; re-ask from another family later.

The script reopens PARTIAL and WRONG anchors up to three attempts in total.

### 4. Issue the receipt

```bash
python3 scripts/diffviva.py receipt viva.json --diff change.diff --out viva-receipt.md
```

Verdicts and exit codes:

| Verdict | Exit | Meaning |
|---|---|---|
| OWNED | 0 | Every anchor answered SOLID without prompting. |
| OWNED_WITH_NOTES | 0 | Only light anchors are shaky; list them for the reviewer. |
| NOT_YET | 2 | A heavy anchor (weight 4+) is not solid, or any anchor is WRONG. |
| INTENT_MISMATCH | 3 | The code does not do what the owner intends. Fix code or intent first. |
| STALE | 4 | The diff changed since the deck was built. Build a new deck. |
| INCOMPLETE | 5 | Some anchors were never asked. |

In `gate` mode, paste the receipt into the PR description or run the command in
a hook. In `practice` mode, just show it.

### 5. Close the loop

- **NOT_YET:** offer a short repair round on the listed anchors only, then a
  fresh question per anchor from a different family.
- **INTENT_MISMATCH:** treat it as a bug report. Write it up as "intended X,
  code does Y, evidence Z", fix or re-scope, then build a new deck.
- **OWNED_WITH_NOTES:** put the notes where the reviewer will see them.

## Worked example

The diff in `examples/sample.diff` changes a refund function and a refund view.
The intent is "cap partial refunds at the order total; retry gateway timeouts".

The deck picks five anchors, including `except GatewayTimeout:` in the retry
loop (BREAK) and `if not request.user.is_staff:` in the view (PREDICT).

> **Examiner:** The gateway times out on all three attempts. Which line runs
> next, and what does the customer's order look like afterwards?
>
> **Candidate:** The loop ends and it raises, so nothing is saved.
>
> **Examiner (thinking):** Key says: the loop ends without `break`, nothing
> raises, and the code falls through to `order.refunds.append(...)` and
> `order.save()`. The refund is recorded but the money never moved. The
> candidate's answer matches the intent, not the code.

Mark `A4 MISMATCH --quote "The loop ends and it raises"`. The receipt comes out
`INTENT_MISMATCH`, and the follow-up is a one-line fix (an `else:` on the loop
that raises) rather than another study session. See
`examples/receipt-example.md` for the full receipt.

## Tips

- Prefer questions whose answer is a concrete value, a line, or a yes/no plus a
  reason. They are easy to mark and hard to bluff.
- Ask one question that requires running the code if a shell is available:
  "Run the test with the gateway stubbed to always time out. What is in
  `order.refunds`?" Then check the actual output, not their summary of it.
- Keep a viva under fifteen minutes. More anchors is not more rigour; better
  anchors is.
- Never decide on authorship. Code a model wrote and the owner understands
  passes exactly like hand-written code.
- If the candidate is the person who prompted the agent, ask at least one WHY
  question about a choice the agent made that they did not ask for.
- Save `viva.json` next to the branch. A rerun with `--diff` tells you at once
  if the receipt still matches the code.
