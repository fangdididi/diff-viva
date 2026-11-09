#!/usr/bin/env python3
"""diffviva - comprehension viva for a code change you are about to own.

Subcommands
  deck     read a unified diff, pick question anchors, write a viva file
  ask      print the next anchor that still needs a mark
  mark     record a mark for an anchor (SOLID / PARTIAL / WRONG / SKIP / MISMATCH)
  receipt  compute the verdict and print a Markdown receipt (exit code = verdict)

Only the Python standard library is used.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone

TIERS = {"routine": 3, "sensitive": 5, "critical": 8}
MARKS = ("SOLID", "PARTIAL", "WRONG", "SKIP", "MISMATCH")
EXIT = {"OWNED": 0, "OWNED_WITH_NOTES": 0, "NOT_YET": 2, "INTENT_MISMATCH": 3,
        "STALE": 4, "INCOMPLETE": 5}

SENSITIVE_PATH = re.compile(
    r"(auth|login|session|token|secret|crypt|password|perm|acl|billing|payment|"
    r"invoice|price|migrat|schema|\.sql$|security|oauth|jwt|webhook)", re.I)

SENSITIVE_LINE = re.compile(
    r"\b(is_staff|is_admin|admin|role|permission|authorize|authenticate|csrf|token|secret|"
    r"password|encrypt|decrypt|sign|verify|charge|refund|amount|balance)\b", re.I)

# (kind, weight, family, regex) -- checked against each added or removed line
SIGNALS = [
    ("error-path", 3, "BREAK", re.compile(
        r"\b(except|catch|raise|throw|rescue|panic|recover|finally|Err\(|errors?\.)", re.I)),
    ("branch", 2, "PREDICT", re.compile(
        r"^\s*(if|elif|else if|else|switch|case|match|when|unless)\b|\?\s*[^:]+:", re.I)),
    ("loop", 2, "PREDICT", re.compile(r"^\s*(for|while|do|loop)\b|\.(map|filter|reduce|forEach)\(", re.I)),
    ("boundary", 2, "EDGE", re.compile(r"(<=|>=|<|>|==|!=)\s*-?\d+|\b(len|length|size|count)\b", re.I)),
    ("constant", 1, "WHY", re.compile(r"\b\d{2,}\b|\b(timeout|retry|retries|limit|max|min|ttl)\b", re.I)),
    ("io", 3, "TRACE", re.compile(
        r"\b(fetch|request|http|query|execute|select|insert|update|delete|open\(|write|read|"
        r"cursor|commit|rollback|send|publish|subscribe|gateway|client|api)\b", re.I)),
    ("concurrency", 3, "BREAK", re.compile(
        r"\b(async|await|thread|lock|mutex|goroutine|go func|chan|atomic|semaphore|promise|"
        r"parallel|concurrent)\b", re.I)),
    ("state", 2, "TRACE", re.compile(r"\b(global|static|cache|singleton|self\.\w+\s*=|this\.\w+\s*=)", re.I)),
]

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def diff_hash(text):
    body = "\n".join(l for l in text.splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---")))
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def parse_diff(text):
    """Return a list of hunks: {file, new_start, header, lines:[(sign, lineno, text)]}."""
    hunks, cur, path = [], None, None
    new_no = old_no = 0
    for raw in text.splitlines():
        if raw.startswith("+++ "):
            p = raw[4:].strip()
            path = p[2:] if p.startswith("b/") else p
            continue
        if raw.startswith("--- ") or raw.startswith("diff --git") or raw.startswith("index "):
            continue
        m = HUNK.match(raw)
        if m:
            old_no, new_no = int(m.group(1)), int(m.group(3))
            cur = {"file": path, "new_start": new_no, "header": m.group(5).strip(), "lines": []}
            hunks.append(cur)
            continue
        if cur is None:
            continue
        if raw.startswith("+"):
            cur["lines"].append(("+", new_no, raw[1:]))
            new_no += 1
        elif raw.startswith("-"):
            cur["lines"].append(("-", old_no, raw[1:]))
            old_no += 1
        else:
            new_no += 1
            old_no += 1
    return [h for h in hunks if h["file"] and h["file"] != "/dev/null"]


def find_anchors(hunks):
    anchors = []
    for h in hunks:
        sens = bool(SENSITIVE_PATH.search(h["file"]))
        removed = [l for l in h["lines"] if l[0] == "-" and l[2].strip()]
        added = [l for l in h["lines"] if l[0] == "+" and l[2].strip()]
        for sign, no, text in h["lines"]:
            if not text.strip() or text.strip().startswith(("#", "//", "*", "/*")):
                continue
            for kind, weight, family, rx in SIGNALS:
                if rx.search(text):
                    hot = sens or bool(SENSITIVE_LINE.search(text))
                    w = weight + (2 if hot else 0) - (1 if sign == "-" and added else 0)
                    anchors.append({"file": h["file"], "line": no, "side": "new" if sign == "+" else "old",
                                    "kind": kind, "family": family, "weight": w, "sensitive": hot,
                                    "code": text.strip()[:160], "context": h["header"][:80]})
                    break
        if removed and not added:
            no = removed[0][1]
            anchors.append({"file": h["file"], "line": no, "side": "old", "kind": "deletion",
                            "family": "BREAK", "weight": 3 + (2 if sens else 0), "sensitive": sens,
                            "code": removed[0][2].strip()[:160], "context": h["header"][:80]})
    return anchors


def pick(anchors, n):
    """Highest weight first, but at most two anchors per file until every file had a turn,
    and never two anchors of the same kind on adjacent lines."""
    ranked = sorted(anchors, key=lambda a: (-a["weight"], a["file"], a["line"]))
    chosen, per_file = [], {}
    for limit in (1, 2, 99):
        for a in ranked:
            if len(chosen) >= n:
                break
            if a in chosen or per_file.get(a["file"], 0) >= limit:
                continue
            if any(c["file"] == a["file"] and c["kind"] == a["kind"] and abs(c["line"] - a["line"]) <= 2
                   for c in chosen):
                continue
            chosen.append(a)
            per_file[a["file"]] = per_file.get(a["file"], 0) + 1
    for i, a in enumerate(chosen, 1):
        a["id"] = f"A{i}"
        a["key_hint"] = None
        a["marks"] = []
    return chosen


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def cmd_deck(args):
    text = open(args.diff, encoding="utf-8").read()
    hunks = parse_diff(text)
    anchors = find_anchors(hunks)
    tier = args.tier
    if tier == "auto":
        tier = "sensitive" if any(a["sensitive"] for a in anchors) else "routine"
        if sum(len(h["lines"]) for h in hunks) > 400:
            tier = "critical" if tier == "sensitive" else "sensitive"
    n = args.count or TIERS[tier]
    chosen = pick(anchors, n)
    viva = {"created": now(), "diff_file": args.diff, "diff_hash": diff_hash(text),
            "intent": args.intent, "owner": args.owner, "tier": tier,
            "files": sorted({h["file"] for h in hunks}), "anchor_pool": len(anchors),
            "anchors": chosen}
    save(args.out, viva)
    print(f"viva written to {args.out}: tier={tier}, {len(chosen)} of {len(anchors)} anchors, "
          f"{len(viva['files'])} file(s)")
    for a in chosen:
        print(f"  {a['id']} [{a['family']}/{a['kind']} w{a['weight']}] {a['file']}:{a['line']} ({a['side']})  {a['code'][:70]}")
    if not chosen:
        print("  no anchors found: the change may be docs/config only; pick anchors by hand")
    return 0


def status_of(a):
    if not a["marks"]:
        return None
    return a["marks"][-1]["mark"]


def cmd_ask(args):
    viva = load(args.viva)
    for a in viva["anchors"]:
        st = status_of(a)
        tries = len(a["marks"])
        if st is None or (st in ("PARTIAL", "WRONG") and tries < 3):
            card = {k: a[k] for k in ("id", "family", "kind", "file", "line", "side", "code")}
            card["attempt"] = tries + 1
            print(json.dumps(card, ensure_ascii=False))
            return 0
    print("no open anchors; run receipt")
    return 0


def cmd_mark(args):
    viva = load(args.viva)
    mark = args.mark.upper()
    if mark not in MARKS:
        print(f"mark must be one of {', '.join(MARKS)}", file=sys.stderr)
        return 1
    for a in viva["anchors"]:
        if a["id"] == args.id:
            if mark in ("SOLID", "PARTIAL", "WRONG", "MISMATCH") and not args.quote:
                print("a mark needs --quote: the developer's own words that justify it", file=sys.stderr)
                return 1
            a["marks"].append({"mark": mark, "quote": args.quote, "note": args.note,
                               "after_explain": args.after_explain, "at": now()})
            save(args.viva, viva)
            print(f"{a['id']} -> {mark} (attempt {len(a['marks'])})")
            return 0
    print(f"no anchor {args.id}", file=sys.stderr)
    return 1


def verdict(viva, current_hash=None):
    if current_hash and current_hash != viva["diff_hash"]:
        return "STALE", []
    notes, blocking, open_ = [], [], []
    for a in viva["anchors"]:
        st = status_of(a)
        if st is None:
            open_.append(a["id"])
            continue
        if any(m["mark"] == "MISMATCH" for m in a["marks"]):
            return "INTENT_MISMATCH", [a["id"]]
        last = a["marks"][-1]
        solid_unprompted = st == "SOLID" and not last.get("after_explain")
        heavy = a["weight"] >= 4
        if solid_unprompted:
            continue
        if st == "SOLID" and last.get("after_explain"):
            (blocking if heavy else notes).append(a["id"])
        elif st == "PARTIAL":
            (blocking if heavy else notes).append(a["id"])
        elif st in ("WRONG", "SKIP"):
            (blocking if heavy or st == "WRONG" else notes).append(a["id"])
    if open_:
        return "INCOMPLETE", open_
    if blocking:
        return "NOT_YET", blocking
    if notes:
        return "OWNED_WITH_NOTES", notes
    return "OWNED", []


def cmd_receipt(args):
    viva = load(args.viva)
    cur = None
    if args.diff:
        cur = diff_hash(open(args.diff, encoding="utf-8").read())
    v, ids = verdict(viva, cur)
    out = [f"## Diff viva: {v}", "",
           f"- Intent: {viva.get('intent') or '(not stated)'}",
           f"- Owner: {viva.get('owner') or '(not stated)'}",
           f"- Tier: {viva['tier']}, {len(viva['anchors'])} anchors from a pool of {viva['anchor_pool']}",
           f"- Diff hash: `{viva['diff_hash']}`" + (" (changed since the viva)" if v == "STALE" else ""), "",
           "| Anchor | Where | Asks | Final mark | Tries |", "|---|---|---|---|---|"]
    for a in viva["anchors"]:
        st = status_of(a) or "open"
        if a["marks"] and a["marks"][-1].get("after_explain") and st == "SOLID":
            st = "SOLID (after explanation)"
        out.append(f"| {a['id']} | `{a['file']}:{a['line']}` | {a['family']} / {a['kind']} | {st} | {len(a['marks'])} |")
    if ids:
        label = {"NOT_YET": "Still to own", "OWNED_WITH_NOTES": "Notes for the reviewer",
                 "INTENT_MISMATCH": "Code does not do what the owner intended",
                 "INCOMPLETE": "Not asked yet", "STALE": ""}[v]
        if label:
            out += ["", f"**{label}:** " + ", ".join(ids)]
    if v == "INTENT_MISMATCH":
        out += ["", "Treat this as a bug report, not a study gap: fix the code or the intent, then run a new deck."]
    text = "\n".join(out) + "\n"
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text)
    print(text, end="")
    return EXIT[v]


def main(argv=None):
    p = argparse.ArgumentParser(prog="diffviva", description=__doc__.splitlines()[0])
    s = p.add_subparsers(dest="cmd", required=True)
    d = s.add_parser("deck", help="build a viva file from a unified diff")
    d.add_argument("diff")
    d.add_argument("--out", default="viva.json")
    d.add_argument("--tier", choices=["auto"] + list(TIERS), default="auto")
    d.add_argument("--count", type=int, default=0, help="override the number of anchors")
    d.add_argument("--intent", default="", help="one sentence: what the change is meant to do")
    d.add_argument("--owner", default="", help="who will maintain this code")
    a = s.add_parser("ask", help="show the next open anchor")
    a.add_argument("viva")
    m = s.add_parser("mark", help="record a mark")
    m.add_argument("viva")
    m.add_argument("id")
    m.add_argument("mark")
    m.add_argument("--quote", default="")
    m.add_argument("--note", default="")
    m.add_argument("--after-explain", action="store_true",
                   help="the answer came after you explained the idea")
    r = s.add_parser("receipt", help="print verdict and Markdown receipt")
    r.add_argument("viva")
    r.add_argument("--diff", help="current diff, to detect a stale viva")
    r.add_argument("--out")
    args = p.parse_args(argv)
    return {"deck": cmd_deck, "ask": cmd_ask, "mark": cmd_mark, "receipt": cmd_receipt}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
