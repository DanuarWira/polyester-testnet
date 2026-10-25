# Polyester VIP 1 Volume Farming & Grid Trading Bot

Bot trading multi-pair otomatis berperforma tinggi di **Polyester Testnet** yang dirancang untuk mempercepat kenaikan kasta akun dari **VIP 0 ke VIP 1** (serta tier selanjutnya) melalui akumulasi volume perdagangan spot secara konsisten selama 30 hari tanpa menggerus modal oleh potongan fee.

---

## 🌟 Fitur Utama

1. **Zero-Taker Fee Policy (Post-Only Enforced)**:
   - Setiap order limit beli dan jual dipasang dengan flag `post_only=True`.
   - Memastikan akun Anda selalu menjadi **Maker** (fee terendah 0.10% di VIP 0, turun hingga 0.08% di VIP 1, serta potensi rebate).
   - Terbebas dari potongan Taker fee sebesar 0.15%.

2. **Capturing Bid-Ask Spread (Profit Generation)**:
   - Mengambil keuntungan mikro dari selisih spread harga antara order beli dan jual secara berulang, sehingga volume trading yang besar justru memupuk profit dan melindungi saldo dari depresiasi fee.

3. **Multi-Pair Parallel Workers**:
   - Menjalankan loop perdagangan konkuren berbasis Python `asyncio` untuk pasangan spot likuid: `BTC-USDT`, `ETH-USDT`, `BNB-USDT` (dapat dikonfigurasi).

4. **Dynamic Inventory Skewing & Circuit Breaker**:
   - Jika pasar bergerak satu arah dan koin menumpuk, bot otomatis menggeser harga jual lebih dekat ke mid-price untuk segera melepas koin (*rebalance*) dan mengerem pembelian.
   - Dilengkapi *Circuit Breaker*: otomatis membatalkan seluruh order jika spread pasar melebar di atas batas aman (default: 1.5%) atau terjadi lonjakan volatilitas ekstrem.

5. **Live Interactive Terminal UI Dashboard (Rich TUI)**:
   - Progress bar akumulasi volume 30-hari menuju target kasta VIP 1 ($100,000 USD).
   - Tabel status grid per-pair secara real-time.
   - Ringkasan keuntungan (*Realized PnL*), biaya fee yang dibayar, dan estimasi Taker fee yang berhasil dihemat.
   - Log aktivitas transaksi terkini.

6. **Safety & Graceful Shutdown**:
   - Saat Anda menekan `Ctrl + C`, bot secara otomatis membatalkan semua open order di Polyester Testnet sebelum mematikan koneksi.

---

## 📁 Struktur Proyek

```
d:\projects\polyester-testnet\
├── .env.example                     # Template kredensial API & parameter bot
├── .env                             # Kredensial aktif (tidak boleh dibagikan/di-commit)
├── requirements.txt                 # Dependensi: polyester-sdk[realtime], rich, pydantic, aiosqlite
├── run.ps1                          # Launcher otomatis untuk PowerShell
├── run.bat                          # Launcher otomatis untuk Command Prompt (CMD)
├── POLYESTER_TESTNET_DOCUMENTATION.md # Dokumentasi lengkap arsitektur & API Polyester
│
└── src/
    ├── config.py                    # Validasi konfigurasi & parsing .env
    ├── client.py                    # Wrapper AsyncPolyester, Ed25519 signing & healthcheck
    ├── market_data.py               # L2 Orderbook parser & mid-price tracker
    ├── risk.py                      # Dynamic skewing & volatility circuit breaker
    ├── grid_worker.py               # Worker independen per pair (post-only order placement)
    ├── telemetry.py                 # Persistent SQLite database untuk tracking volume VIP 30-hari
    ├── dashboard.py                 # Antarmuka terminal interaktif Rich TUI
    └── main.py                      # Orchestrator & entry point utama
```

---

## 🚀 Panduan Memulai & Menjalankan Bot

### Langkah 1: Dapatkan Kredensial API dari Dashboard Polyester
1. Buka [Polyester Testnet](https://testnet.polyester.com).
2. Masuk menggunakan Web3 Wallet (MetaMask/Rabby) atau Google/Email.
3. Buka menu **API** di sidebar -> Klik **Create Key**:
   - Salin **API Key ID** (format: `ak_...`).
   - Salin **Private Key** (kunci hex 64-karakter). *Catatan: Kunci ini hanya ditampilkan sekali!*
   - Pastikan izin **Spot Trading** dan **Ledger Read** telah dicentang.
4. Buka menu **Profile** -> Salin **Account ID** (format string Base58, misal: `RLxqJGUDg92`).

### Langkah 2: Buat File `.env`
Salin template `.env.example` menjadi `.env`:
```powershell
Copy-Item .env.example .env
```
Buka `.env` menggunakan text editor (Notepad, VS Code, dll.), lalu isi kredensial Anda:
```env
POLYESTER_API_KEY_ID=ak_testnet_xxxxxxxxxxxxx
POLYESTER_API_PRIVATE_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
POLYESTER_ACCOUNT_ID=RLxqJGUDg92

# Pasangan trading yang diproses paralel
TRADING_PAIRS=BTC-USDT,ETH-USDT,BNB-USDT

# Target volume 30 hari untuk naik ke VIP 1
TARGET_30D_VOLUME_USD=100000.0

# Set DRY_RUN=false untuk live trading di testnet, atau true untuk simulasi
DRY_RUN=false
```

### Langkah 3: Pastikan Saldo Ada di Trading Bucket
Polyester memisahkan saldo menjadi **Funding** dan **Trading**:
- Pastikan Anda telah mengklaim Paper Assets (*faucet*) di testnet.
- Buka dashboard Polyester -> Pindahkan saldo yang ingin digunakan bot dari **Funding Bucket** ke **Trading Bucket**.

### Langkah 4: Jalankan Bot
Cukup jalankan salah satu skrip launcher:

**Melalui PowerShell:**
```powershell
.\run.ps1
```

**Atau melalui Command Prompt (CMD):**
```cmd
run.bat
```

**Atau langsung melalui Python:**
```powershell
.venv\Scripts\python.exe -m src.main
```

---

## 🛡️ Mode Simulasi (Dry-Run Mode)

Jika Anda ingin melihat antarmuka dashboard dan menguji alur kerja bot tanpa menaruh order sungguhan di akun testnet Anda, cukup ubah nilai di `.env`:
```env
DRY_RUN=true
```
Bot akan menyimulasikan pergerakan harga pasar, penempatan order post-only, pengisian order acak, dan grafik progres VIP 1 secara visual.

---

## 🛑 Cara Mematikan Bot dengan Aman

Cukup tekan **`Ctrl + C`** pada jendela terminal. 
Bot akan melakukan **Graceful Shutdown**:
1. Menghentikan seluruh worker multi-pair.
2. Memanggil fungsi `cancel_all` untuk membatalkan seluruh order terbuka di Polyester Testnet.
3. Menyimpan database transaksi dan menutup koneksi secara bersih.
