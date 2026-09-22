"""Run the vietphrase.app NER-B int8 ONNX model and keep approved character names."""

from __future__ import annotations

import ctypes
import hashlib
import importlib
import sys
import urllib.request
from pathlib import Path

import numpy as np
import onnxruntime as ort

from vp.engine import Engine
from vp.ner_decide import FoundName, ScanStats, chunk_text, select_names
from vp.ner_text import Entity, Tokenizer, decode_bio, dedupe_entities, keep_entity, segment_text
from vp.textutil import has_cjk

MODEL_PAGE = "https://vietphrase.app/model/ner-b"
VOCAB_SHA256 = "45bbac6b341c319adc98a532532882e91a9cefc0329aa57bac9ae761c27b291c"
VOCAB_BYTES = 109540
ONNX_SHA256 = "221a54e8e38c09f10552cf15e3db9a5cf7e31f2e959678b40627ae0b93d0fe2c"
ONNX_BYTES = 1894085
BATCH = 16
_CUDA_SONAMES = (
    "libnvJitLink.so.12",
    "libcudart.so.12",
    "libnvrtc.so.12",
    "libcufft.so.11",
    "libcurand.so.10",
    "libcublas.so.12",
    "libcublasLt.so.12",
    "libcudnn.so.9",
)
_cuda_preloaded = False


def _preload_cuda_libs() -> None:
    """Make pip's CUDA 12 libraries visible before ONNX Runtime opens its GPU provider."""
    global _cuda_preloaded
    if _cuda_preloaded:
        return
    _cuda_preloaded = True
    by_name: dict[str, Path] = {}
    for module_name in (
        "nvidia.nvjitlink",
        "nvidia.cuda_runtime",
        "nvidia.cuda_nvrtc",
        "nvidia.cublas",
        "nvidia.cudnn",
        "nvidia.cufft",
        "nvidia.curand",
    ):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        for entry in getattr(module, "__path__", []):
            for path in Path(entry).rglob("*.so*"):
                if path.is_file():
                    by_name.setdefault(path.name, path)
    for soname in _CUDA_SONAMES:
        path = by_name.get(soname)
        if path is None:
            continue
        ctypes.CDLL(str(path), mode=ctypes.RTLD_GLOBAL)


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "vp-cli"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def _cached(cache_dir: Path, name: str, url: str, size: int, sha256: str, refresh: bool) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / name
    if dest.is_file() and not refresh:
        data = dest.read_bytes()
        if len(data) == size and hashlib.sha256(data).hexdigest() == sha256:
            return dest
        dest.unlink()
    data = _download(url)
    if len(data) != size or hashlib.sha256(data).hexdigest() != sha256:
        raise RuntimeError(f"{name}: sai kích thước hoặc SHA-256")
    dest.write_bytes(data)
    return dest


def ensure_model(cache_dir: Path, *, refresh: bool = False) -> tuple[Path, Path]:
    root = cache_dir / "ner-b"
    vocab = _cached(
        root,
        "vocab.txt",
        MODEL_PAGE + "/webgpu/vocab.txt",
        VOCAB_BYTES,
        VOCAB_SHA256,
        refresh,
    )
    model = _cached(
        root,
        "model_int8_dyn.onnx",
        MODEL_PAGE + "/wasm/model_int8_dyn.onnx",
        ONNX_BYTES,
        ONNX_SHA256,
        refresh,
    )
    return vocab, model


class NerEngine:
    def __init__(self, vocab_path: Path, model_path: Path, *, require_gpu: bool = False) -> None:
        self.tokenizer = Tokenizer(vocab_path.read_text(encoding="utf-8"))
        if len(self.tokenizer.vocab) != 21128:
            raise RuntimeError(f"Vocab NER có {len(self.tokenizer.vocab)} mục, cần 21128")
        available = ort.get_available_providers()
        if require_gpu and "CUDAExecutionProvider" not in available:
            raise RuntimeError(
                "Không thấy CUDA. Cần onnxruntime-gpu và driver NVIDIA để quét sâu trên GPU."
            )
        if require_gpu:
            chosen = ["CUDAExecutionProvider"]
        else:
            chosen = [name for name in ("CUDAExecutionProvider", "CPUExecutionProvider") if name in available]
        if "CUDAExecutionProvider" in chosen:
            _preload_cuda_libs()
        self.session = ort.InferenceSession(str(model_path), providers=chosen or None)
        active = self.session.get_providers()
        self.provider = active[0] if active else "default"
        if require_gpu and self.provider != "CUDAExecutionProvider":
            raise RuntimeError(f"NER không chạy trên GPU, phiên đang dùng {self.provider}.")
        self.output_name = self.session.get_outputs()[0].name

    def analyze(self, text: str) -> list[Entity]:
        if len(text) < 4:
            return []
        segments = segment_text(self.tokenizer, text)
        found: list[Entity] = []
        for start in range(0, len(segments), BATCH):
            batch = segments[start : start + BATCH]
            width = max(len(row.input_ids) for row in batch)
            ids = np.zeros((len(batch), width), dtype=np.int64)
            mask = np.zeros((len(batch), width), dtype=np.int64)
            types = np.zeros((len(batch), width), dtype=np.int64)
            for row_index, row in enumerate(batch):
                n = len(row.input_ids)
                ids[row_index, :n] = row.input_ids
                mask[row_index, :n] = 1
            logits = self.session.run(
                [self.output_name],
                {"input_ids": ids, "attention_mask": mask, "token_type_ids": types},
            )[0]
            for row_index, row in enumerate(batch):
                n = len(row.input_ids)
                labels: list[int] = []
                probs: list[float] = []
                for token in range(n):
                    label, prob = _argmax_prob(logits[row_index, token])
                    labels.append(label)
                    probs.append(prob)
                for entity in decode_bio(labels, probs, row.offsets, row.text):
                    if not keep_entity(entity, row):
                        continue
                    found.append(
                        Entity(
                            entity.text,
                            entity.tag,
                            row.start + entity.start,
                            row.start + entity.end,
                            entity.confidence,
                        )
                    )
        return dedupe_entities(found)


def _argmax_prob(row: np.ndarray) -> tuple[int, float]:
    label = int(np.argmax(row))
    peak = float(row[label])
    total = float(np.exp(row - peak).sum())
    return label, 1.0 / total


def suggest_name(engine: Engine, zh: str) -> str:
    parts: list[str] = []
    for ch in engine.convert(zh):
        reading = engine.phienam.get(ch, ch)
        if has_cjk(reading):
            return ""
        parts.append(reading[:1].upper() + reading[1:] if reading else reading)
    return " ".join(parts)


def scan_file(
    text: str,
    engine: Engine,
    cache_dir: Path,
    *,
    refresh: bool = False,
    require_gpu: bool = False,
    on_progress=None,
) -> tuple[list[FoundName], ScanStats]:
    vocab, model = ensure_model(cache_dir, refresh=refresh)
    ner = NerEngine(vocab, model, require_gpu=require_gpu)
    print(f"Quét sâu NER · {_device_label(ner.provider)}", file=sys.stderr, flush=True)
    scan_text = engine.convert(text or "").replace("\r\n", "\n").replace("\r", "\n")
    chunks = chunk_text(scan_text)
    spans: list[tuple[str, str]] = []
    known: set[str] = set()
    for index, chunk in enumerate(chunks):
        if on_progress:
            on_progress(index + 1, len(chunks))
        if len(chunk) < 4:
            continue
        for entity in ner.analyze(chunk):
            spans.append((entity.text, entity.tag))
            pri = engine.exact_priority(engine.convert(entity.text))
            if pri is not None and pri >= 10:
                known.add(entity.text)
    found, stats = select_names(spans, lambda zh: suggest_name(engine, zh), known=known)
    stats.chunks = len(chunks)
    stats.entities = len(spans)
    stats.provider = ner.provider
    return found, stats


def _device_label(provider: str) -> str:
    if provider == "CUDAExecutionProvider":
        return "GPU CUDA"
    if provider == "TensorrtExecutionProvider":
        return "GPU TensorRT"
    return "CPU"
