# Headline TypeCraft S01-S04 — status 2026-11-11

Desain Canva: DAHalAB27TI. Halaman 2=S01, 3=S02, 4=S03, 5=S04. Status: TECHNICAL PASS (QA tepi), belum USER APPROVED.

Aturan: teks normal = native Canva (VECTALLY, label, body, S05 headline Asap). Headline bentuk tidak natural = TypeCraft
dengan instance statis keluarga font brand (League Gothic, Archivo; OFL tanpa Reserved Font Name). Font asli tidak ditimpa.

| Hal | Kata | Font TypeCraft | Jarak | Rotasi | IoU | Selisih tepi px |
|---|---|---|---|---|---|---|
| S01 | THE BOOKS | League Gothic W79 | -0.01 | 0 | 0.791 | ≤1 |
| S01 | STORY. | League Gothic W79 | -0.024 | 0 | 0.702 | 0 |
| S02 | WHAT’S | Archivo VX W66 800 | -0.005 | 0 | 0.783 | ≤1 |
| S02 | HARDER | Archivo VX W66 800 | -0.006 | 0 | 0.808 | 0 |
| S02 | TO | Archivo VX W66 800 | 0.025 | 0 | 0.735 | ≤1 |
| S02 | TRACK? | Archivo VX W66 800 | -0.010 | 0 | 0.753 | 0 |
| S03 | WHICH | Archivo VX Slant W84 800 | -0.009 | -4 | 0.805 | ≤1 |
| S03 | REPORT | Archivo VX Slant W84 800 | -0.0316 | -4 | 0.813 | ≤1 |
| S03 | SHOWS | Archivo VX Slant W64 900 | -0.019 | -10 | 0.632 | ≤5 |
| S03 | PROFIT? | Archivo VX Slant W64 800 | -0.029 | -4 | 0.670 | ≤2 |
| S04 | IT’S THE | Archivo VX W87 800 | -0.016 | 0 | 0.769 | 0 |
| S04 | PROFIT & | Archivo VX W62 800 | -0.018 | 0 | 0.850 | ≤1 |
| S04 | LOSS. | Archivo VX W66 900 | -0.004 | 0 | 0.864 | ≤2 |

Catatan:
- S04 IT’S THE native Asap lama dihapus (diganti TypeCraft, IoU 0.85 vs Asap 0.73, satu keluarga dengan PROFIT &).
- SHOWS/PROFIT? sumber punya distorsi perspektif; batas fit outline ~0.6. Stem THE BOOKS sumber sedikit lebih tebal (29 vs 26 px).
- Elemen TypeCraft nyasar di halaman 1 (pilot lama) sudah dihapus atas izin user (2026-11-11).
- Bukti: HEADLINE_QA.json, HEADLINE_QA_SHEET.png (sumber | Canva | overlay merah=sumber hijau=Canva), final_S01..S04.png.
- Font instance: outputs/VECTALLY-hybrid/headline-fonts/*.ttf, font-identification/LeagueGothic-W79.ttf (skrip: work/make_headline_fonts.py).

Teknis: Chrome khusus `D:\Codex\chrome-claude-profile` (CDP 127.0.0.1:9333, flag anti-throttle, login Canva).
Jembatan: `scripts/claude_gateway_bridge_v2.py 8765 config/upstreams.claude-cdp.json`.
Unit jarak TypeCraft ~2x model PIL dan ikut kerning: ukur rasio di Canva lalu koreksi 1x.
Halaman aktif harus di-set (gulir + klik area kosong di samping halaman) sebelum "Tambahkan ke desain".
