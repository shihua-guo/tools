from __future__ import annotations

import ast
import inspect
import re
import textwrap
from types import ModuleType
from typing import Any


ALIGNER_TOKEN_LIMIT = 4096
_PATCHED_ATTR = "_mp4_asr_offline_aligner_patched"


class AlignerTokenLimitExceeded(RuntimeError):
    def __init__(self, actual: int, limit: int):
        super().__init__(f"aligner batch has {actual} tokens, limit is {limit}")
        self.actual = actual
        self.limit = limit


def correct_aligner_guard_source(source: str) -> tuple[str, int]:
    """Correct guards that confuse four MRoPE positions with four tokens.

    CapsWriter allocates ``LlamaBatch(n_total * 4)`` so its position buffer can
    hold four MRoPE coordinates per token. ``LlamaBatch.set_embd`` still sets
    ``batch.n_tokens`` to ``n_total``.  A locally added guard used the buffer
    size as the token count and consequently skipped valid alignments.
    """
    corrected, assignment_count = re.subn(
        r"(?m)^(\s*n_tokens\s*=\s*)n_total\s*\*\s*4(\s*(?:#.*)?)$",
        r"\1n_total\2",
        source,
    )
    corrected, condition_count = re.subn(
        r"(\bif\s+)\(?\s*n_total\s*\*\s*4\s*\)?(\s*>\s*[^:]+:)",
        r"\1n_total\2",
        corrected,
    )
    return corrected, assignment_count + condition_count


def _is_fourfold_n_total(node: ast.AST) -> bool:
    if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Mult):
        return False
    operands = (node.left, node.right)
    return any(isinstance(item, ast.Name) and item.id == "n_total" for item in operands) and any(
        isinstance(item, ast.Constant) and item.value == 4 for item in operands
    )


def has_bad_aligner_guard(source: str) -> bool:
    """Return whether an actual comparison still uses fourfold token count."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    fourfold_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and _is_fourfold_n_total(node.value):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            fourfold_names.update(target.id for target in targets if isinstance(target, ast.Name))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if _is_fourfold_n_total(node.left):
            return True
        if isinstance(node.left, ast.Name) and node.left.id in fourfold_names:
            return True
    return False


def _replace_bad_guard(aligner_module: ModuleType, aligner_class: type[Any]) -> bool:
    try:
        source = textwrap.dedent(inspect.getsource(aligner_class.align))
    except (OSError, TypeError):
        return False

    corrected, replacement_count = correct_aligner_guard_source(source)
    if replacement_count == 0:
        if has_bad_aligner_guard(source):
            raise RuntimeError("检测到无法自动修正的 CapsWriter Aligner 四倍 token guard")
        return False

    namespace: dict[str, Any] = {}
    exec(compile(corrected, str(getattr(aligner_module, "__file__", "<aligner>")), "exec"), aligner_module.__dict__, namespace)
    corrected_align = namespace["align"]
    corrected_align.__qualname__ = aligner_class.align.__qualname__
    aligner_class.align = corrected_align
    return True


def install_aligner_compatibility(aligner_module: ModuleType, token_limit: int = ALIGNER_TOKEN_LIMIT) -> bool:
    """Install the Qwen aligner fix in memory without editing CapsWriter files.

    Returns True when the known bad ``n_total * 4`` guard was found and
    corrected. The context-size and pre-decode protections are installed for
    both original and locally modified 2026-03-04 CapsWriter sources.
    """
    aligner_class = aligner_module.QwenForcedAligner
    if getattr(aligner_class, _PATCHED_ATTR, False):
        return False

    bad_guard_corrected = _replace_bad_guard(aligner_module, aligner_class)
    original_init = aligner_class.__init__
    original_align = aligner_class.align

    def patched_init(self: Any, config: Any) -> None:
        object.__setattr__(config, "n_ctx", token_limit)
        original_init(self, config)

        # CapsWriter 2026-03-04 hard-codes n_batch=2048 in the aligner even
        # when config.n_ctx is larger. Recreate only the llama context with a
        # matching logical batch limit; the already loaded model is reused.
        old_context = self.ctx
        self.ctx = aligner_module.llama.LlamaContext(
            self.model,
            n_ctx=token_limit,
            n_batch=token_limit,
            embeddings=False,
        )
        del old_context

        native_decode = self.ctx.decode

        def guarded_decode(batch: Any) -> Any:
            actual = int(batch.n_tokens)
            if actual > token_limit:
                raise AlignerTokenLimitExceeded(actual, token_limit)
            return native_decode(batch)

        self.ctx.decode = guarded_decode

    def safe_align(
        self: Any,
        audio: Any,
        text: str,
        language: str = "Chinese",
        offset_sec: float = 0.0,
    ) -> Any:
        try:
            return original_align(self, audio, text, language=language, offset_sec=offset_sec)
        except AlignerTokenLimitExceeded as exc:
            duration_sec = len(audio) / 16000.0
            print(
                f"[ALIGN SKIP] n_total={exc.actual} > {exc.limit}, skipping alignment",
                flush=True,
            )
            return aligner_module.ForcedAlignResult(
                items=[
                    aligner_module.ForcedAlignItem(
                        text=text,
                        start_time=offset_sec,
                        end_time=offset_sec + duration_sec,
                    )
                ],
                performance={"skipped": True, "n_total": exc.actual, "limit": exc.limit},
            )

    patched_init.__qualname__ = original_init.__qualname__
    safe_align.__qualname__ = original_align.__qualname__
    aligner_class.__init__ = patched_init
    aligner_class.align = safe_align
    setattr(aligner_class, _PATCHED_ATTR, True)
    return bad_guard_corrected
