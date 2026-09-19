# HANDOVER — Dich lai piaotia bang zhvi (MR merged vao data VI)

> Doc file nay de lam tiep. Moi so lieu da verify bang code, khong doan.
> Ngon ngu: tieng Viet. Quy tac repo: chi lam viec duoc giao, khong tu sua
> code/dict khi chua duyet, khong commit khi chua duoc yeu cau.

## 1. BOI CANH VA KET QUA

- Truyen: "Bat dau bang danh dau hoang co thanh the" (piaotia), 4752 chuong.
- Nguon Han: `crawler/data/piaotia/bat-dau-bang-danh-dau-hoang-co-thanh-the-(china)/`
- Ban Viet: `crawler/data/piaotia/bat-dau-bang-danh-dau-hoang-co-thanh-the/`
  (da ghi de bang zhvi sau khi va dict/code; 4 chuong thieu Han giu ban cu).
- Chua commit.
- Ban txt `piaotia-full/` + work dir ngoai repo **da xoa** (2026-09-19).
  Log duyet 100 chuong dau giu o `piaotia-100/`.

## 2. FOLDER / FILE LIEN QUAN

| Path | Noi dung |
|---|---|
| `crawler/data/piaotia/...-(china)/` | Nguon Han (97 vol .json.gz, 4748 chuong; thieu that 4 chuong: idx 1457/1516/1778/1812) |
| `crawler/data/piaotia/...-the/` | Ban VI **hien hanh** (4752 chuong; 4 chuong thieu Han giu nguyen) |
| `piaotia-100/` | Log duyet 100 chuong dau (khong con `merged/`): `review-246-cap.txt`, `bao-cao.txt`, `so-sanh.txt`, `rules-merge.tsv`, `keys-custom-de-xuat.tsv`, `phan-tich-update-code-vietphrase.txt` |
| `zhvi/` | Source engine. Diem nong: `src/zhvi/vietphrase/loader.py` (`_first_meaning` cat `/`\| theo vi tri som nhat), `lattice.py` (AD-9), `sense.py` (`_ASPECT` + `了` sau `在/于`), `qa.py` (strip `bqkan8` `/span`), `quality/export_qa.py` (stutter bo interior Latin), `pipeline.py` (`resolve_global_glossary`) |
| `crawler/vietphrase/dicts/` | Dict base (regenerable — TUYET DOI khong sua truc tiep): `VietPhrase_*.txt`, `Names.txt`, `LuatNhan.txt`, `Custom.txt` (highest-trust, sua o day), `QualityOverrides.txt` |
| `zhvi/glossary.manual.tsv` | 4 term chung (Tieu Ban: `小胖`…). Default `DEFAULT_GLOBAL_GLOSSARY` |
| `zhvi/glossary.d/hoang-co.tsv` | ~160 term series piaotia (`君逍遥=Quân Tiêu Dao`, `药离`, `就叫他逍遥`…) |
| `zhvi/workspace/zhvi.toml` | `global_glossary = "zhvi/glossary.manual.tsv"` |

Da xoa (khong dung lai): `piaotia-full/`, `/home/falcol/piaotia-full-work/`, `~/.config/zhvi/`, `/tmp/opencode/`. Glossary khong con o home — tap trung trong repo. Env `ZHVI_GLOBAL_GLOSSARY` van ghi de duoc.

## 3. HIEU BIET KY THUAT (da verify)

1. **AD-9 longest-match-first**: layer precedence chi xet trong cung do dai.
   Key fix phai DAI HON hoac BANG edge base sai (vd `会会吧`, `道道长虹`,
   `蒙上了` vs QO `蒙上`). Xac dinh edge thang bang `zhvi explain`.
2. **`_first_meaning`**: cat tai `/` hoac `|` **nao dung truoc**. Truoc day
   uu tien `/` nen `A|B/C` giu ca `|`. Da sua (`zhvi-loader-7`).
3. **SERIES/global glossary**: default trong repo (`zhvi/glossary.manual.tsv`
   + `glossary.d/*.tsv`). `resolve_global_glossary` van nap drop-in khi file
   chinh thieu. Lan full cu thieu SERIES vi `~/.config` chua co file chinh
   → 58.877 cho lowercase; da dich lai voi glossary trong repo.
4. **QA `repeated_artifact`**: bo lap nam trong 1 tu Latin (Yamamoto
   "amam"). Van chan stutter that (`ababab`).
5. **QA junk**: strip inline `bqkan8`, `/span`. `leftover_cjk` con chu thich
   `(火)` co chu y, ky tu loi nguon (谷伓/谷娋) — 3 chuong giu ban cu.
6. **`了` sau gioi tu noi cho** (`在/于`): khong chen "đã" (`áp chế ở đã`).
   `来了` van `đã`; cum dai `看了起来` giu span. `RENDERER` zhvi-renderer-9.
7. **逍遥**: TUYET DOI khong ep key mu (`tieu dao ca doi` la nghia thuong).
   Dat ten: khoa hep `就叫他逍遥=liền gọi hắn Tiêu Dao`.
8. **W6 giu `了`** tuong tac dirty VietPhrase_3 `X了` dai hon key dung —
   override Custom cung do dai/dai hon (khong sua `VietPhrase_*.txt`).

## 4. PHUONG AN DA DUNG

- Va Custom + sense/QA/loader + glossary trong repo → `vp_plan` +
  `sanitize_source` toan 4744 chuong co Han → ghi `vol-*.json.gz`
  (compact separators) + `chapters_index.json.gz`.
- 315 chuong lech dong: can theo Han (khong con giu cu vi lech dong).
- Pipe `|` trong output: ~752 → 6 doan le (khong vet).

## 5. TRANG THAI + VIEC CON LAI

- [x] Va dict/code (Custom, `了` locative, SERIES path, QA Yamamoto, junk, `|`).
- [x] Dich lai + ghi data VI (chua commit).
- [x] Glossary tap trung `zhvi/glossary.manual.tsv` + `zhvi/glossary.d/`.
- [x] Xoa `piaotia-full/`, work dir 80GB, `~/.config/zhvi`, `/tmp/opencode`.
- [ ] Commit khi user yeu cau (chi file da doi).
- Con lai nhe: `(火)` / ky tu loi nguon; 4 chuong thieu Han; 6 doan con `|`.
- Ghi nho: khong doc `.env*`; khong commit/push khi chua duoc yeu cau.
