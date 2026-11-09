import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import diffviva as dv  # noqa: E402

SAMPLE = os.path.join(HERE, "..", "examples", "sample.diff")

DOCS_ONLY = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,2 +1,2 @@
-Old words
+New words
"""

DELETE_ONLY = """diff --git a/lib/cache.py b/lib/cache.py
--- a/lib/cache.py
+++ b/lib/cache.py
@@ -5,3 +5,1 @@ def get(key):
-    lock.acquire()
-    value = store[key]
     return value
"""


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = dv.main(argv)
    return code, out.getvalue(), err.getvalue()


class ParseTests(unittest.TestCase):
    def test_parses_files_and_line_numbers(self):
        hunks = dv.parse_diff(open(SAMPLE).read())
        self.assertEqual([h["file"] for h in hunks], ["app/billing/refund.py", "app/web/views.py"])
        added = [l for l in hunks[1]["lines"] if l[0] == "+"]
        self.assertEqual(added[0][1], 41)

    def test_removed_lines_keep_old_numbers(self):
        hunks = dv.parse_diff(open(SAMPLE).read())
        removed = [l for l in hunks[0]["lines"] if l[0] == "-"]
        self.assertEqual(removed[0][1], 10)

    def test_hash_ignores_context_lines(self):
        a = "@@ -1 +1 @@\n x\n-a\n+b\n"
        b = "@@ -1 +1 @@\n y\n-a\n+b\n"
        self.assertEqual(dv.diff_hash(a), dv.diff_hash(b))
        self.assertNotEqual(dv.diff_hash(a), dv.diff_hash(a.replace("+b", "+c")))


class AnchorTests(unittest.TestCase):
    def setUp(self):
        self.anchors = dv.find_anchors(dv.parse_diff(open(SAMPLE).read()))

    def test_sensitive_path_and_line_raise_weight(self):
        billing = [a for a in self.anchors if a["file"].startswith("app/billing")]
        self.assertTrue(all(a["sensitive"] for a in billing))
        staff = [a for a in self.anchors if "is_staff" in a["code"]][0]
        self.assertTrue(staff["sensitive"])

    def test_added_lines_outrank_replaced_lines(self):
        old = [a for a in self.anchors if a["side"] == "old"]
        new_raise = [a for a in self.anchors if "RefundTooLarge" in a["code"]][0]
        self.assertTrue(all(o["weight"] < new_raise["weight"] for o in old))

    def test_pick_spreads_across_files(self):
        chosen = dv.pick(list(self.anchors), 2)
        self.assertEqual(len({a["file"] for a in chosen}), 2)

    def test_pick_ids_are_sequential(self):
        chosen = dv.pick(list(self.anchors), 4)
        self.assertEqual([a["id"] for a in chosen], ["A1", "A2", "A3", "A4"])

    def test_comments_are_ignored(self):
        hunks = dv.parse_diff("+++ b/x.py\n@@ -1 +1 @@\n+# if timeout > 30: retry\n")
        self.assertEqual(dv.find_anchors(hunks), [])

    def test_pure_deletion_gets_a_break_anchor(self):
        anchors = dv.find_anchors(dv.parse_diff(DELETE_ONLY))
        self.assertTrue(any(a["kind"] == "deletion" and a["family"] == "BREAK" for a in anchors))


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.viva = os.path.join(self.tmp, "viva.json")

    def deck(self, *extra):
        return run(["deck", SAMPLE, "--out", self.viva, *extra])

    def ids(self):
        return [a["id"] for a in json.load(open(self.viva))["anchors"]]

    def test_auto_tier_is_sensitive_for_billing(self):
        self.deck()
        v = json.load(open(self.viva))
        self.assertEqual(v["tier"], "sensitive")
        self.assertEqual(len(v["anchors"]), 5)

    def test_count_override(self):
        self.deck("--count", "2")
        self.assertEqual(len(self.ids()), 2)

    def test_docs_only_change_has_no_anchors(self):
        p = os.path.join(self.tmp, "d.diff")
        open(p, "w").write(DOCS_ONLY)
        code, out, _ = run(["deck", p, "--out", self.viva])
        self.assertEqual(code, 0)
        self.assertIn("no anchors", out)

    def test_mark_requires_quote(self):
        self.deck()
        code, _, err = run(["mark", self.viva, "A1", "SOLID"])
        self.assertEqual(code, 1)
        self.assertIn("--quote", err)

    def test_unknown_mark_rejected(self):
        self.deck()
        code, _, _ = run(["mark", self.viva, "A1", "GREAT", "--quote", "x"])
        self.assertEqual(code, 1)

    def test_unknown_anchor_rejected(self):
        self.deck()
        code, _, _ = run(["mark", self.viva, "A99", "SKIP"])
        self.assertEqual(code, 1)

    def test_incomplete_until_all_marked(self):
        self.deck()
        run(["mark", self.viva, "A1", "SOLID", "--quote", "it raises"])
        code, out, _ = run(["receipt", self.viva])
        self.assertEqual(code, dv.EXIT["INCOMPLETE"])
        self.assertIn("A2", out)

    def test_all_solid_is_owned(self):
        self.deck()
        for i in self.ids():
            run(["mark", self.viva, i, "SOLID", "--quote", "answer"])
        code, out, _ = run(["receipt", self.viva])
        self.assertEqual(code, 0)
        self.assertIn("Diff viva: OWNED", out)

    def test_wrong_on_heavy_anchor_blocks(self):
        self.deck()
        for i in self.ids():
            run(["mark", self.viva, i, "SOLID", "--quote", "answer"])
        run(["mark", self.viva, "A1", "WRONG", "--quote", "it just logs"])
        code, out, _ = run(["receipt", self.viva])
        self.assertEqual(code, dv.EXIT["NOT_YET"])
        self.assertIn("Still to own", out)

    def test_solid_after_explanation_on_heavy_anchor_blocks(self):
        self.deck()
        for i in self.ids():
            run(["mark", self.viva, i, "SOLID", "--quote", "answer"])
        run(["mark", self.viva, "A1", "SOLID", "--quote", "now I see", "--after-explain"])
        code, out, _ = run(["receipt", self.viva])
        self.assertEqual(code, dv.EXIT["NOT_YET"])
        self.assertIn("after explanation", out)

    def test_light_partial_gives_notes(self):
        p = os.path.join(self.tmp, "light.diff")
        open(p, "w").write("+++ b/src/list.py\n@@ -1 +1,2 @@\n+for x in items:\n+    total = total + 1\n")
        run(["deck", p, "--out", self.viva])
        v = json.load(open(self.viva))
        self.assertTrue(all(a["weight"] < 4 for a in v["anchors"]))
        for i in self.ids():
            run(["mark", self.viva, i, "PARTIAL", "--quote", "roughly"])
        code, out, _ = run(["receipt", self.viva])
        self.assertEqual(code, 0)
        self.assertIn("OWNED_WITH_NOTES", out)

    def test_mismatch_wins_over_everything(self):
        self.deck()
        for i in self.ids():
            run(["mark", self.viva, i, "SOLID", "--quote", "answer"])
        run(["mark", self.viva, "A4", "MISMATCH", "--quote", "I thought it stops after 3 timeouts"])
        code, out, _ = run(["receipt", self.viva])
        self.assertEqual(code, dv.EXIT["INTENT_MISMATCH"])
        self.assertIn("bug report", out)

    def test_stale_when_diff_changes(self):
        self.deck()
        for i in self.ids():
            run(["mark", self.viva, i, "SOLID", "--quote", "answer"])
        p = os.path.join(self.tmp, "new.diff")
        open(p, "w").write(open(SAMPLE).read().replace("range(3)", "range(5)"))
        code, out, _ = run(["receipt", self.viva, "--diff", p])
        self.assertEqual(code, dv.EXIT["STALE"])
        code, _, _ = run(["receipt", self.viva, "--diff", SAMPLE])
        self.assertEqual(code, 0)

    def test_ask_returns_open_then_done(self):
        self.deck("--count", "1")
        code, out, _ = run(["ask", self.viva])
        self.assertEqual(json.loads(out)["id"], "A1")
        run(["mark", self.viva, "A1", "WRONG", "--quote", "no idea"])
        _, out, _ = run(["ask", self.viva])
        self.assertEqual(json.loads(out)["attempt"], 2)
        run(["mark", self.viva, "A1", "SOLID", "--quote", "got it"])
        _, out, _ = run(["ask", self.viva])
        self.assertIn("no open anchors", out)

    def test_ask_gives_up_after_three_tries(self):
        self.deck("--count", "1")
        for _ in range(3):
            run(["mark", self.viva, "A1", "WRONG", "--quote", "no"])
        _, out, _ = run(["ask", self.viva])
        self.assertIn("no open anchors", out)

    def test_receipt_written_to_file(self):
        self.deck("--count", "1", "--intent", "cap refunds", "--owner", "@dev")
        run(["mark", self.viva, "A1", "SOLID", "--quote", "x"])
        out_md = os.path.join(self.tmp, "r.md")
        run(["receipt", self.viva, "--out", out_md])
        text = open(out_md).read()
        self.assertIn("cap refunds", text)
        self.assertIn("@dev", text)


if __name__ == "__main__":
    unittest.main()
