"""VietPhrase core — lattice top-K thay cho greedy longest-match."""
from .loader import Dictionary, dict_files_fingerprint, load_dictionary
from .trace import SourceSpan, VpDraft, VpSpan

__all__ = [
    "Dictionary",
    "SourceSpan",
    "VpDraft",
    "VpSpan",
    "dict_files_fingerprint",
    "load_dictionary",
]
