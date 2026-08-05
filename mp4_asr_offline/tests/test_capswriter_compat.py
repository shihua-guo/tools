from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from capswriter_compat import correct_aligner_guard_source, has_bad_aligner_guard, install_aligner_compatibility


class CorrectAlignerGuardSourceTests(unittest.TestCase):
    def test_corrects_intermediate_n_tokens_assignment(self) -> None:
        source = """
def align(self):
    n_tokens = n_total * 4
    if n_tokens > 4096:
        print(f"[ALIGN SKIP] n_total={n_total}, n_tokens={n_tokens} > 4096")
    batch = llama.LlamaBatch(n_total * 4, embd_dim=1024)
"""

        corrected, count = correct_aligner_guard_source(source)

        self.assertEqual(count, 1)
        self.assertIn("n_tokens = n_total", corrected)
        self.assertIn("if n_tokens > 4096:", corrected)
        self.assertIn("LlamaBatch(n_total * 4", corrected)

    def test_corrects_direct_condition_only(self) -> None:
        source = """
def align(self):
    if (n_total * 4) > self.max_batch_tokens:
        return None
"""

        corrected, count = correct_aligner_guard_source(source)

        self.assertEqual(count, 1)
        self.assertIn("if n_total > self.max_batch_tokens:", corrected)

    def test_leaves_correct_guard_and_mrope_allocation_unchanged(self) -> None:
        source = """
def align(self):
    if n_total > 4096:
        print("[ALIGN SKIP]")
    batch = llama.LlamaBatch(n_total * 4, embd_dim=1024)
"""

        corrected, count = correct_aligner_guard_source(source)

        self.assertEqual(count, 0)
        self.assertEqual(corrected, source)
        self.assertFalse(has_bad_aligner_guard(source))

    def test_detects_unhandled_fourfold_guard_but_not_batch_capacity(self) -> None:
        bad_source = """
def align(self):
    token_capacity: int = 4 * n_total
    if token_capacity > limit:
        return None
"""
        allocation_only = "batch = llama.LlamaBatch(n_total * 4, embd_dim=1024)\n"

        self.assertTrue(has_bad_aligner_guard(bad_source))
        self.assertFalse(has_bad_aligner_guard(allocation_only))


class InstallAlignerCompatibilityTests(unittest.TestCase):
    def test_uses_real_batch_tokens_and_returns_bounded_fallback(self) -> None:
        module = ModuleType("fake_aligner")
        module.__file__ = __file__

        class FakeContext:
            def __init__(self, model, n_ctx, n_batch, embeddings):
                self.n_ctx = n_ctx
                self.n_batch = n_batch

            def decode(self, batch):
                return batch.n_tokens

        class FakeAligner:
            def __init__(self, config):
                self.model = object()
                self.ctx = FakeContext(self.model, config.n_ctx, 2048, False)

            def align(self, audio, text, language="Chinese", offset_sec=0.0):
                self.ctx.decode(SimpleNamespace(n_tokens=self.requested_tokens))
                return module.ForcedAlignResult(items=[])

        @dataclass
        class FakeItem:
            text: str
            start_time: float
            end_time: float

        @dataclass
        class FakeResult:
            items: list[FakeItem]
            performance: dict | None = None

        module.QwenForcedAligner = FakeAligner
        module.llama = SimpleNamespace(LlamaContext=FakeContext)
        module.ForcedAlignItem = FakeItem
        module.ForcedAlignResult = FakeResult

        install_aligner_compatibility(module)
        aligner = FakeAligner(SimpleNamespace(n_ctx=2048))

        self.assertEqual(aligner.ctx.n_ctx, 4096)
        self.assertEqual(aligner.ctx.n_batch, 4096)

        aligner.requested_tokens = 2401
        normal = aligner.align([0] * 32000, "正常")
        self.assertEqual(normal.items, [])

        aligner.requested_tokens = 4097
        fallback = aligner.align([0] * 32000, "超限", offset_sec=10.0)
        self.assertEqual(len(fallback.items), 1)
        self.assertEqual(fallback.items[0].start_time, 10.0)
        self.assertEqual(fallback.items[0].end_time, 12.0)
        self.assertTrue(fallback.performance["skipped"])


if __name__ == "__main__":
    unittest.main()
