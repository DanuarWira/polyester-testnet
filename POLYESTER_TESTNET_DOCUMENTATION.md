# Polyester Testnet: Panduan Arsitektur, Autentikasi, Keamanan & Dokumentasi API Lengkap

Dokumentasi komprehensif ini disusun berdasarkan penelaahan mendalam terhadap portal resmi [Polyester Testnet](https://testnet.polyester.com/docs/user-docs/start), arsitektur blockchain L1 Polyester, protokol *Zipper* & *PolyEngine*, serta spesifikasi API (ConnectRPC, REST, WebSocket Centrifugo) dan SDK resmi (`@polyester/sdk`, `polyester-sdk`). Dokumen ini ditujukan sebagai referensi teknis utama sebelum merancang arsitektur dan *development plan* proyek.

---

## Daftar Isi
1. [Ringkasan Eksekutif & Arsitektur Inti Platform](#1-ringkasan-eksekutif--arsitektur-inti-platform)
2. [Alur Pengguna & Panduan Memulai (User Docs: Start Here)](#2-alur-pengguna--panduan-memulai-user-docs-start-here)
3. [Arsitektur Autentikasi & Keamanan Mendalam](#3-arsitektur-autentikasi--keamanan-mendalam)
   - [3.1 Autentikasi Web3 Wallet & Smart Accounts (EIP-4361 / SIWE)](#31-autentikasi-web3-wallet--smart-accounts-eip-4361--siwe)
   - [3.2 Autentikasi Programatik API Key (Ed25519 Cryptographic Signing)](#32-autentikasi-programatik-api-key-ed25519-cryptographic-signing)
   - [3.3 Formula & Spesifikasi Canonical Request Signing](#33-formula--spesifikasi-canonical-request-signing)
   - [3.4 GuardSigner & Perlindungan Bertingkat MFA (Multi-Factor Authentication)](#34-guardsigner--perlindungan-bertingkat-mfa-multi-factor-authentication)
   - [3.5 Network Security & Scoped Permissions](#35-network-security--scoped-permissions)
4. [Katalog & Spesifikasi Seluruh API (ConnectRPC, REST, WebSocket)](#4-katalog--spesifikasi-seluruh-api-connectrpc-rest-websocket)
   - [4.1 Network Endpoints & Protokol Transport](#41-network-endpoints--protokol-transport)
   - [4.2 Layanan RPC & Endpoint Utama](#42-layanan-rpc--endpoint-utama)
   - [4.3 Struktur Buku Order, Tipe Order & Skema Fee](#43-struktur-buku-order-tipe-order--skema-fee)
   - [4.4 Real-time Streaming WebSocket (Centrifugo)](#44-real-time-streaming-websocket-centrifugo)
5. [Spesifikasi & Panduan Penggunaan SDK Resmi](#5-spesifikasi--panduan-penggunaan-sdk-resmi)
   - [5.1 Python SDK (`polyester-sdk`)](#51-python-sdk-polyester-sdk)
   - [5.2 TypeScript SDK (`@polyester/sdk`)](#52-typescript-sdk-polyestersdk)
6. [Checklist Rekomendasi Sebelum Menyusun Project Plan](#6-checklist-rekomendasi-sebelum-menyusun-project-plan)

---

## 1. Ringkasan Eksekutif & Arsitektur Inti Platform

**Polyester** adalah bursa desentralisasi (*Decentralized Exchange* / DEX) buku order (*order-book*) spot dan peminjaman (*lending*) lintas rantai (*cross-chain*) berperforma tinggi. Polyester dikembangkan oleh Fabric Labs di atas fondasi teknologi mutakhir:

```
+-------------------------------------------------------------------------+
|                              Aplikasi Klien                             |
|          Web App (React/Turnkey)  /  Trading Bots  /  Institusional      |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                            Lapisan Akses API                            |
|     ConnectRPC (Protobuf/JSON)  |  REST /v1  |  WebSocket Centrifugo    |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                  PolyEngine (Matching Engine v0.4+)                     |
|     Eksekusi sub-millisecond, order-book matching, risk management      |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                      Polyester Chain (Layer 1 EVM)                      |
|       Smart Accounts (ERC-4337 style), Gas Abstraction/Sponsorship      |
|               Unified Ledger (Funding vs Trading Buckets)               |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                            Zipper Protocol                              |
|   Cross-Chain Asset Wrapping, Vaults & Validators (Sepolia, Fuji, BSC)  |
+-------------------------------------------------------------------------+
```

### Komponen Utama:
1. **Polyester Chain (EVM Layer 1)**: Rantai blok independen yang mengabstraksi gas (*gas sponsorship*) sehingga pengguna tidak perlu memikirkan biaya bahan bakar (*native gas*) saat bertransaksi. Semua akun adalah *Smart Accounts*.
2. **PolyEngine (Matching Engine)**: Mesin pencocokan berkecepatan sub-milidetik yang mampu memproses throughput ribuan order per detik dengan latensi rendah.
3. **Zipper Protocol**: Jembatan desentralisasi dan validasi aset lintas rantai. Pengguna mendepositokan aset dari rantai eksternal (Ethereum Sepolia, Avalanche Fuji, BSC Testnet), dan Zipper secara instan mengonversinya menjadi *Unified Assets* tanpa perlu *bridging* manual yang lambat.
4. **Paper Assets (Testnet Tokens)**: Lingkungan uji coba menyediakan aset uji (`tETH`, `tBTC`, `tBNB`, `tAVAX`, `tUSDT`) yang dapat diklaim melalui faucet untuk pengujian strategi bebas risiko.

---

## 2. Alur Pengguna & Panduan Memulai (User Docs: Start Here)

Berdasarkan panduan resmi `user-docs/start`, proses *onboarding* pengguna terdiri dari langkah-langkah berikut:

### 1. Koneksi Akun & Smart Account Derivation
- **Metode Masuk**:
  - Web3 Wallets: MetaMask, Rabby, Phantom, WalletConnect.
  - Social / Embedded Logins: Menggunakan email / Google melalui Turnkey.
- **Tanpa KYC**: Tidak ada proses verifikasi identitas (KYC) untuk membuat akun, deposit, trading, maupun penarikan.
- **Abstraksi Akun**: Akun pengguna di Polyester adalah *Smart Account*. EOA (*Externally Owned Account*) milik pengguna bertindak sebagai pemilik (*owner*). Alamat smart account diturunkan secara deterministik; tidak ada deployment on-chain yang dipicu saat pertama kali login.

### 2. Struktur Akun Dua Kantong (Funding vs Trading Buckets)
Buku besar (*ledger*) akun Polyester memisahkan saldo menjadi dua kantong (*buckets*):
- **Funding Bucket**: Tempat aset mendarat setelah didepositkan dari rantai luar melalui Zipper. Kantong ini aman dari risiko perdagangan aktif.
- **Trading Bucket**: Saldo gabungan terpadu (*unified trading balance*) yang menjadi margin dan agunan untuk mengeksekusi order spot di PolyEngine.
- **Transfer Internal**: Saldo dapat dipindahkan antara *Funding* dan *Trading* secara instan melalui API/UI menggunakan *signed intent*.

### 3. Alur Deposit & Penarikan
- **Deposit**: Buka menu Deposit -> Pilih aset & rantai asal (misal: Sepolia tETH) -> Kirim transaksi dari dompet eksternal ke alamat kontrak Zipper Vault. Setelah validator Zipper memverifikasi, saldo langsung dikreditkan sebagai *Unified Asset*.
- **Trading**: Saldo di trading bucket langsung dapat dipasangkan pada buku order pasar spot.
- **Withdrawal**: Penarikan aset ke rantai luar tunduk pada kebijakan *Address Book*, *Whitelist*, dan verifikasi *GuardSigner*.

---

## 3. Arsitektur Autentikasi & Keamanan Mendalam

Aspek keamanan Polyester dibangun secara berlapis (*defense-in-depth*) dengan standar kriptografi modern:

```
+-------------------------------------------------------------------------------+
|                       STRATIFIKASI KEAMANAN POLYESTER                         |
+-------------------------------------------------------------------------------+
| 1. Sesi Browser / Web App : EIP-4361 (SIWE) + EIP-191 Personal Sign           |
| 2. Programmatic API       : Asymmetric Ed25519 Signing + Timestamp (<=10s)     |
| 3. Akses Jaringan         : IP Whitelist / CIDR Masking (hingga 32 IP)        |
| 4. Otoritas Operasi Kritis: GuardSigner Co-Signer + MFA (ClaimFreshStepUp)    |
| 5. Proteksi Saldo         : Separasi Funding Bucket vs Trading Bucket         |
+-------------------------------------------------------------------------------+
```

### 3.1 Autentikasi Web3 Wallet & Smart Accounts (EIP-4361 / SIWE)

Untuk interaksi frontend atau dashboard:
1. **Challenge Request**: Klien memanggil endpoint ConnectRPC:
   - Endpoint: `POST https://api.testnet.polyester.com/auth.v1.AuthService/CreateWalletChallenge`
   - Payload:
     ```json
     {
       "purpose": "LOGIN",
       "signerAddress": "0xYourEOAAddress...",
       "smartAccountAddress": "0xYourSmartAccountAddress...",
       "uri": "https://testnet.polyester.com"
     }
     ```
2. **Canonical Message**: Server merespons dengan pesan berformat standar EIP-4361 (*Sign-In with Ethereum*) yang memiliki masa berlaku (*expiry*) 5 menit.
3. **Pemberian Tanda Tangan**: Pengguna menandatangani pesan menggunakan `personal_sign` (EIP-191) melalui wallet EOA (menghasilkan tanda tangan biner 65-byte).
   > **Perhatian**: Untuk login sesi utama, Polyester menolak format tanda tangan Safe/ERC-6492. Tanda tangan mentah 65-byte EIP-191 dari EOA pemilik wajib digunakan.

---

### 3.2 Autentikasi Programatik API Key (Ed25519 Cryptographic Signing)

Untuk bot trading, backend service, dan integrasi API otomatis, Polyester **TIDAK MENGGUNAKAN** static secret token biasa atau shared HMAC secret. Sebagai gantinya, Polyester menggunakan **kriptografi asimetris kurva Ed25519**:

1. **Pembuatan Keypair Mandiri**:
   - Pengembang membuat pasangan kunci Ed25519 secara lokal di mesin klien (menghasilkan private key 64-byte dan public key 32-byte).
   - **Private key TIDAK PERNAH dikirimkan ke server Polyester.**
2. **Pendaftaran Public Key**:
   - Public key (32 bytes raw, di-encode dalam Base64) didaftarkan ke Polyester melalui endpoint `POST /v1/auth/api-keys` (atau via UI).
   - Parameter registrasi:
     - `label`: Nama identitas key (1-64 karakter).
     - `publicKeyEd25519`: String Base64 dari 32 raw bytes public key.
     - `subaccountId`: (Opsional) Mengikat key hanya ke subaccount tertentu. Jika dikosongkan, key menjadi root account key.
     - `ipWhitelist`: (Opsional) Array string berisi hingga 32 subnet IPv4/IPv6 CIDR.
3. **Header Permintaan HTTP Wajib**:
   Setiap request privat ke endpoint Polyester harus menyertakan 3 header:
   - `X-API-KEY-ID`: ID unik API Key yang diperoleh saat registrasi (format: `ak_...`).
   - `X-API-TIMESTAMP`: Waktu saat ini dalam Unix epoch milliseconds (`Date.now()`).
   - `X-API-SIGNATURE`: Tanda tangan Ed25519 atas *canonical request string*.

---

### 3.3 Formula & Spesifikasi Canonical Request Signing

Untuk mencegah manipulasi *in-flight* dan serangan *replay attack*, setiap request harus ditandatangani sesuai spesifikasi kanonikal ketat:

#### Formula Canonical String
Canonical string dibentuk dengan menggabungkan 5 komponen yang dipisahkan oleh satu karakter newline (`\n`):

$$\text{CanonicalString} = \text{timestamp\_ms} + \text{"\\n"} + \text{HTTP\_METHOD} + \text{"\\n"} + \text{path} + \text{"\\n"} + \text{canonical\_query} + \text{"\\n"} + \text{body\_sha256\_hex}$$

> **PENTING**: **Jangan** menambahkan karakter newline penutup (`\n`) di akhir string.

#### Rincian Komponen:
1. `timestamp_ms`: Nilai string numerik millisecond yang **sama persis** dengan isi header `X-API-TIMESTAMP`.
2. `HTTP_METHOD`: Huruf kapital metode HTTP (`GET`, `POST`, `DELETE`, `PUT`).
3. `path`: Jalur path absolut endpoint, contoh: `/v1/spot/fee-rates` atau `/trade.v1.TradeService/PlaceOrder`.
4. `canonical_query`: String query URL yang telah diurutkan menurut abjad (*alphabetical order*). Jika tidak ada query string, gunakan string kosong `""`.
5. `body_sha256_hex`: Hash SHA-256 (format string hex lowercase 64 karakter) dari isi body request mentah UTF-8.
   - Jika request tidak memiliki body (seperti pada metode `GET`), nilai ini wajib berupa hash SHA-256 dari string kosong:  
     `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

#### Eksekusi & Encoding Signature:
1. Hitung tanda tangan Ed25519 dari byte UTF-8 `CanonicalString` menggunakan **Private Key Ed25519** klien (menghasilkan 64 bytes signature).
2. Encode signature ke dalam salah satu dari dua format yang didukung:
   - **Hexadecimal string** (128 karakter lowercase), atau
   - **Base64 string** (88 karakter standard padded).
3. Masukkan ke dalam header `X-API-SIGNATURE`.

#### Toleransi Skew Waktu (Anti-Replay Attack)
Server Polyester memberlakukan validasi waktu ketat: perbedaan antara `X-API-TIMESTAMP` dan waktu server **tidak boleh melebihi 10 detik** ($\pm 10\text{ detik}$). Jika lewat, server langsung menolak dengan error clock skew. Server NTP yang sinkron adalah kewajiban pada server bot.

---

### 3.4 GuardSigner & Perlindungan Bertingkat MFA (Multi-Factor Authentication)

Salah satu inovasi keamanan paling krusial di Polyester adalah **GuardSigner**:

- **Tujuan**: Mencegah peretas yang berhasil mencuri API Key atau membajak sesi trading agar tidak dapat menguras (*drain*) saldo akun ke alamat asing.
- **Mekanisme Kerja**:
  - **Address Book**: Buku alamat untuk menyimpan daftar alamat eksternal terpercaya.
  - **Withdrawal / Transfer Whitelist**: Fitur isolasi keamanan. Ketika whitelist diaktifkan, penarikan atau transfer dana hanya diperbolehkan ke alamat-alamat yang sudah terdaftar.
  - **GuardSigner Service**: Layanan penandatangan sekunder independen (*co-signer*). Setiap modifikasi konfigurasi whitelist (menambah alamat baru, menghapus alamat, atau mematikan whitelist) membutuhkan tanda tangan persetujuan dari GuardSigner.
  - **MFA Step-Up Gate (`auth.v1.MFAService/ClaimFreshStepUp`)**: GuardSigner **tidak akan pernah** menandatangani modifikasi keamanan sebelum pengguna menyelesaikan tantangan Multi-Factor Authentication (MFA / 2FA) secara interaktif.
  - Dengan demikian, kebocoran API Key dengan izin trading tidak dapat mematikan whitelist atau memindahkan dana keluar secara sepihak.

---

### 3.5 Network Security & Scoped Permissions

1. **IP Allowlist / Whitelist**: Setiap API Key dapat dikunci ke maksimal 32 entri CIDR. Request yang berasal dari luar IP ini akan ditolak di level gateway.
2. **Subaccount Isolation**: Pengguna dapat membuat subaccount terpisah untuk setiap strategi trading atau bot. API Key dapat dibatasi cakupannya hanya pada subaccount tertentu (`subaccountId`), sehingga jika terjadi malfungsi algoritma, dampaknya terisolasi dari akun utama.
3. **CSPRNG Enforced**: Pembuatan order `requestId` dan penarikan membutuhkan generator acak kriptografi aman (`crypto.getRandomValues` / `crypto.randomUUID`). Lingkungan tanpa CSPRNG akan menghasilkan `ConfigurationError`.

---

## 4. Katalog & Spesifikasi Seluruh API (ConnectRPC, REST, WebSocket)

### 4.1 Network Endpoints & Protokol Transport

| Layanan | URL Base Testnet | Deskripsi |
| :--- | :--- | :--- |
| **ConnectRPC & REST API** | `https://api.testnet.polyester.com` | Endpoint utama RPC, manajemen akun, order, dan pasar |
| **Realtime WebSocket** | `wss://api-testnet.polyester.com` | Koneksi Centrifugo WebSocket untuk streaming publik & privat |
| **Block Explorer** | `https://polyesterscan.com` | Penelusuran transaksi on-chain, status Zipper, dan contract verifications |

#### Header Standar untuk Permintaan ConnectRPC:
```http
POST /package.v1.ServiceName/MethodName HTTP/1.1
Host: api.testnet.polyester.com
Content-Type: application/json
Connect-Protocol-Version: 1
X-API-KEY-ID: ak_live_...
X-API-TIMESTAMP: 1729840000000
X-API-SIGNATURE: 7a8f...
```

---

### 4.2 Layanan RPC & Endpoint Utama

Struktur rute RPC Polyester disusun modular di bawah package versi `v1`:

#### A. Autentikasi & Keamanan (`auth.v1`)
- `auth.v1.AuthService/CreateWalletChallenge`: Membuat pesan tantangan login wallet EIP-4361.
- `auth.v1.AuthService/AcceptTerms`: Merekam persetujuan syarat dan ketentuan platform.
- `POST /v1/auth/api-keys`: Mendaftarkan public key Ed25519 baru dan mengatur IP whitelist.
- `auth.v1.MFAService/UpdateMFAFactor`: Konfigurasi faktor MFA (TOTP / Authenticator).
- `auth.v1.MFAService/ClaimFreshStepUp`: Verifikasi MFA untuk memperoleh izin sesi sensitif (*step-up token*).
- `auth.v1.AddressBookService/CopyAddressBookEntry`: Menduplikasi atau menetapkan entri buku alamat ke subaccount.

#### B. Pasar & Data Referensi (`marketoverview.v1` / REST)
- `marketoverview.v1.MarketOverviewService/ListMarketOverview`: Mengambil ringkasan seluruh instrumen pasar aktif (harga terakhir, volume 24 jam, perubahan harga persentase, status order-book).
- `GET /v1/spot/fee-rates`: Mengambil struktur tarif fee transaksi spot per simbol berdasarkan level VIP akun pemanggil.
- `GET /v1/chain/analytics/zipped-asset-supply/group`: Metrik pasokan aset yang dijembatani oleh protokol Zipper.

#### C. Perdagangan & Order Execution (`orders` / `trade.v1`)
- `CreateOrder` / `PlaceOrder`: Memasang order baru (Limit, Market, Stop/Trigger).
- `CancelOrder`: Membatalkan order aktif menggunakan `order_id` atau `client_order_id`.
- `ModifyOrder`: Mengubah harga atau jumlah order aktif di buku order secara atomik.
- `BatchOrders`: Mengirim kumpulan order sekaligus dalam satu *round-trip* jaringan.
- `CancelAllOrders`: Membatalkan seluruh order terbuka pada simbol tertentu atau seluruh pasar.
- `ListOpenOrders`: Mengambil daftar seluruh order yang masih berstatus terbuka (*resting on book*).

#### D. Ledger, Saldo & Transfer Akun
- `ListBalances`: Membaca saldo akun yang memisahkan komponen `funding` dan `trading`.
- `transfer_trading_to_trading`: Memindahkan saldo antar trading bucket (misal: dari akun utama ke subaccount).
- `trading_withdraws.create_to_funding`: Mengembalikan saldo dari trading bucket ke funding bucket sebelum ditarik ke luar.

---

### 4.3 Struktur Buku Order, Tipe Order & Skema Fee

#### Tipe Order & Parameter Kunci:
- **`side`**: `"buy"` atau `"sell"`.
- **`order_type`**:
  - `"limit"`: Order dengan batas harga spesifik.
  - `"market"`: Order eksekusi instan pada harga pasar terbaik.
- **Time In Force (`tif`)**:
  - `"gtc"` (*Good 'Til Cancelled*): Order tetap ada di buku hingga dibatalkan.
  - `"ioc"` (*Immediate Or Cancel*): Bagian yang tidak segera terisi langsung dibatalkan.
  - `"fok"` (*Fill Or Kill*): Order harus terisi penuh seketika atau dibatalkan seutuhnya.
- **Flags**:
  - `post_only` (*boolean*): Memastikan order hanya bertindak sebagai *maker* penyedia likuiditas. Jika order akan langsung match sebagai *taker*, order otomatis dibatalkan tanpa terkena fee.
  - `client_order_id`: UUID unik dari pengembang untuk pelacakan idempotensi.
- **Skala Angka**: Seluruh kuantitas (`qty`) dan harga (`price`) wajib dikirim sebagai **string desimal** (misal: `"0.01"`, `"100.5"`), dilarang menggunakan tipe floating point numerik untuk menghindari masalah presisi.

#### Skema Fee Spot Berdasarkan VIP Tier:
Polyester menerapkan model Maker / Taker transparan:

| Level VIP | Maker Fee | Taker Fee |
| :---: | :---: | :---: |
| **VIP 0** | 0.100% | 0.150% |
| **VIP 1** | 0.080% | 0.135% |
| **VIP 2** | 0.065% | 0.120% |
| **VIP 3** | 0.050% | 0.105% |
| **VIP 4** | 0.040% | 0.090% |
| **VIP 5** | 0.030% | 0.080% |
| **VIP 6** | 0.020% | 0.070% |
| **VIP 7** | 0.015% | 0.060% |
| **VIP 8** | 0.0125% | 0.055% |
| **VIP 9** | 0.010% | 0.050% |
| **VIP 10** | 0.005% | 0.045% |

- **Maker Rebates**: Tersedia insentif fee negatif (rebate) untuk penyedia likuiditas berperingkat tinggi.
- **Fee Source Selector**: Pada order beli spot, pengguna dapat memilih apakah fee dipotong dari *Quote Asset* atau dari *Received Asset*.

---

### 4.4 Real-time Streaming WebSocket (Centrifugo)

- **Protokol**: Centrifugo realtime broker melalui transport `wss://api-testnet.polyester.com`.
- **Wire Format**: Mendukung *Protobuf binary* (berperforma tinggi) atau format *JSON*.
- **Mekanisme Handshake**: SDK menggunakan model *handshake-before-return*.
- **Channel Publik**:
  - `market:overview`: Pembaruan ticker dan ringkasan pasar global secara berkala.
  - `orderbook:{symbol}`: Snapshot dan delta tingkat kedalaman buku order (*L2 order book*).
  - `trades:{symbol}`: Aliran eksekusi transaksi publik.
- **Channel Privat** (Membutuhkan autentikasi token / subscription credentials):
  - `orders:{account_id}`: Notifikasi pembaruan status order (placed, partially filled, filled, cancelled).
  - `balances:{account_id}`: Perubahan saldo real-time (holds, funding, trading equity).
  - `subaccounts:{account_id}`: Pembaruan kebijakan dan posisi subaccount.
- **Kebijakan Fail-Closed Overflow**: Jika buffer klien terlambat memproses pesan dan terjadi penumpukan (*overflow*), koneksi ditutup secara aman (*fail-closed*) untuk mencegah inkonsistensi status finansial. Klien wajib mengimplementasikan rekonsiliasi status setelah *reconnect*.

---

## 5. Spesifikasi & Panduan Penggunaan SDK Resmi

Fabric Labs menyediakan library SDK resmi untuk mempermudah integrasi tanpa perlu membangun logika kanonikalisasi tanda tangan dari nol.

### 5.1 Python SDK (`polyester-sdk`)

Paket resmi di PyPI: [`polyester-sdk`](https://pypi.org/project/polyester-sdk/) (Membutuhkan Python 3.11+).

#### Instalasi:
```bash
# Instalasi dengan dukungan realtime WebSocket Centrifugo
pip install "polyester-sdk[realtime]"
```

#### Contoh Kode: Autentikasi, Ambil Pasar & Eksekusi Order
```python
import asyncio
from polyester import AsyncPolyester, POLYESTER_TESTNET_ENVIRONMENT, format_ledger_u128

async def run_bot():
    # Inisialisasi klien dengan kredensial Ed25519
    async with AsyncPolyester(
        api_key_id="ak_testnet_1234567890",
        api_private_key="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",  # 64-char hex
        default_account_id="RLxqJGUDg92",
        environment=POLYESTER_TESTNET_ENVIRONMENT
    ) as client:
        # 1. Mengambil ringkasan pasar publik
        overview = await client.market_overview.list(limit=5)
        for m in overview.markets:
            print(f"Pasar: {m.symbol} | Harga Terakhir: {m.last_price}")

        # 2. Cek saldo akun
        balances = await client.balances.list()
        for b in balances.items:
            print(f"Aset {b.asset}: Funding={format_ledger_u128(b.funding)}, Trading={format_ledger_u128(b.trading)}")

        # 3. Memasang limit order spot (Post-Only)
        order = await client.orders.create(
            symbol="BTC-USDT",
            side="buy",
            order_type="limit",
            tif="gtc",
            qty="0.05",
            price="65000.00",
            post_only=True,
            client_order_id="my-quant-bot-0001"
        )
        print(f"Order berhasil dipasang: {order.order_id}")

        # 4. Ambil daftar order terbuka
        open_orders = await client.orders.list_open()
        print(f"Total open orders: {len(open_orders.orders)}")

        # 5. Batalkan order jika diperlukan
        await client.orders.cancel(client_order_id="my-quant-bot-0001")
        print("Order berhasil dibatalkan.")

if __name__ == "__main__":
    asyncio.run(run_bot())
```

---

### 5.2 TypeScript SDK (`@polyester/sdk`)

Paket resmi di npm: [`@polyester/sdk`](https://www.npmjs.com/package/@polyester/sdk). Mendukung runtime Browser, Node.js, Bun, dan Edge (ESM).

#### Instalasi:
```bash
npm install @polyester/sdk
```

#### Contoh Kode: Browser Client dengan Smart Account Login
```typescript
import { PolyesterBrowserClient, POLYESTER_DEVNET_ENVIRONMENT } from "@polyester/sdk";
import type { AccountSigner } from "@polyester/sdk";
import { createPolyesterAccountSigner } from "@polyester/sdk/account-signer";

async function initBrowserApp(ownerWallet: any) {
  const environment = POLYESTER_DEVNET_ENVIRONMENT;
  
  // Menurunkan alamat smart account dari wallet pemilik
  const { accountAddress } = createPolyesterAccountSigner({
    environment,
    owner: ownerWallet
  });

  const accountSigner: AccountSigner = {
    environmentFingerprint: environment.fingerprint,
    accountAddress,
    ownerAddress: ownerWallet.address,
    // Login membutuhkan tanda tangan mentah EIP-191 65-byte
    signMessage: (message) => ownerWallet.signMessage({ message }),
  };

  const client = new PolyesterBrowserClient({ environment, accountSigner });

  // Melakukan login sesi
  await client.auth.login({ provider: "turnkey" });

  // Mengambil daftar order terbuka
  const { orders } = await client.orders.listOpen();
  console.log("Order terbuka:", orders);
  
  return client;
}
```

---

## 6. Checklist Rekomendasi Sebelum Menyusun Project Plan

Sebelum menyusun dokumen rencana proyek (*project plan*), pastikan pertimbangan-pertimbangan arsitektural berikut telah diperhitungkan:

| Kategori | Pertimbangan Kritis | Rekomendasi Teknis |
| :--- | :--- | :--- |
| **Kredensial & Secrets** | Penyimpanan Private Key Ed25519 | Private key 64-char hex **tidak boleh** masuk ke repo/git. Gunakan secure environment variables atau KMS (AWS KMS / HashiCorp Vault). |
| **Sinkronisasi Waktu** | Toleransi Skew 10 Detik | Pastikan server hosting menjalankan daemon NTP (seperti `chrony` atau `systemd-timesyncd`) agar selisih waktu tidak melebihi batas 10 detik. |
| **Presisi Finansial** | Floating Point vs Desimal | Gunakan tipe data `Decimal` / string untuk setiap variabel kuantitas dan harga. Jangan melakukan serialisasi nilai float IEEE 754 ke payload API. |
| **Siklus Hidup Aset** | Funding vs Trading Bucket | Rancang modul alokasi dana yang otomatis mengecek dan memindahkan saldo dari *Funding* ke *Trading* bucket sebelum bot mulai membuat order. |
| **Ketahanan Jaringan** | Reconnect & Order Reconciliation | Centrifugo WebSocket tidak menjamin *catch-up* pesan saat terputus. Pada event `onDisconnect` -> `onReconnect`, bot wajib menarik snapshot REST buku order dan order terbuka untuk rekonsiliasi posisi. |
| **Manajemen Resiko** | Subaccount & Whitelist | Manfaatkan subaccount untuk memisahkan bot uji coba dengan bot utama. Aktifkan *Withdrawal Whitelist* dengan GuardSigner + MFA untuk perlindungan maksimal. |
| **Protokol Wire** | Pilihan Bahasa Pemrograman | Jika menggunakan Python untuk automasi/bot, prioritaskan `polyester-sdk[realtime]`. Jika membangun antarmuka web, gunakan `@polyester/sdk` dengan Next.js / React. |

---

*Dokumentasi ini disiapkan secara otomatis sebagai landasan teknis resmi sebelum perancangan Project Architecture & Execution Plan.*
