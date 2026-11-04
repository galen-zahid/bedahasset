# bedahasset

CLI untuk "membedah" desain feed sosmed hasil AI yang sudah flat (PNG) menjadi layer-layer
terpisah yang bisa disusun ulang dan diedit di Canva.

```
run.bat                             # Windows: klik dua kali (in -> out)
python split.py in out              # batch semua PNG/JPG di folder
python split.py in\x.png out        # satu file
python split.py in out --force      # proses ulang walaupun sudah pernah selesai
python split.py in out --config config_lain.yaml
```

- **Resume**: desain yang sudah punya `out/<nama>/manifest.json` di-skip. Hasil ditulis dulu ke
  `out/.<nama>.partial/` dan baru di-rename kalau sukses, jadi file yang setengah jadi tidak
  akan dianggap selesai.
- **Log** ada di `out/log.txt`. Satu file yang error dicatat (dengan traceback) dan batch tetap lanjut.
- Jalan di CPU; otomatis pakai GPU (CUDA) kalau tersedia (`device: auto` di `config.yaml`).

## Setup di Windows (cara paling gampang)

Yang dibutuhkan: **Python 3.11** (https://www.python.org/downloads/, centang *Add to PATH*),
koneksi internet, dan ruang kosong **±5 GB** (±2.5 GB untuk library di folder project, ±2 GB
untuk model AI di folder user `C:\Users\<nama>`).

1. Ambil project ini, misalnya `git clone -b ccr-6e448746-jedgxp https://github.com/galen-zahid/bedahasset.git`
   atau download ZIP dari GitHub lalu extract. Contoh: ke `D:\bedahasset`.
2. **Klik dua kali `setup.bat`.** Skrip ini akan membuat `.venv`, meng-install semua library, mengecek
   instalasi, lalu men-download semua model AI.
   - Kalau koneksi putus, jalankan `setup.bat` lagi. Langkah yang sudah beres dilewati dan download
     model **dilanjutkan dari posisi terakhir** (tidak mulai dari nol).
   - Punya GPU NVIDIA? Dari PowerShell jalankan `.\setup.bat -Gpu`.
3. Taruh gambar (PNG/JPG) di folder `in`.
4. **Klik dua kali `run.bat`.** Hasilnya muncul di folder `out`, satu subfolder per desain.

Dari PowerShell juga bisa:

```powershell
cd D:\bedahasset
.\run.bat                                   # in -> out
powershell -ExecutionPolicy Bypass -File run.ps1 -In D:\desain -Out D:\hasil
powershell -ExecutionPolicy Bypass -File run.ps1 -Force   # proses ulang semuanya
.\.venv\Scripts\python.exe split.py --check            # cek instalasi
.\.venv\Scripts\python.exe split.py --download-models  # download/cek model saja
```

- Desain yang sudah selesai otomatis di-skip, jadi batch boleh dihentikan (Ctrl+C) lalu dilanjutkan.
- Satu file yang error tidak menghentikan batch. Detailnya ada di `out\log.txt`.
- Drive C: penuh? Isi `cache_dir: "D:/ai-cache"` di `config.yaml`, maka semua model disimpan di sana.

### Instalasi manual (kalau tidak mau pakai setup.bat)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1      # kalau diblokir: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu   # GPU: .../whl/cu124
pip install -r requirements.txt
pip install --no-deps simple-lama-inpainting==0.1.2
python split.py --download-models
```

### Model AI (di-download sekali, ±2 GB)

| model | dipakai untuk | lokasi default |
|---|---|---|
| BiRefNet-general (~970 MB) | cutout subject | `%USERPROFILE%\.rembg\models\` |
| big-lama (~200 MB) | inpaint background | `%USERPROFILE%\.cache\torch\hub\checkpoints\` |
| Depth-Anything-V2-Small (~100 MB) | foreground by depth | `%USERPROFILE%\.cache\huggingface\` |
| CLIPSeg rd64-refined (~600 MB) | lokasi awan debu/kapur/asap | `%USERPROFILE%\.cache\huggingface\` |
| SAM vit-base (~375 MB) | memisahkan objek yang menempel (orang vs barbell, 2 orang) | `%USERPROFILE%\.cache\huggingface\` |
| EasyOCR en (~100 MB) | baca teks | `%USERPROFILE%\.EasyOCR\` |

Waktu per desain (~1100×1400) di CPU 4 core: ±1–2 menit, separuhnya untuk BiRefNet. Di GPU jauh
lebih cepat. Kalau terlalu lambat, ganti `subject.rembg_model` ke `birefnet-general-lite`
(2–3× lebih cepat, tepi sedikit lebih kasar).

## Output per desain: `out/<nama>/`

| file | isi |
|---|---|
| `01_background.png` | clean plate: subject, objek foreground, teks, tombol, glow dan partikel dihapus lalu di-inpaint (LaMa) |
| `02_element_NN_<kategori>.png` | subject **dipecah per elemen** (orang, barbell, ikon, garis penghubung, dll.), masing-masing transparan, ukuran kanvas penuh. Kategori: `asset_large`/`asset_small` (foto), `vector_large`/`vector_icon` (ilustrasi), `shape` (flat: garis, konektor, badge). Kalau subject cuma satu elemen, namanya tetap `02_subject.png`. Gabungannya ada di `extra/02_subject_all.png` |
| `03_foreground_NN.png` | objek di DEPAN subject (berdasarkan depth). Tidak dibuat kalau tidak ada |
| `04_stripe_NN_base.png` | strip di belakang subject: oranye **solid 100%**, 1 warna (bisa diganti Rectangle native, lihat `shapes.csv`) |
| `04_stripe_NN_depth.png` | gelap-terang **abu-abu netral** di atas oranye (tanpa warna foto): balok/jendela yang terlihat menembus strip di referensi |
| `04_stripe_NN_grunge.png` | bercak hitam kecil |
| `05_particles.png` | debu/kapur/percikan (bintik kecil + awan/kepulan besar) sebagai overlay transparan |
| `06_grain.png` | film grain + vignette sesuai noise level gambar asli |
| `07_ui_NN.png` | tombol/pill di sekitar teks (mis. CTA), teksnya sudah dihapus. Bisa dipakai langsung atau dibuat ulang dari `text.csv` |
| `vectors/*.svg` | **"pen tool"**: tiap layer flat/vektor (ilustrasi, ikon, garis, tombol, strip) sebagai SVG, path per warna. Upload SVG ke Canva lalu warnanya bisa diganti satu-satu. Ukuran = kanvas, taruh di 0,0 |
| `extra/02_subject_all.png` | semua elemen subject digabung jadi satu (opsional) |
| `crops/` | tiap layer di-crop ke bounding box-nya |
| `manifest.csv` / `.json` | layer, file, type, **category** (background / asset_* / vector_* / shape / support / text), x, y, w, h, z_order, suggested_opacity (+ SSIM, warna aksen, noise, timing di json) |
| `text.csv` | semua teks: string, bbox, warna, estimasi font size (px), plus box/warna tombol kalau ada |
| `shapes.csv` | strip sebagai persegi panjang native Canva: `canva_x, canva_y, canva_w, canva_h, canva_rotation_deg, color_hex, canva_transparency_pct` |
| `preview_recomposite.png` | semua layer ditumpuk ulang (teks TIDAK ikut, karena teks dibuat native di Canva) |
| `out/<nama>_sheet.png` | **contact sheet**: original, recomposite, semua layer (dengan kategori & z_order), semua SVG, dan daftar teks dalam satu gambar. Buat ulang: `python tools/contact_sheet.py out` |
| `preview_diff.png` | selisih vs asli (diperkuat 4×, terang = beda) |

### Cara menyusun di Canva

1. Buat desain dengan ukuran kanvas sama dengan gambar asli (lihat `width`/`height` di manifest.json).
2. Upload layer **full-size** dan taruh semuanya di posisi x=0, y=0 dengan ukuran penuh. Karena ukurannya sama dengan kanvas, otomatis pas 1:1.
   Atau pakai file di `crops/` lalu posisikan sesuai kolom x, y, w, h di `manifest.csv`.
3. Urutan tumpukan ikuti `z_order` (kecil = paling bawah). Biasanya:
   background → stripe_base → stripe_depth → stripe_grunge → subject → foreground → ui → teks → particles → grain.
   (Nomor file bukan urutan tumpukan. Strip ada di BELAKANG subject.)
   Strip native: ganti `04_stripe_NN_base.png` dengan Rectangle Canva memakai
   X/Y/W/H/Rotate/warna/Transparency dari `shapes.csv`, lalu taruh `..._depth.png` dan `..._grunge.png` di atasnya.
4. Set transparency di Canva sesuai `suggested_opacity` (grain disarankan 0.6, karena grain asli
   sudah ada di layer lain dan grain ini terutama untuk menyatukan elemen baru).
5. Buat ulang teks dari `text.csv` sebagai teks native: posisi dari `x,y`, warna `color_hex`,
   ukuran dari `est_font_size_px` (dalam px kanvas; kalau kanvas Canva di-skala, skala juga
   angkanya). Baris `/`, `|`, `[line]`, `[decor]` adalah tanda grafis kecil di sekitar teks
   (pemisah, garis) yang juga sudah dihapus dari background.

### Strip berlapis (`stripe.mode: canva`, default)

Semua layer pakai blend **Normal**, jadi jalan di semua akun Canva. Background tetap bersih.

Strip di referensi berperilaku seperti "oranye × scene": di dalam strip semuanya oranye yang
sama dengan terang-gelap berbeda. Karena itu strip dibangun ulang sebagai:

1. **base**: oranye solid 100% (menutup background, jadi background di bawahnya tidak berpengaruh).
2. **depth**: satu layer abu-abu netral (hitam sampai putih + opacity) yang menggelapkan,
   menerangkan, dan mengurangi saturasi oranye. Rumusnya `C = (1−d)·oranye + d·abu`, dihitung
   per pixel lalu sedikit diblur. Bentuk gelap-terang yang tembus strip ada di sini, tapi tanpa
   warna foto.
3. **grunge**: bercak hitam kecil.

Hasil tumpukannya sangat dekat dengan referensi (rata-rata selisih <8/255 di area strip),
tapi tidak identik per pixel karena layer depth diblur sedikit.

Mode lain: `single` (1 PNG), `multiply` (perlu blend Multiply, 1:1 tapi background di balik
strip ikut berisi scene), `layered` (+ `shade: true` untuk 1:1 dengan layer sisa berisi foto).

### Overlay tanpa blend mode

Canva tidak punya blend mode (screen/add), jadi partikel dan strip diurai menjadi
`asli = (1 − a)·background + a·warna`, yaitu blending "normal" biasa. (warna, a) masuk ke layer
overlay/strip, dan background-nya dibersihkan. Kalau ditumpuk lagi hasilnya mendekati aslinya.

Lampu/pantulan oranye lain di foto (lampu rak, pantulan lantai) sengaja tetap di background;
hanya strip grafis di belakang subject yang dijadikan layer. Mode lama (semua cahaya aksen jadi
overlay) masih ada: `glow.enabled: true` (output `04_glow.png`).

## Tuning

Semua threshold ada di `config.yaml`, lengkap dengan komentar. Yang paling sering perlu disentuh:

- `subject.alpha_lo/hi`, `subject.ambiguous_choke`: tepi subject terlalu tebal atau tipis.
- `background.dilate_px`, `background.lama_max_side`: masih ada "hantu" subject di background.
- `foreground.depth_margin`: objek depan tidak terdeteksi (turunkan) atau terlalu banyak (naikkan).
- `text.min_confidence`, `text.max_subject_overlap`: teks terlewat atau teks di foto ikut terhapus.
- `stripe.*`: deteksi strip di belakang subject (`hue_tol_deg`, `min_behind_frac`,
  `collinear_tol`) dan teksturnya (`texture_sigma`, `subject_clearance_px`).
- `particles.min_contrast`, `particles.max_chroma`, `particles.max_blob_area`: partikel.
- `elements.sam`, `elements.sam_model`: SAM untuk memisahkan objek yang menempel. Lebih cepat:
  `Zigeng/SlimSAM-uniform-77`. Matikan dengan `sam: false`.
- `vectorize.*`: toleransi magic wand dan ketelitian SVG (`svg_epsilon`, `svg_max_colors`).
- `elements.link_cut_frac`: makin besar, makin banyak elemen dipecah (sambungan tebal ikut diputus).
  `elements.enabled: false` untuk kembali ke satu layer subject.
- `particles.cloud.*`: awan debu/kapur/asap besar (CLIPSeg dengan text prompt). Ubah `prompts`
  untuk efek lain (mis. "sparks", "fog"); `max_area_frac` mencegah kabut di seluruh background
  ikut diekstrak.
- `text.fix_text`, `text.space_gap_mult`, `text.caps_tolerance`: perbaikan hasil OCR
  (spasi kata, ALL CAPS, tanda titik).

## Struktur kode

```
split.py               CLI: batch, resume, logging, isolasi error per file, --check, --download-models
setup.bat / setup.ps1  instalasi Windows sekali jalan
run.bat / run.ps1      jalankan di Windows
config.yaml            semua threshold
pipeline/
  config.py            loader config
  download.py          download model yang bisa dilanjutkan + checksum (first run)
  models.py            model (BiRefNet, Depth Anything, EasyOCR, LaMa, CLIPSeg), load sekali per batch, auto GPU
  imageio.py           load/save PNG, bbox
  matting.py           guided filter, levels, feather, island removal, decontaminate warna
  elements.py          pecah subject jadi elemen terpisah (putus sambungan tipis + SAM) + kategori
  vectorize.py         tepi "magic wand" untuk vektor + ekspor SVG ("pen tool")
  subject.py           matte subject + re-matting tepi terhadap clean plate (anti halo)
  text.py              OCR + second pass, mask glyph, deteksi tombol & dekor
  foreground.py        objek di depan subject via depth + connected components
  background.py        mask inpaint, LaMa, kembalikan pixel asli yang jelas background
  stripe.py            strip aksen di belakang subject: deteksi, layer utuh, geometri Canva
  glow.py              deteksi warna aksen + color-to-alpha (mode glow lama, default mati)
  particles.py         partikel kecil + awan debu/kapur (CLIPSeg + color-to-alpha)
  grain.py             estimasi noise, regrain area inpaint, overlay grain + vignette
  composite.py         recomposite, diff, SSIM
  manifest.py          tulis PNG, crop, manifest, text.csv
  runner.py            urutan langkah per desain
```

## Batasan yang diketahui

- Rambut gelap di atas latar gelap secara matematis tidak bisa dipisah dengan sempurna. Helai
  halus yang tidak terlihat oleh BiRefNet sengaja dibuang (supaya tidak ada pita/kabut di latar
  terang), jadi rambut bisa terlihat sedikit lebih "rapi" daripada aslinya.
- Area di belakang subject dan awan adalah hasil "karangan" LaMa, jadi wajar kalau tidak 100%
  realistis saat subject digeser jauh.
- Layer awan di `05_particles` punya lubang berbentuk subject (karena layer ini ada di atas subject).
- OCR font display/grunge masih bisa salah eja; perbaikan otomatis hanya untuk spasi, kapitalisasi,
  tanda titik, dan karakter sampah. Selalu cek `text.csv` (kolom `confidence`).
  Estimasi font size mengasumsikan cap-height ≈ 0.72 em.
- Model segmentasi awan (CLIPSeg) kasar (352 px), jadi bentuk awan berasal dari analisis warna,
  bukan dari model. Awan yang berwarna (asap oranye, dll.) perlu `max_chroma` dinaikkan.
