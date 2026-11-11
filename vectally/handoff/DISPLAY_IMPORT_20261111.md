# Impor display copy S02, S04, S05 (11 Nov 2026)

Salinan kerja: `DAHakqcLPHk`. Halaman 1 adalah salinan S02 lama dari `DAHabUK1x7c`; halaman 2 kandidat S03 (copy kecil saja), halaman 3, 4, 5 kandidat S02, S04, S05. Importer menyisipkan halaman baru setelah halaman aktif, jadi cek nomor halaman setelah impor. Desain lain tidak diubah.

Font: `YACgEZ1OEPI` terbukti League Gothic (normal dan italic) lewat `findFonts`. Headline S01 cocok ke League Gothic lebar 75–85 (IoU 0.76–0.80), sedangkan lebar normal yang tersedia native hanya 0.55–0.57. Headline besar S03 (WHICH, REPORT, SHOWS, PROFIT?) maksimal 0.44–0.66 dengan font native.

Status: RENDERED di Canva, TECHNICAL PASS untuk font native. VISUAL PASS, buyer edit-test, dan USER APPROVED belum.

## Alur yang terbukti
1. `work/s01_s05_display_fit.py` memilih font, sudut, ukuran, spacing dari sumber.
2. `work/s02_s04_s05_display_package.py` menulis `ASSETS_DISPLAY_COPY_PACKAGE.json` tanpa menimpa paket lama.
3. `canva apps start` di `D:\cusbe-importer`, lalu buka desain dengan parameter `ui` app importer.
4. Upload lewat CUSBE butuh `Authorize-Privileged.ps1`. `browser_file_upload` gagal (`DOM.setFileInputFiles: Not allowed`), jadi file dimasukkan lewat `File`/`DataTransfer` dari server lokal 127.0.0.1.
5. Klik elemen panel bisa timeout saat tab Chrome di belakang; `el.click()` lewat `browser_evaluate` berhasil.
6. Koreksi posisi dari export memakai `position_element`, lalu ukur dengan `work/s02_s04_s05_display_qc.py`.

## Temuan
- Asap Condensed bold (`YAD1fmY3NpE,0`) masuk sebagai teks native lewat importer.
- `position_element` memakai kotak luar elemen setelah rotasi, bukan left/top elemen. Rotasi -86 terlempar keluar halaman sebelum dikoreksi.
- Kotak teks perlu lebih lebar dari perkiraan lokal. `LOSS.` sempat terbungkus pada width 928; sekarang 1010.

## Hasil ukur setelah koreksi
Metrik: `outputs/VECTALLY-story-repair/display-import-20261111/after/metrics.json`. Ukuran ink 0.94–1.05 dari sumber, geser pusat maksimal 6 px, IoU di tempat 0.52–0.78. IoU ini tidak membuktikan 1:1.

## Belum selesai
- S04 `LOSS.`: bentuk font lebih ringan dari sumber; perlu keputusan visual.
- S01 `THE BOOKS`, `STORY.`: butuh League Gothic condensed; identitas `YACgEZ1OEPI` belum dicek.
- S03: copy miring perlu TypeCraft.
- S06: blocker Asap heavy, menunggu keputusan pengguna.
- Gradien, buyer edit-test, dan konsolidasi ke koleksi utama.
