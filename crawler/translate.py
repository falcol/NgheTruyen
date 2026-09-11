"""Translate raw Chinese chapter text to Vietnamese.

Default: VietPhrase dictionary convert (longest-match Trie).
Optional: --edit qwen (post-edit VP). HachimiMT cannot edit VP (ZH→VI only).
Optional: --engine qwen|hachimi (hachimi: mask Names/Custom → HachimiMT-60-QT → unmask).
"""
import argparse
import json
import re
import sys
from pathlib import Path

import requests

from vietphrase.engine import CUSTOM_FILE
from vietphrase.engine import CUSTOM_PRI
from vietphrase.engine import DICT_DIR
from vietphrase.engine import _Node
from vietphrase.engine import _first_meaning
from vietphrase.engine import _match
from vietphrase.engine import _upsert
from vietphrase.engine import convert as vp_convert
from vietphrase.engine import ensure_dicts

try:
    import torch
    from transformers import AutoTokenizer, MarianMTModel
except ImportError:
    torch = None
    AutoTokenizer = None
    MarianMTModel = None

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:14b"
HACHIMI_REPO = "ngocdang83/HachimiMT-60-QT"
MAX_CHUNK_CHARS = 2200  # fits output + glossary in NUM_CTX 8192
NUM_CTX = 8192  # 16384 KV overflows RTX 3060 12GB with qwen3:14b
MAX_CJK_RETRIES = 1
HACHIMI_MAX_LENGTH = 256
HACHIMI_MAX_NEW_TOKENS = 300
HACHIMI_BATCH = 8
HACHIMI_MASK_RE = re.compile(r"#(\d+)#")
CUSTOM_SKIP_HEAD = ("đem ", "theo ", "cái ", "có ", "đang ", "muốn ")

SYSTEM_PROMPT = """Bạn dịch CONVERT kiểu VietPhrase / QuickTrans: phiên Hán Việt từng chữ, GIỮ TRẬT TỰ tiếng Trung.
Không viết lại thành tiếng Việt tự nhiên. Không thoát ý. Không đảo chủ-vị cho “mượt”.

1. CÚ PHÁP CONVERT:
- 着 / 著 → lấy (煮着灵茶 → nấu lấy linh trà; 坐落着 → tọa lạc lấy)
- 那个 → cái kia    你那个X → ngươi người X kia
- 的 → đích khi là định ngữ dài; còn lại lược nếu đã Hán Việt
- Thành ngữ dịch từng chữ: 恨铁不成钢 → chỉ tiếc rèn sắt không thành thép
- 得 → đến (得天地厚爱 → đến thiên địa hậu ái)
- Giữ nhịp lặp: 磨炼磨炼 → ma luyện ma luyện

2. HỢP THỂ — không tách dịch nghĩa:
  混沌道體 → hỗn độn đạo thể   SAI: thân thể Hỗn Độn
  承混沌道體 → nhận hỗn độn đạo thể
  先天道體 → tiên thiên đạo thể
  輪迴道 → Luân Hồi đạo        SAI: Đạo Vòng Quay
  逍遙宗 → Tiêu Diêu Tông      SAI: Tự Do Tông, Tiêu Dao Tông
  諸天萬界 → Chư Thiên Vạn Giới
  入贅 → ở rể                  SAI: nhập tế, làm rể
  神殺令 → thần sát lệnh
  轉世之門 → chuyển thế chi môn
  大乘境 → Đại Thừa cảnh
  神帝境 → thần Đế Cảnh
  低階 → đê giai

3. DANH XƯNG / TỪ VỰNG CONVERT (đúng thứ tự Trung):
  李老師 → Lý Lão sư     SAI: Lão sư Lý, cô giáo Lý
  師傅 → Sư phó          SAI: Sư phụ
  女教師 → nữ giáo sư    SAI: nữ lão sư, cô giáo
  小胖子 → Tiểu Bàn tử
  小屁孩 → tiểu thí hài
  奶聲奶氣 → nãi thanh nãi khí
  投胎 → đầu thai
  重生 / 轉世重生 → trọng sinh / chuyển thế trọng sinh
  坑了 → hố
  我靠 → Mịa nó          SAI: Tôi chửi thề, Khốn kiếp
  你個sb → Ngươi SB
  ta / ngươi / hắn / nàng / gã — không tôi / cô / anh / cậu

4. BẮT BUỘC:
- Không còn chữ Hán. Tên: 凌天 → Lăng Thiên (không Linh Thiên). 白髮 → tóc trắng.
- Giữ phân dòng. Đổi 「」 thành "".
- Chỉ in bản dịch."""

# Gold pairs from raw_china/expect.txt — few-shot beats more rules.
FEW_SHOT: list[tuple[str, str]] = [
    (
        "白髮老者大口緊閉，竟然是以神念發聲。",
        "Lão giả tóc trắng miệng lớn đóng chặt, lại là lấy thần niệm phát ra tiếng.",
    ),
    (
        "「小天得天地厚愛，承混沌道體，身上更有大氣運，大福緣，最多遇到一些小險境罷了，正好能磨鍊磨鍊他的心性。」白髮老者聞言，露出了一道慈祥的笑容，擺了擺手說道。",
        '"Tiểu Thiên đến thiên địa hậu ái, nhận hỗn độn đạo thể, trên thân càng có đại khí vận, lớn phúc duyên, nhiều nhất gặp phải một chút nhỏ hiểm cảnh mà thôi, vừa vặn có thể ma luyện ma luyện tâm tính của hắn." Lão giả tóc trắng nghe vậy, lộ ra một đạo nụ cười hiền lành, khoát tay áo nói rằng.',
    ),
    (
        "「喂，這裡是什麼地方？」凌天語氣不善的推了推身旁一個小胖子，話從口中說出，他發現自己的聲音怎麼變得有些奶聲奶氣了？",
        '"Uy, nơi này là địa phương nào?" Lăng Thiên ngữ khí bất thiện đẩy bên cạnh một cái Tiểu Bàn tử, lời nói từ trong miệng nói ra, hắn phát hiện âm thanh của chính mình thế nào biến có chút nãi thanh nãi khí?',
    ),
    (
        "「你那個小師弟，天賦異稟，但卻生性頑皮。」白髮老者聞言，輕嘆一聲，有些恨鐵不成鋼道：「把萬寶宗的仙庫里的諸多神兵利器洗劫一空就算了，最後居然還把劍宗葬劍閣里的所有頂尖劍訣燒掉。」",
        '"Ngươi người tiểu sư đệ kia, thiên phú dị bẩm, nhưng lại trời sinh tính tinh nghịch." Lão giả tóc trắng nghe vậy, than nhẹ một tiếng, có chút chỉ tiếc rèn sắt không thành thép nói: "Đem Vạn Bảo Tông tiên trong kho rất nhiều thần binh lợi khí cướp sạch không còn coi như xong, cuối cùng thế mà còn đem Kiếm Tông táng Kiếm các bên trong tất cả đỉnh tiêm kiếm quyết thiêu hủy."',
    ),
    (
        "「我靠，不是說是秘境傳送陣嗎，怎麼頭這麼痛！」凌天頭痛欲裂，好不容易睜開眼睛後，他發現自己坐在一張木桌前，周圍坐著一群小屁孩。",
        '"Mịa nó, không phải nói là bí cảnh truyền tống trận sao, thế nào đầu như thế đau nhức!" Lăng Thiên đầu đau muốn nứt, thật vất vả mở to mắt sau, hắn phát hiện mình ngồi ở trước một cái bàn gỗ, chung quanh ngồi một đám tiểu thí hài.',
    ),
]

EDIT_TAIL = """
Bạn là editor CONVERT, không phải dịch giả mới.
Nhận bản gốc Trung + bản VietPhrase. Sửa NHẸ bản VietPhrase, không dịch lại từ đầu.
- Giữ trật tự Trung, hợp thể Hán Việt, glossary.
- Cấm thuần Việt: thân thể Hỗn Độn, Tự Do Tông, cô giáo, tôi/cậu/bạn.
- Bỏ 'đích'/'liễu' trơ (của 的/了). Giữ 'lấy' (着).
- Còn chữ Hán → phiên Hán Việt.
- Giữ số đoạn. Chỉ in bản đã sửa."""

def _load_custom_glossary() -> dict[str, str]:
    path = Path(__file__).resolve().parent / "vietphrase" / "dicts" / "Custom.txt"
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line[0] in "#;" or line.startswith("//"):
            continue
        eq = line.find("=")
        if eq < 1:
            continue
        out[line[:eq].strip()] = line[eq + 1 :].strip()
    return out


GLOSSARY = _load_custom_glossary()

CJK_FALLBACK: dict[str, str] = {
    "好不容易": "thật vất vả",
    "霸道": "bá đạo",
}


def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def make_chunks(paragraphs: list[str], max_chars: int = MAX_CHUNK_CHARS) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for p in paragraphs:
        if current and current_len + len(p) > max_chars:
            chunks.append(current)
            current, current_len = [], 0
        current.append(p)
        current_len += len(p)
    if current:
        chunks.append(current)
    return chunks


def format_system_prompt(glossary: dict[str, str] | None = None) -> str:
    terms = glossary if glossary is not None else GLOSSARY
    if not terms:
        return SYSTEM_PROMPT
    lines = "\n".join(f"  {src} → {dst}" for src, dst in terms.items())
    return SYSTEM_PROMPT + "\n\n6. GLOSSARY (bắt buộc đúng từng mục, không dịch nghĩa, không tách hợp thể):\n" + lines


def convert_messages(source: str, extra_system: str = "") -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": format_system_prompt() + extra_system}]
    for zh, vi in FEW_SHOT:
        msgs.append({"role": "user", "content": zh})
        msgs.append({"role": "assistant", "content": vi})
    msgs.append({"role": "user", "content": source})
    return msgs


def ollama_chat(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.1,
    echo: bool = True,
    keep_alive: str | int | None = None,
    think: bool = False,
) -> str:
    payload = {
        "model": model or MODEL,
        "messages": messages,
        "stream": True,
        "think": think,
        "options": {"num_ctx": NUM_CTX, "temperature": temperature},
    }
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    resp = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=600)
    resp.raise_for_status()
    pieces: list[str] = []
    for line in resp.iter_lines():
        if not line:
            continue
        data = json.loads(line)
        piece = data.get("message", {}).get("content", "")
        if piece:
            pieces.append(piece)
            if echo:
                print(piece, end="", flush=True)
        if data.get("done"):
            break
    if echo:
        print()
    return "".join(pieces).strip()


def split_translated(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def qwen_edit(source: str, draft: str, keep_alive: str | int | None = "5m") -> str:
    return ollama_chat(
        convert_messages(f"[NGUỒN]\n{source}\n\n[VIETPHRASE]\n{draft}", extra_system=EDIT_TAIL),
        keep_alive=keep_alive,
    )


_TRAD_SIMP: dict[str, str] | None = None
_HACHIMI_TOK = None
_HACHIMI_MODEL = None
_HACHIMI_DEVICE: str | None = None
_MASK_ROOT: _Node | None = None


def to_simplified(text: str) -> str:
    global _TRAD_SIMP
    if _TRAD_SIMP is None:
        ensure_dicts()
        path = Path(__file__).resolve().parent / "vietphrase" / "dicts" / "trad-simp.txt"
        raw = "".join(path.read_text(encoding="utf-8-sig").split())
        chars = list(raw)
        if len(chars) % 2:
            chars = chars[:-1]
        _TRAD_SIMP = {chars[i]: chars[i + 1] for i in range(0, len(chars), 2)}
    mp = _TRAD_SIMP
    return "".join(ch if ch == "么" else mp.get(ch, ch) for ch in text)


def _load_mask_file(root: _Node, path: Path, pri: int) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line[0] in "#;" or line.startswith("//"):
            continue
        eq = line.find("=")
        if eq < 1:
            continue
        zh = line[:eq].strip()
        if "{0}" in zh or len(zh) == 1:
            continue
        vi = _first_meaning(line[eq + 1 :])
        if not zh or not vi:
            continue
        if pri == CUSTOM_PRI:
            named = any(ch.isupper() for ch in vi)
            if vi.lower().startswith(CUSTOM_SKIP_HEAD):
                continue
            if not named and (len(zh) < 3 or any(p in zh for p in "了着著的")):
                continue
        simp = to_simplified(zh)
        _upsert(root, simp, vi, pri)
        if simp != zh:
            _upsert(root, zh, vi, pri)


def _mask_root() -> _Node:
    global _MASK_ROOT
    if _MASK_ROOT is None:
        ensure_dicts()
        root = _Node()
        _load_mask_file(root, DICT_DIR / "Names.txt", 20)
        _load_mask_file(root, DICT_DIR / "Names_2.txt", 20)
        _load_mask_file(root, DICT_DIR / CUSTOM_FILE, CUSTOM_PRI)
        _MASK_ROOT = root
        print("[hachimi] mask dict Names+Custom", file=sys.stderr)
    return _MASK_ROOT


def mask_names(text: str) -> tuple[str, list[str]]:
    root = _mask_root()
    pieces: list[str] = []
    table: list[str] = []
    index_of: dict[str, int] = {}
    i = 0
    n = len(text)
    while i < n:
        hit = _match(root, text, i)
        if hit is None:
            pieces.append(text[i])
            i += 1
            continue
        end, vi = hit
        zh = text[i:end]
        idx = index_of.get(zh)
        if idx is None:
            idx = len(table)
            index_of[zh] = idx
            table.append(vi)
        pieces.append(f" #{idx}# ")
        i = end
    return "".join(pieces), table


def unmask_names(text: str, table: list[str]) -> str:
    def _repl(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        if not (0 <= idx < len(table)):
            return match.group(0)
        vi = table[idx]
        start, end = match.span()
        prev = text[start - 1] if start else ""
        nxt = text[end] if end < len(text) else ""
        if prev.isalnum() and vi[:1].isalnum():
            vi = " " + vi
        if nxt.isalnum() and vi[-1:].isalnum():
            vi = vi + " "
        return vi

    text = HACHIMI_MASK_RE.sub(_repl, text)
    leftover = HACHIMI_MASK_RE.findall(text)
    if leftover:
        print(f"[warn] leftover mask {leftover} -> {text}", file=sys.stderr)

    def _loose(match: re.Match[str]) -> str:
        raw = match.group(1) or match.group(2)
        idx = int(raw)
        if 0 <= idx < len(table):
            print(f"[warn] broken mask {match.group(0)} -> {table[idx]}", file=sys.stderr)
            return table[idx]
        return match.group(0)

    text = re.sub(r"#(\d+)|(\d+)#", _loose, text)
    return text


def _get_hachimi():
    global _HACHIMI_TOK, _HACHIMI_MODEL, _HACHIMI_DEVICE
    if torch is None or AutoTokenizer is None or MarianMTModel is None:
        raise RuntimeError(
            "HachimiMT needs torch + transformers + sentencepiece "
            "(pip install torch transformers sentencepiece)"
        )
    if _HACHIMI_MODEL is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[hachimi] load {HACHIMI_REPO} on {device}", file=sys.stderr)
        tok = AutoTokenizer.from_pretrained(HACHIMI_REPO)
        model = MarianMTModel.from_pretrained(HACHIMI_REPO).to(device).eval()
        _HACHIMI_TOK = tok
        _HACHIMI_MODEL = model
        _HACHIMI_DEVICE = device
    return _HACHIMI_TOK, _HACHIMI_MODEL, _HACHIMI_DEVICE


def hachimi_translate(paragraphs: list[str]) -> list[str]:
    tok, model, device = _get_hachimi()
    masked_all: list[str] = []
    tables: list[list[str]] = []
    span_n = 0
    for p in paragraphs:
        masked, table = mask_names(to_simplified(p))
        masked_all.append(masked)
        tables.append(table)
        span_n += len(table)
    print(f"[hachimi] {span_n} unique masks / {len(paragraphs)} paras", file=sys.stderr)
    out: list[str] = []
    n = len(masked_all)
    for start in range(0, n, HACHIMI_BATCH):
        chunk = masked_all[start : start + HACHIMI_BATCH]
        print(f"[hachimi {start + 1}-{start + len(chunk)}/{n}]", file=sys.stderr)
        inp = tok(
            chunk,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=HACHIMI_MAX_LENGTH,
        ).to(device)
        with torch.inference_mode():
            gen = model.generate(
                **inp,
                max_new_tokens=HACHIMI_MAX_NEW_TOKENS,
                num_beams=4,
                early_stopping=True,
            )
        decoded = [tok.decode(row, skip_special_tokens=True).strip() for row in gen]
        for i, raw in enumerate(decoded):
            out.append(unmask_names(raw, tables[start + i]))
    return out


def aligned_chunks(src: list[str], vi: list[str], max_chars: int = MAX_CHUNK_CHARS) -> list[tuple[list[str], list[str]]]:
    out: list[tuple[list[str], list[str]]] = []
    cs: list[str] = []
    cv: list[str] = []
    n = 0
    for s, v in zip(src, vi):
        if cs and n + len(s) > max_chars:
            out.append((cs, cv))
            cs, cv, n = [], [], 0
        cs.append(s)
        cv.append(v)
        n += len(s)
    if cs:
        out.append((cs, cv))
    return out


def translate_chunk(paragraphs: list[str]) -> list[str]:
    source = "\n\n".join(paragraphs)
    return split_translated(ollama_chat(convert_messages(source)))


CJK_RE = re.compile(r"[一-鿿]")
CJK_SEQ_RE = re.compile(r"[一-鿿]+")


def apply_cjk_glossary(text: str) -> str:
    mapping = {**GLOSSARY, **CJK_FALLBACK}
    for src in sorted(mapping, key=len, reverse=True):
        start = 0
        dst = mapping[src]
        while True:
            i = text.find(src, start)
            if i < 0:
                break
            j = i + len(src)
            piece = dst
            if i > 0 and not text[i - 1].isspace() and text[i - 1] not in "「『\"'(" and piece[:1].isalnum():
                piece = " " + piece
            if j < len(text) and not text[j].isspace() and text[j] not in "」』\"')" and piece[-1:].isalnum():
                piece = piece + " "
            text = text[:i] + piece + text[j:]
            start = i + len(piece)
    return text


def retry_cjk_paragraph(paragraph: str) -> str:
    leftover = ", ".join(CJK_SEQ_RE.findall(paragraph))
    return ollama_chat(
        convert_messages(
            "Đoạn Convert sau còn sót chữ Hán. Thay MỌI chữ Hán bằng phiên âm Hán Việt. "
            "Không thêm/bớt câu. Chỉ in đoạn đã sửa.\n\n"
            f"Chữ Hán còn sót: {leftover}\n\n{paragraph}"
        ),
        temperature=0.1,
    )


def strip_leftover_cjk(paragraphs: list[str]) -> list[str]:
    out: list[str] = []
    for i, p in enumerate(paragraphs):
        current = apply_cjk_glossary(p)
        for attempt in range(MAX_CJK_RETRIES):
            if not CJK_RE.search(current):
                break
            print(f"[retry-cjk] paragraph {i}", file=sys.stderr)
            current = apply_cjk_glossary(retry_cjk_paragraph(current))
        if CJK_RE.search(current):
            print(f"[warn] paragraph {i}: còn sót chữ Hán -> {current}", file=sys.stderr)
        out.append(current)
    return out


def _warn_leftover_cjk(paragraphs: list[str]) -> list[str]:
    out: list[str] = []
    for i, p in enumerate(paragraphs):
        current = apply_cjk_glossary(p)
        if CJK_RE.search(current):
            print(f"[warn] paragraph {i}: còn chữ Hán -> {current}", file=sys.stderr)
        out.append(current)
    return out


def translate_chapter(
    text: str,
    index: int,
    title: str,
    engine: str = "vietphrase",
    edit: str = "none",
) -> dict:
    paragraphs = split_paragraphs(text)
    if engine == "hachimi":
        print(f"[hachimi] {len(paragraphs)} paragraphs", file=sys.stderr)
        translated_paragraphs = _warn_leftover_cjk(hachimi_translate(paragraphs))
        return {"index": index, "title": title, "paragraphs": translated_paragraphs}
    if engine == "vietphrase":
        ensure_dicts()
        print(f"[vietphrase] {len(paragraphs)} paragraphs", file=sys.stderr)
        translated_paragraphs = [vp_convert(p, overlay=GLOSSARY) for p in paragraphs]
        if edit == "qwen":
            pairs = aligned_chunks(paragraphs, translated_paragraphs)
            edited: list[str] = []
            n = len(pairs)
            for i, (src, draft) in enumerate(pairs, 1):
                print(f"[qwen-edit {i}/{n}]", file=sys.stderr)
                got = split_translated(qwen_edit("\n\n".join(src), "\n\n".join(draft)))
                if len(got) != len(draft):
                    print(f"[warn] qwen-edit chunk {i}: {len(got)} paras vs {len(draft)}, giữ VietPhrase", file=sys.stderr)
                    edited.extend(draft)
                else:
                    edited.extend(got)
            translated_paragraphs = strip_leftover_cjk(edited)
        else:
            for i, p in enumerate(translated_paragraphs):
                if CJK_RE.search(p):
                    print(f"[warn] paragraph {i}: còn chữ Hán -> {p}", file=sys.stderr)
        return {"index": index, "title": title, "paragraphs": translated_paragraphs}
    chunks = make_chunks(paragraphs)
    translated_paragraphs: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        print(f"[chunk {i}/{len(chunks)}]", file=sys.stderr)
        translated_paragraphs.extend(translate_chunk(chunk))
    translated_paragraphs = strip_leftover_cjk(translated_paragraphs)
    return {"index": index, "title": title, "paragraphs": translated_paragraphs}


def main():
    ap = argparse.ArgumentParser(description="Translate raw zh chapter txt to vi JSON")
    ap.add_argument("input", type=Path, help="Raw .txt chapter file (zh)")
    ap.add_argument("-o", "--output", type=Path, help="Output .json path (default: <input>.vi.json)")
    ap.add_argument("--index", type=int, default=0, help="Chapter index (0-based)")
    ap.add_argument("--title", default="", help="Chapter title (vi); left blank if not given")
    ap.add_argument(
        "--engine",
        choices=("vietphrase", "qwen", "hachimi"),
        default="vietphrase",
        help="vietphrase = dictionary convert (default). qwen = local LLM. hachimi = HachimiMT-60-QT.",
    )
    ap.add_argument("--qwen-only", action="store_true", help="Alias for --engine qwen")
    ap.add_argument(
        "--edit",
        choices=("none", "qwen"),
        default="none",
        help="After VietPhrase: qwen light convert edit.",
    )
    args = ap.parse_args()

    text = args.input.read_text(encoding="utf-8")
    engine = "qwen" if args.qwen_only else args.engine
    chapter = translate_chapter(text, args.index, args.title, engine=engine, edit=args.edit)

    out_path = args.output or args.input.with_suffix(".vi.json")
    out_path.write_text(json.dumps(chapter, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
