# Pipeline aset VECTALLY versi Claude, untuk dikoreksi Codex

Repo: `D:\bedahasset`, branch `ccr-6e448746-jedgxp`, folder kerja `vectally\`.
Hasil terbaru di Canva: `DAHalMGU_GQ`, halaman 2–6 = S01–S05. Pembanding kualitas: desain Codex `DAHaawX9Fm8`.

## Status setelah review Codex (11 Nov 2026)
Sudah diperbaiki di `smooth_native_paths.py`, `render_package_svg.py`, `s01_connector.py`: F1 (gerbang topologi di semua jalur), F2/F3 (jembatan lubang dipilih per indeks dan dicek di dalam badan), F4 (tangen G1 di sambungan halus), F5 sebagian (uji lengkung garis, pengenal elips, fallback 0.8), F7, F8.
Belum: batas bersama antarbagian, klasifikasi dari PNG sumber yang generik, F6 (headline menunggu font dan TypeCraft).
Paket `ASSETS_GEOM2_PACKAGE.json` dibuat sebelum perbaikan ini dan perlu dibangun ulang.
S03 sudah dibangun per objek dari PNG sumber: `work/s03_objects.py` -> `S03/ASSETS_OBJECT_PACKAGE.json`, halaman 2 di `DAHalMGU_GQ`. Uji pindah, ganti warna, dan ganti teks di Canva lolos, tidak disimpan.

## Alur
```
PNG sumber
  -> paket lama (mask + kontur poligon, work/native_contour_path.py)
  -> work/smooth_native_paths.py     rekonstruksi per shape
  -> work/s01_book_primitives.py     geometri tangan: donut, checklist, garis tengah (S01)
  -> work/s01_connector.py           jalur konektor, panel, titik (S01)
  -> ASSETS_GEOM2_PACKAGE.json
  -> CUSBE Native Importer (D:\cusbe-importer, Apps SDK)
  -> export Canva -> bandingkan zoom dengan sumber
```

## Cara jalan
Python: `D:\bedahasset\.venv\Scripts\python.exe`, working dir `vectally\`. Output tidak menimpa file yang sudah ada.
```
SMOOTH_ROUND=0 python work/smooth_native_paths.py outputs/VECTALLY-story-repair/S01/ASSETS_NORMAL_COPY_PACKAGE.json tmp1.json
python work/s01_book_primitives.py tmp1.json tmp2.json
python work/s01_connector.py tmp2.json outputs/VECTALLY-story-repair/S01/ASSETS_GEOM2_PACKAGE.json
python work/s02_s05_clean_batch.py
```

## Isi tiap program
| File | Fungsi |
|---|---|
| `work/smooth_native_paths.py` | Inti. Render shape 4x, blur ringan, ambil kontur, lalu rekonstruksi |
| `work/s01_book_primitives.py` | Donut dari `cv2.fitEllipse` + titik batas terukur; checklist dan garis tengah dari koordinat terukur |
| `work/s01_connector.py` | Cabang = polyline berjari-jari yang di-offset konstan; pil dan lingkaran dari busur cubic |
| `work/s02_s05_clean_batch.py` | Jalankan rekonstruksi S02–S05, buang Asap Condensed, pasang posisi teks terukur |
| `work/render_package_svg.py` | Render paket ke PNG lewat resvg untuk inspeksi. Teks tidak dirender |
| `work/s01_s05_display_fit.py`, `s01_s05_brand_classify.py` | Fit font dan klasifikasi headline |
| `work/s02_s04_s05_display_qc.py` | Ukur tinta headline export terhadap sumber |

## Logika `smooth_native_paths.py`
Per shape, urutannya:
1. Lewati kalau path sudah punya kurva, multi-path, atau seukuran halaman. Lewati juga kalau luasnya kecil.
2. `minAreaRect`: kalau batang (rasio <= 0.33, isi >= 0.8) atau isi >= 0.985, ganti persegi miring. Ujung dianggap bulat kalau minimal 3 dari 4 sudut kosong.
3. `fit_loop`: `approxPolyDP` eps 1 px. Edge dianggap lurus kalau panjang >= 10 px dan tiap ujungnya berbelok >= 22° atau edge itu >= 2.2x edge tetangganya.
4. Sisi lurus dipas least-squares (SVD). Sudut = perpotongan dua garis, maksimal geser 3.5 px.
5. Bagian non-lurus dipecah di sudut >= 45°, lalu dipas cubic gaya Schneider. Toleransi dicoba 1.4, 1.1, 0.85, 0.6, lalu 1.8, 2.4.
6. Lubang memakai jembatan lebar-nol karena satu path hanya boleh satu M. Batas 1850 byte per path.
7. Gerbang IoU terhadap shape asal: 0.93 tebal, 0.8 tipis, 0.75 untuk toleransi kasar. Gagal: fallback kurva saja, lalu biarkan shape lama.

## Kelemahan yang sudah diketahui
- **Input masih poligon lama, bukan PNG sumber.** Tepi direkonstruksi dari mask ambang yang sudah kehilangan antialias. Ini kelemahan terbesar.
- **Rekonstruksi per shape, bukan per objek.** Batas antarbagian dalam satu objek tidak disatukan, jadi bagian yang bersambung bisa punya tepi berbeda.
- **Geometri bersih hanya S01 yang digambar tangan.** Koordinat di `s01_book_primitives.py` dan `s01_connector.py` khusus gambar itu, belum generik untuk 84 sumber.
- **Kurva masih terlalu banyak** di shape panjang: badan kartu S03 dan sapuan hijau S03. Ini melanggar "titik kontrol sesedikit yang diperlukan".
- **Tangen sambungan garis ke kurva tidak dipaksa kontinu.** Di `fit_loop` baris `t1 = ... if False else None` adalah sisa kode mati, jadi `t1` selalu `None`.
- **`to_path` memilih titik jembatan lubang secara kasar**, dan `_inner_corners` punya variabel `a` yang tidak dipakai.
- **Ambang dipilih empiris** dari S01–S05: 22°, 45°, 2.2x, 0.33, 0.8.
- **Warna solid.** Gradien, bayangan halus, dan lapisan transparan belum direkonstruksi.
- **`SMOOTH_ROUND=0` untuk S01 adalah tambalan**, karena deteksi ujung bulat salah pada batang tipis.
- **Validasi belum lengkap.** Uji pindah di Canva baru satu grup (kartu S03). Background kontras baru lokal.

## Yang minta dikoreksi
1. Apakah rekonstruksi sebaiknya memakai PNG sumber langsung, dan bagaimana cara Codex menentukan titik pada A03 dan A07?
2. Bagaimana menyatukan batas antarbagian dalam satu objek tanpa menimpa urutan layer?
3. Apa cara generik untuk stroke atau konektor, supaya tidak perlu koordinat tangan tiap gambar?
4. Ambang mana yang salah, dan shape mana di `ASSETS_GEOM2_PACKAGE.json` yang harus dibangun ulang?
5. Bagian pipeline Codex mana yang harus dipakai langsung menggantikan kode ini?

Aturan tetap: kelompokkan per aset, badan benda utuh, jangan ubah copy jadi vektor statis, font hanya League Gothic, Archivo Black, Asap. Jangan timpa paket lama.
