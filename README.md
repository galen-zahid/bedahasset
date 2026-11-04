# bedahasset

CLI untuk "membedah" desain feed sosmed hasil AI yang sudah flat (PNG) menjadi layer-layer
terpisah yang bisa disusun ulang dan diedit di Canva.

```
python split.py in/ out/            # batch semua PNG di folder
python split.py in/x.png out/       # satu file
python split.py in/ out/ --force    # proses ulang walaupun sudah pernah selesai
python split.py in/ out/ --config config_lain.yaml
```

- **Resume**: desain yang sudah punya `out/<nama>/manifest.json` di-skip. Hasil ditulis dulu ke
  `out/.<nama>.partial/` dan baru di-rename kalau sukses, jadi file yang setengah jadi tidak
  akan dianggap selesai.
- **Log** ada di `out/log.txt`. Satu file yang error dicatat (dengan traceback) dan batch tetap lanjut.
- Jalan di CPU; otomatis pakai GPU (CUDA) kalau tersedia (`device: auto` di `config.yaml`).

## Setup (Windows + PowerShell, Python 3.11)

```powershell
cd C:\path\ke\bedahasset
py -3.11 -m venv .venv
# kalau diblokir execution policy:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

# 1) PyTorch - pilih SALAH SATU
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu      # CPU saja
# pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124  # GPU NVIDIA

# 2) dependency lain
pip install -r requirements.txt
pip install --no-deps simple-lama-inpainting==0.1.2

# (opsional, GPU) rembg di GPU:
# pip uninstall -y onnxruntime; pip install onnxruntime-gpu
```

**Run pertama mendownload model** (sekali saja, ±1.4 GB total, butuh internet):

| model | dipakai untuk | lokasi cache |
|---|---|---|
| BiRefNet-general (~970 MB) | cutout subject | `%USERPROFILE%\.u2net\` |
| big-lama (~200 MB) | inpaint background | `%USERPROFILE%\.cache\torch\hub\checkpoints\` |
| Depth-Anything-V2-Small (~100 MB) | foreground by depth | `%USERPROFILE%\.cache\huggingface\` |
| EasyOCR en (~100 MB) | baca teks | `%USERPROFILE%\.EasyOCR\` |

Waktu per desain (~1100×1400) di CPU 4 core: ±70 detik, dan sebagian besar untuk BiRefNet. Di GPU jauh lebih cepat.

## Output per desain: `out/<nama>/`

| file | isi |
|---|---|
| `01_background.png` | clean plate: subject, objek foreground, teks, tombol, glow dan partikel dihapus lalu di-inpaint (LaMa) |
| `02_subject.png` | cutout subject utama, transparan, ukuran kanvas penuh |
| `03_foreground_NN.png` | objek di DEPAN subject (berdasarkan depth). Tidak dibuat kalau tidak ada |
| `04_glow.png` | cahaya/aksen warna dominan sebagai overlay transparan (sudah pre-baked, tanpa blend mode) |
| `05_particles.png` | debu/kapur/percikan kecil sebagai overlay transparan |
| `06_grain.png` | film grain + vignette sesuai noise level gambar asli |
| `07_ui_NN.png` | tombol/pill di sekitar teks (mis. CTA), teksnya sudah dihapus. Bisa dipakai langsung atau dibuat ulang dari `text.csv` |
| `crops/` | tiap layer di-crop ke bounding box-nya |
| `manifest.csv` / `.json` | layer, file, type, x, y, w, h, z_order, suggested_opacity (+ SSIM, warna aksen, noise, timing di json) |
| `text.csv` | semua teks: string, bbox, warna, estimasi font size (px), plus box/warna tombol kalau ada |
| `preview_recomposite.png` | semua layer ditumpuk ulang (teks TIDAK ikut, karena teks dibuat native di Canva) |
| `preview_diff.png` | selisih vs asli (diperkuat 4×, terang = beda) |

### Cara menyusun di Canva

1. Buat desain dengan ukuran kanvas sama dengan gambar asli (lihat `width`/`height` di manifest.json).
2. Upload layer **full-size** dan taruh semuanya di posisi x=0, y=0 dengan ukuran penuh. Karena ukurannya sama dengan kanvas, otomatis pas 1:1.
   Atau pakai file di `crops/` lalu posisikan sesuai kolom x, y, w, h di `manifest.csv`.
3. Urutan tumpukan ikuti `z_order` (kecil = paling bawah). Biasanya:
   background → glow → subject → foreground → ui → teks → particles → grain.
   (Nomor file bukan urutan tumpukan. Glow ada di BELAKANG subject.)
4. Set transparency di Canva sesuai `suggested_opacity` (grain disarankan 0.6, karena grain asli
   sudah ada di layer lain dan grain ini terutama untuk menyatukan elemen baru).
5. Buat ulang teks dari `text.csv` sebagai teks native: posisi dari `x,y`, warna `color_hex`,
   ukuran dari `est_font_size_px` (dalam px kanvas; kalau kanvas Canva di-skala, skala juga
   angkanya). Baris `[decor]` adalah garis/slash kecil di sekitar teks.

### Kenapa overlay-nya "lossless"

Canva tidak punya blend mode (screen/add), jadi glow dan partikel diurai secara matematis menjadi
`asli = (1 − a)·base + a·warna`, yaitu blending "normal" biasa. Base masuk ke `01_background`,
sedangkan (warna, a) masuk ke overlay. Kalau ditumpuk lagi, hasilnya identik dengan aslinya, tapi
overlay-nya bisa dimatikan, digeser, atau diubah opacity-nya.

## Tuning

Semua threshold ada di `config.yaml`, lengkap dengan komentar. Yang paling sering perlu disentuh:

- `subject.alpha_lo/hi`, `subject.ambiguous_choke`: tepi subject terlalu tebal atau tipis.
- `background.dilate_px`, `background.lama_max_side`: masih ada "hantu" subject di background.
- `foreground.depth_margin`: objek depan tidak terdeteksi (turunkan) atau terlalu banyak (naikkan).
- `text.min_confidence`, `text.max_subject_overlap`: teks terlewat atau teks di foto ikut terhapus.
- `glow.hue_tol_deg`, `glow.min_chroma`, `glow.color_mode`: cakupan dan warna glow.
- `particles.min_contrast`, `particles.max_chroma`, `particles.max_blob_area`: partikel.
- `particles.cloud.enabled`: eksperimental, untuk mengekstrak awan debu besar.

## Struktur kode

```
split.py               CLI: batch, resume, logging, isolasi error per file
config.yaml            semua threshold
pipeline/
  config.py            loader config
  models.py            model (BiRefNet, Depth Anything, EasyOCR, LaMa), load sekali per batch, auto GPU
  imageio.py           load/save PNG, bbox
  matting.py           guided filter, levels, feather, island removal, decontaminate warna
  subject.py           matte subject + re-matting tepi terhadap clean plate (anti halo)
  text.py              OCR + second pass, mask glyph, deteksi tombol & dekor
  foreground.py        objek di depan subject via depth + connected components
  background.py        mask inpaint, LaMa, kembalikan pixel asli yang jelas background
  glow.py              deteksi warna aksen + color-to-alpha
  particles.py         partikel kecil (+ awan, eksperimental)
  grain.py             estimasi noise, regrain area inpaint, overlay grain + vignette
  composite.py         recomposite, diff, SSIM
  manifest.py          tulis PNG, crop, manifest, text.csv
  runner.py            urutan langkah per desain
```

## Batasan yang diketahui

- Awan debu/kapur besar (bukan bintik) tetap menempel di background. Mode `cloud` masih eksperimental.
- Rambut gelap di atas latar gelap secara matematis tidak bisa dipisah dengan sempurna. Di latar
  terang mungkin masih ada sedikit kabut tipis (atur `ambiguous_choke`).
- Area di belakang subject adalah hasil "karangan" LaMa, jadi wajar kalau tidak 100% realistis
  saat subject digeser jauh.
- OCR font display/grunge bisa salah eja (kolom `confidence`), jadi selalu cek isi `text.csv`.
  Estimasi font size mengasumsikan cap-height ≈ 0.72 em.
