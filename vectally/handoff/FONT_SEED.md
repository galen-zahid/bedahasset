# Font seed VECTALLY (10 Nov 2026)

Tujuan: membuat teks native dengan font yang benar lewat connector Canva, tanpa CUSBE.
`add_text` selalu jatuh ke font default, jadi teks dibuat dari kotak yang sudah ada.

## Desain
- Seed: `DAHah8U-f6k` "VECTALLY_FONT_SEED_v01 (working copy)". Salinan halaman 12, 9, 13 dari `DAHabUK1x7c`; sumber tidak diubah.
- Uji buangan: `DAHah3osRc0` (boleh dihapus kalau user setuju).

| Halaman | Ukuran | Kotak teks |
|---|---|---|
| 1 | 1122x1402 (Feed) | Archivo Black 8, Asap 5, font OEPI 4 |
| 2 | 941x1672 (Story) | Archivo Black 1, Asap normal 4, Asap bold 1 |
| 3 | 941x1672 (Story) | Archivo Black 1, Asap normal 2, Asap "heavy" 5 |

## Cara pakai
1. `copy-design` dengan satu `page_numbers` per salinan. Nomor halaman duplikat (`[2,2,1]`) gagal; satu halaman berhasil.
2. Page ID berubah di salinan, element ID tetap. Baca ulang locator dari salinan.
3. `replace_text`, `format_text`, `resize_element`, `position_element`, lalu hapus kotak yang tidak dipakai.
4. Jangan `ungroup_elements` kalau masih perlu ID anaknya: ID anak berubah setelah ungroup.

## Hasil uji (draft dibatalkan)
| Uji | Hasil |
|---|---|
| Ganti teks, dua baris, ukuran, warna, line height, lebar, posisi | PASS, `fontRef` tetap |
| `font_weight` bold pada kotak Asap normal | PASS, render tebal |
| Letter spacing | Ikut kotak seed, connector tidak bisa mengubah |

## Belum selesai
- CHECK: Asap "heavy" terbaca di `read-design` dan di halaman 3, tetapi katalog tidak memuatnya dan render belum dibuktikan benar heavy. Guard S06 tidak diubah.
- CHECK: `YACgEZ1OEPI,0` (font display, 20 kotak di desain uji) tidak ada di `FONT_CATALOGUE.json`; namanya belum diketahui.
- BLOCKED: Asap medium, Asap semibold, Asap Condensed belum punya kotak seed. Belum ada halaman Canva yang memakainya.
- BLOCKED: Playwright ke editor Canva kena verifikasi bot (HTTP 403, "Just a moment..."). Tidak dicoba diakali.
- Jumlah kotak per halaman seed terbatas; connector tidak bisa menduplikat kotak teks.
- `merge-designs` diperlukan untuk menyatukan salinan satu halaman; belum diuji di sini.
