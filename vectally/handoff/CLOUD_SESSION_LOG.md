**Log sesi cloud — 10 November 2026**

Melanjutkan dari snapshot VECTALLY_CLOUD_INPUT_20261110.zip. Tidak ada aset yang dibangun ulang dari nol, tidak ada perubahan Canva.

| Langkah | Hasil terverifikasi |
|---|---|
| `python3 handoff/cloud_audit.py` | 84/84 sumber cocok SHA256; 1 paket diblokir: S06 `FONT_VARIANT_UNAVAILABLE Asap heavy/normal` (diharapkan). Guard tidak diubah. |
| Port path | 23 resep `work/*.py`: `D:/download/VECTALLY` → `VECTALLY_SOURCES`, `C:/Windows/Fonts/segoeuib.ttf` (label laporan saja) → `VECTALLY_REPORT_FONT`/DejaVu. Lewat `work/vpaths.py`. |
| Runner | `handoff/vectally.py` (Python, jobs.json yang sama). `Vectally.ps1` tetap; ditambah `-SourceRoot` dan fallback path sumber relatif repo. PS belum diuji ulang (pwsh tidak ada di cloud). |
| Reproduksi BuildGraphics | S01, S03, S04: paket IDENTIK byte. S02, S06: 1 path masing-masing beda urutan titik, render piksel identik (IoU 1.0, 0 px). Kemungkinan beda versi numpy (cloud 2.5.4 vs lokal 2.4.6). |
| Reproduksi Compose | S02, S04 identik. S06 Compose menghitung tinggi teks 73.8/69, paket kurasi memakai tinggi AKTUAL Canva 73.3/68.5 → paket kurasi dikembalikan dari backup; tetap diblokir font. |
| Canva (read-only) | Desain utama DAHaawX9Fm8: 11 halaman; salinan uji DAHabUK1x7c: 20 halaman — cocok dengan STATE.json. |
| Batas impor aktual | Konektor Canva di sesi cloud hanya bisa menambah teks dengan font bawaan (tidak bisa memilih Asap/League Gothic/Archivo Black atau fontRef). Mengimpor lewat konektor ini akan menjadi fallback font diam-diam → TIDAK dilakukan. Impor tetap lewat CUSBE Native Importer (app-source) di mesin pengguna. |

Status tidak berubah: 0 final, 17 draft, 67 belum siap. Tidak ada klaim 100%.
