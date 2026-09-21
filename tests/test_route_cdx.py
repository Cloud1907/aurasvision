#!/usr/bin/env python3
"""The hook router is silent unless the user explicitly invokes $cdx."""
import json
import os
import subprocess
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTER = os.path.join(ROOT, "bin", "route.py")


class ExplicitCdxRouteTest(unittest.TestCase):
    def run_router(self, prompt):
        result = subprocess.run(
            [sys.executable, ROUTER, "--explicit-cdx"],
            input=json.dumps({"prompt": prompt}), text=True,
            capture_output=True, cwd=ROOT, check=False)
        self.assertEqual(result.returncode, 0)
        return result.stdout

    def test_ordinary_prompt_is_silent(self):
        self.assertEqual(self.run_router("projeyi analiz et"), "")

    def test_explicit_cdx_runs_router(self):
        self.assertTrue(self.run_router("$cdx projeyi analiz et").strip())

    def test_plain_word_is_not_invocation(self):
        self.assertEqual(self.run_router("cdx hakkında bilgi ver"), "")


if __name__ == "__main__":
    unittest.main()
