# Strategy: GTA VI Trophy Rarity Forecast

## 1. Strategy

Pendekatan weighted-history forecasting digunakan karena data rates dari 55 trophy hampir tidak berubah antar history slot (seri pendek, rate stabil). Alih-alih memprediksi tren naik/turun yang tidak terlihat, entry mengambil weighted average dari 4 history terbaru (fungsi `weighted_rate`, line 10-18) dan menghitung quantile spread di sekitar nilai titik tersebut (fungsi `compute_quantiles`, line 21-37). Spread proporsional terhadap tingkat rarity: trophy yang jarang dapat (rate rendah) dapat spread absolut kecil, sementara trophy umum (rate tinggi) dapat spread lebih lebar. Pilihan ini sederhana, stabil, dan tidak membuat nilai quantile melampaui 100% atau turun di bawah 0%.

## 2. Parameter Reasons

- **Window 4 recent reads** (line 45-46): sejarah pendek (6-8 slot), 4 terbaru menangkap informasi paling aktual sambil tetap memberikan konteks. Jika kurang dari 4 tersedia, semua yang ada digunakan.
- **Base-2 exponential weights** (line 51-53): weight terbaru = 2^(n-1), terlama = 2^0. Misal 4 slot: weights [0.25, 0.5, 1.0, 2.0] setelah dinormalisasi. Memberi penekanan kuat pada pembacaan terakhir karena data near-constant berarti drift kecil saja.
- **Spread = 10% of point estimate** (line 24): variasi quantile di sekitar median sebesar 10% dari rate terhitung. Untuk rate 0.63%, spread ~0.063; untuk rate 100%, spread 10. Ini mencerminkan ketidakpastian yang lebih besar pada trophy umum vs. sangat jarang.
- **Minimum spread 0.01** (line 24): mencegah quantile menjadi titik tunggal (semua nilai sama) saat rate sangat kecil; sekurang-kurangnya ada variasi 0.01 di antara quantiles.
- **Clamp [0, 100]** (line 27-28): mencegah quantile negatif atau >100% yang tidak masuk akal secara domain.
- **Round 4 decimals** (line 29): presisi cukup untuk submission tanpa floating-point noise berlebih.
- **Non-decreasing enforcement** (line 31-34): mencegah quantile 0.05 > 0.25 dst. yang bisa terjadi karena rounding atau clamp. Jika q[i] < q[i-1], set q[i] = q[i-1].

## 3. Syntax Check

Kode dijalankan dengan `python3 main.py`. Awalnya muncul `NameError: name 's' is not defined` di line 14 karena typo `s[i]` alih-alih `series[i]` di fungsi `weighted_rate`. Diperbaiki dengan `sed -i 's/s\[i\] \* w\[i\]/series[i] * w[i]/' main.py`. Setelah fix, `python3 main.py` berjalan bersih tanpa error dan menghasilkan `out/p00.out` serta `out/p01.out`. Verifikasi output: 55 rows per file, 5 quantiles per row, semua nilai dalam [0,100], non-decreasing per row — semuanya `True`.

## 4. Crash Risk

- **Empty history**: `recent = []`, `weights = []`, `weighted_rate` mengembalikan 0.0 (line 11-12). `compute_quantiles(0.0, levels)` menghasilkan quantiles sekitar 0 dengan spread 0.01, semua dalam [0,100]. Aman.
- **Single read**: `weights = [1.0]`, `weighted_rate` mengembalikan rate tersebut. Aman.
- **Missing/short rates**: Jika history entry tidak memiliki rate untuk semua 55 trophy, `series` akan lebih pendek dari `weights` dan `weighted_rate` menggunakan `weights[:n]` (line 13). Namun input kompetisi selalu memiliki rates lengkap 55 nilai per entry; asumsi ini valid.
- **Malformed JSON**: `json.load` akan raising exception. Harness competition menyediakan case file yang well-formed; jika terjadi, entry akan gagal tapi tidak corrupt output yang sudah ditulis karena penulisan hanya dilakukan setelah parse berhasil.
- **Output directory missing**: `os.makedirs(output_dir, exist_ok=True)` (line 86) membuat direktori jika belum ada.
- **Rates di luar [0,100]**: clamp di `compute_quantiles` (line 27-28) menangani nilai ekstrem yang mungkin muncul di history.

## 5. Conclusion

Entry telah berjalan dan menghasilkan output yang tervalidasi: 55 rows × 5 quantiles non-decreasing dalam [0,100] untuk kedua case (p00, p01). Format sesuai keperluan kompetisi. Entry siap untuk submit; sisa pekerjaan hanya memastikan lingkungan MAKEFUN_INPUT_DIR dan MAKEFUN_OUTPUT_DIR pointing ke direktori yang tepat saat evaluasi, yang sudah ditangani oleh fallbacks `"input"` dan `"out"` di `main()`.
