# Launcher PowerShell untuk Polyester VIP Volume Bot
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   POLYESTER VIP 1 VOLUME FARMING & GRID TRADING BOT     " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[ERROR] Virtual environment .venv tidak ditemukan. Silakan jalankan instalasi terlebih dahulu." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path ".env")) {
    Write-Host "[PERINGATAN] File .env tidak ditemukan. Menyalin template dari .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "[INFO] File .env telah dibuat. Silakan edit .env dan masukkan kredensial API Anda." -ForegroundColor Green
}

& ".venv\Scripts\python.exe" -m src.main
