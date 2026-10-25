@echo off
title Polyester VIP Volume Bot
echo ==========================================================
echo    POLYESTER VIP 1 VOLUME FARMING ^& GRID TRADING BOT     
echo ==========================================================

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv tidak ditemukan.
    pause
    exit /b 1
)

if not exist ".env" (
    echo [PERINGATAN] File .env tidak ditemukan. Menyalin dari .env.example...
    copy ".env.example" ".env"
    echo [INFO] File .env telah dibuat. Silakan edit .env dan masukkan kredensial API Anda.
)

.venv\Scripts\python.exe -m src.main
pause
