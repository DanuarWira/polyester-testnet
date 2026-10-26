"""Configuration and Settings Module for Polyester VIP Volume Bot."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class BotConfig:
    """Strongly typed application configuration."""

    def __init__(self) -> None:
        # Polyester Testnet Credentials
        self.api_key_id: str = os.getenv("POLYESTER_API_KEY_ID", "").strip()
        self.api_private_key: str = os.getenv("POLYESTER_API_PRIVATE_KEY", "").strip()
        self.account_id: str = os.getenv("POLYESTER_ACCOUNT_ID", "").strip()
        self.api_url: str = os.getenv("POLYESTER_API_URL", "https://api.testnet.polyester.com").strip()
        self.ws_url: str = os.getenv("POLYESTER_WS_URL", "wss://api.testnet.polyester.com").strip()

        # Strategy Mode: QUICK_CHURN (Aggressive Tight Maker) or GRID_PASSIVE (Passive Grid)
        self.strategy_mode: str = os.getenv("STRATEGY_MODE", "QUICK_CHURN").strip().upper()
        if self.strategy_mode not in ("QUICK_CHURN", "GRID_PASSIVE"):
            self.strategy_mode = "QUICK_CHURN"

        # Multi-pair settings
        raw_pairs = os.getenv("TRADING_PAIRS", "BTC-USDT,ETH-USDT,BNB-USDT")
        self.trading_pairs: List[str] = [p.strip().upper() for p in raw_pairs.split(",") if p.strip()]

        # Grid settings
        self.grid_levels: int = int(os.getenv("GRID_LEVELS", "3"))
        self.grid_spread_pct: Decimal = Decimal(str(os.getenv("GRID_SPREAD_PCT", "0.0025")))
        default_order_size = "100.0" if self.strategy_mode == "QUICK_CHURN" else "50.0"
        self.order_size_usdt: Decimal = Decimal(str(os.getenv("ORDER_SIZE_USDT", default_order_size)))

        # Risk and Inventory settings
        self.max_inventory_usd_per_pair: Decimal = Decimal(str(os.getenv("MAX_INVENTORY_USD_PER_PAIR", "300.0")))
        self.circuit_breaker_spread_pct: Decimal = Decimal(str(os.getenv("CIRCUIT_BREAKER_SPREAD_PCT", "0.015")))
        default_interval = "1.0" if self.strategy_mode == "QUICK_CHURN" else "3.0"
        self.update_interval_seconds: float = float(os.getenv("UPDATE_INTERVAL_SECONDS", default_interval))
        self.repeg_tolerance_ticks: int = int(os.getenv("REPEG_TOLERANCE_TICKS", "1"))

        # VIP Tracker settings
        self.target_30d_volume_usd: Decimal = Decimal(str(os.getenv("TARGET_30D_VOLUME_USD", "100000.0")))
        self.min_portfolio_usd: Decimal = Decimal(str(os.getenv("MIN_PORTFOLIO_USD", "1000.0")))

        # Runtime settings
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
        self.dry_run: bool = os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes")

        # Database directory
        self.data_dir: Path = BASE_DIR / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path: Path = self.data_dir / "trades.db"

    def validate(self) -> List[str]:
        """Validate critical configuration fields before running."""
        errors: List[str] = []
        if not self.api_key_id or "your_api_key_id" in self.api_key_id:
            errors.append("POLYESTER_API_KEY_ID belum diset dengan benar di .env")
        if not self.api_private_key or "your_64_character" in self.api_private_key:
            errors.append("POLYESTER_API_PRIVATE_KEY belum diset dengan benar di .env")
        elif len(self.api_private_key) not in (64, 128):
            errors.append("POLYESTER_API_PRIVATE_KEY harus berupa 64 hex characters")
        if not self.account_id or "your_account_id" in self.account_id:
            errors.append("POLYESTER_ACCOUNT_ID belum diset dengan benar di .env")
        if not self.trading_pairs:
            errors.append("TRADING_PAIRS tidak boleh kosong (minimal 1 pair, misal: BTC-USDT)")
        if self.grid_levels < 1 or self.grid_levels > 10:
            errors.append("GRID_LEVELS harus berada di rentang 1 s.d. 10")
        if self.grid_spread_pct <= 0:
            errors.append("GRID_SPREAD_PCT harus lebih besar dari 0")
        if self.order_size_usdt <= 0:
            errors.append("ORDER_SIZE_USDT harus lebih besar dari 0")
        return errors


config = BotConfig()
