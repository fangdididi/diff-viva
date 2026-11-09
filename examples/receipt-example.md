## Diff viva: INTENT_MISMATCH

- Intent: Cap partial refunds at the order total; retry gateway timeouts
- Owner: @sam
- Tier: sensitive, 5 anchors from a pool of 8
- Diff hash: `b91d5acf91b12724`

| Anchor | Where | Asks | Final mark | Tries |
|---|---|---|---|---|
| A1 | `app/billing/refund.py:12` | BREAK / error-path | SOLID | 1 |
| A2 | `app/web/views.py:41` | PREDICT / branch | SOLID | 1 |
| A3 | `app/billing/refund.py:15` | TRACE / io | SOLID | 2 |
| A4 | `app/billing/refund.py:17` | BREAK / error-path | MISMATCH | 1 |
| A5 | `app/billing/refund.py:11` | PREDICT / branch | SOLID | 1 |

**Code does not do what the owner intended:** A4

Treat this as a bug report, not a study gap: fix the code or the intent, then run a new deck.
