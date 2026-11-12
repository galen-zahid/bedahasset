# Prompt lanjutan VECTALLY — sesi baru (dibuat 2026-11-12)

Salin semua teks di bawah garis ini ke sesi Claude Code baru (working dir boleh `D:\Codex\kinrava-editable`).

---

Lanjutkan proyek VECTALLY (Canva editable kit CUSBE). Bahasa Indonesia santai, ringkas, kritis. Ikuti `C:\Users\HP\.claude\CLAUDE.md`. Jangan menimpa file, status jujur (SOURCE WRITTEN / RENDERED / TECHNICAL PASS / VISUAL PASS / USER APPROVED), minta izin sebelum hapus/publish/kirim. Commit tiap bagian jelas ke branch `ccr-6e448746-jedgxp` di repo `D:\bedahasset` dengan trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Jangan commit ZIP besar.

## Tujuan user saat ini
1. User mau **render semua VECTALLY sendiri di PowerShell** (satu perintah), BUKAN Claude yang memproses. Tugas Claude: memastikan program render benar, lalu impor hasilnya ke Canva.
2. Hasil akhir: **3 link Canva** — Feed (48), Story (30), Highlight (6).

## Font lock VECTALLY (WAJIB, jangan diganti diam-diam)
- League Gothic — primary display (headline condensed)
- Archivo Black — secondary impact
- Asap — body, CTA, label, metadata
- Asap Condensed DILARANG. Font instance buatan sendiri (Archivo VX …, League Gothic W79) = melanggar lock; user sudah menegur.

## Status program render (BELUM FINAL — inilah pekerjaan pertama)
Perintah untuk user (setelah program dinyatakan siap):
`cd D:\bedahasset\vectally; .\Render-Vectally.ps1 -Stamp <baru>`  (stamp baru, karena folder `-20261112` berisi hasil lama yang tidak layak)

Alur program:
1. `D:\bedahasset\split.py --mode rebuild --config vectally\config_vectally.yaml` (OCR + pisah bidang → `CANVA_PACKAGE.json` per desain)
2. `vectally\work\batch_finalize.py` → geometri ulang pakai mesin Codex+Claude `smooth_native_paths.py`, font brand (Asap / Archivo Black), headline besar ditandai `HEADLINE_TYPECRAFT`, Story S01–S05 pakai paket kurasi, warnai ulang sisa huruf headline ke warna latar, QA (`QA_SHEET.png`, `QA_RINGKASAN.csv`). Output `outputs\VECTALLY-final-<stamp>\<Family>\NN_<kode>.json`.

Perubahan sesi ini (BELUM di-commit, cek `git status` di `D:\bedahasset`):
- `pipeline/rebuild/canva_package.py`: mode `canva_never_image` (tanpa fallback PNG; gradien → warna solid rata-rata; tiap path jadi 1 shape dalam 1 grup per objek; bidang terlalu rumit dicoba tanpa lubang lalu disederhanakan). Backup asli: `D:\bedahasset\backups\20261112-never-image\canva_package.py`.
- `vectally/config_vectally.yaml` (BARU): salinan config.yaml + `canva_never_image: true`, `canva_max_split: 999`, `effects: false`.
- `vectally/work/batch_finalize.py`: `drop_text_ghosts` (recolor ke warna cincin latar), `text_boxes` gabung baris headline, `ring_color`.
- `vectally/work/smooth_native_paths.py`: guard indeks di cek ujung batang (sudah di-commit 7e4fab3).
- `vectally/Render-Vectally.ps1`: sudah pakai `--config $Config`; parameter `-SourceRoot`/`-OutRoot` kemungkinan sudah tertulis (edit Python berjalan sebelum interupsi) — VERIFIKASI isi file.

Hasil uji: A04 (Feed terburuk sebelumnya) → 0 PNG, ~238 shape dalam grup, ~110 dirapikan mesin Codex, match 0.80, area headline bersih. Render pertama user (stamp 20261112) TIDAK LAYAK: banyak bagian jadi PNG + layer efek PNG; jangan diimpor.

## Pekerjaan berikutnya (urut)
1. Verifikasi `Render-Vectally.ps1` (parse OK, param SourceRoot/OutRoot) lalu uji end-to-end di scratch untuk 5 sampel terburuk: A04, A09, A12 (Feed), S23 (Story), H03 (Highlight). Sumber uji sudah disiapkan di scratchpad sesi lama `...\scratchpad\nv5\src` (boleh buat ulang). Perintah uji:
   `powershell -File D:\bedahasset\vectally\Render-Vectally.ps1 -Stamp test -SourceRoot <src> -OutRoot <out>`
   (Uji terakhir diinterupsi user saat berjalan; cek apakah ada proses python split.py yang masih jalan sebelum mulai.)
2. Cek QA_SHEET visual: tidak ada PNG, tidak ada gumpalan sisa huruf, latar utuh. Perbaiki bila perlu.
3. Commit + push, lalu beri user satu perintah final dengan stamp baru.
4. Setelah user render: impor JSON per keluarga ke 3 desain Canva baru via app CUSBE importer (`D:\cusbe-importer`, `canva apps start` di localhost:8080; app AAHOGHKNaHM tetap DRAFT, jangan publish). Importer menerima banyak JSON sekaligus (1 file = 1 halaman).
5. Headline: keputusan user belum final. Opsi yang disarankan: mayoritas headline = teks native Canva League Gothic/Archivo Black (buyer bisa edit tanpa app); TypeCraft hanya untuk yang wajib miring/terdistorsi (mis. S03). Fakta: TypeCraft TIDAK punya League Gothic/Archivo Black/Asap bawaan (harus upload font; buyer juga harus upload) — editor "Distorsi" TypeCraft punya mesh 10 titik untuk memadatkan/memiringkan. Tanyakan user sebelum memakai TypeCraft.
6. Story S01–S05 sudah dikerjakan manual di desain `DAHalAB27TI` (halaman 2–6) dengan headline TypeCraft memakai font instance (Archivo VX / League Gothic W79) — PERLU diganti ke font lock sesuai keputusan headline. QA lama: `vectally/work/headline_qa/`.
7. QA export semua halaman, kirim 3 link (Feed, Story, HL).

## Infrastruktur browser (bila perlu otomasi Canva)
- Chrome khusus Claude: `"C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="D:\Codex\chrome-claude-profile" --remote-debugging-port=9333 --remote-debugging-address=127.0.0.1 --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --disable-background-timer-throttling` (sudah login Canva akun galenzahid04).
- Jembatan CUSBE: `python -I D:/Codex/cusbe-remote-mcp/scripts/claude_gateway_bridge_v2.py 8765 D:/Codex/cusbe-remote-mcp/config/upstreams.claude-cdp.json` (POST 127.0.0.1:8765 {name, arguments, timeout}). Upload file harus dari `D:\Codex\cusbe-remote-mcp\.playwright-mcp\uploads\`.
- Pelajaran: halaman aktif harus diset (gulir kanvas ke halaman + klik area kosong di samping) sebelum menambah elemen; satuan jarak TypeCraft ±2x model PIL dan ikut kerning.
- User TIDAK mau desktop takeover. Jangan isi password / lewati CAPTCHA.

## Lain-lain
- Banner Canva "Pembayaran terakhir gagal" (Canva Bisnis) — beri tahu user bila relevan.
- Dorvan dan KINRAVA menyusul setelah VECTALLY (KINRAVA font lock: Anton, Barlow Condensed ExtraBold, Manrope).
