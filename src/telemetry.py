"""Telemetry, Trade Recording, and VIP Volume Tracking Module."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Dict, List, Optional
import aiosqlite
from src.config import config


class TelemetryEngine:
    """Manages persistent trade recording and VIP volume progression."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or str(config.db_path)
        self._initialized = False

    async def initialize(self) -> None:
        """Create tables and indexes if they don't already exist."""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    pair TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    qty REAL NOT NULL,
                    volume_usd REAL NOT NULL,
                    maker_fee_paid REAL NOT NULL,
                    taker_fee_saved REAL NOT NULL,
                    realized_pnl REAL NOT NULL DEFAULT 0.0,
                    order_id TEXT,
                    client_order_id TEXT
                );
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades (timestamp);
            """)
            await db.commit()

        self._initialized = True

    async def record_fill(
        self,
        pair: str,
        side: str,
        price: Decimal,
        qty: Decimal,
        order_id: str = "",
        client_order_id: str = "",
        realized_pnl: Decimal = Decimal("0.0"),
    ) -> None:
        """Record an executed order fill to SQLite."""
        await self.initialize()

        volume_usd = price * qty
        # At VIP 0: Maker fee is 0.10% (0.0010), Taker is 0.15% (0.0015)
        # Using Post-Only saves the taker spread (0.05% of notional)
        maker_fee_rate = Decimal("0.0010")
        taker_fee_rate = Decimal("0.0015")

        maker_fee_paid = volume_usd * maker_fee_rate
        taker_fee_saved = volume_usd * (taker_fee_rate - maker_fee_rate)

        now = time.time()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO trades (
                    timestamp, pair, side, price, qty, volume_usd,
                    maker_fee_paid, taker_fee_saved, realized_pnl, order_id, client_order_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    pair,
                    side.upper(),
                    float(price),
                    float(qty),
                    float(volume_usd),
                    float(maker_fee_paid),
                    float(taker_fee_saved),
                    float(realized_pnl),
                    order_id,
                    client_order_id,
                ),
            )
            await db.commit()

    async def get_metrics(self) -> Dict[str, Any]:
        """Aggregate trading metrics for the dashboard and VIP progress."""
        await self.initialize()

        now = time.time()
        time_24h_ago = now - (24 * 3600)
        time_30d_ago = now - (30 * 24 * 3600)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 24-hour volume
            async with db.execute(
                "SELECT COALESCE(SUM(volume_usd), 0.0) as vol FROM trades WHERE timestamp >= ?",
                (time_24h_ago,),
            ) as cursor:
                row = await cursor.fetchone()
                volume_24h = float(row["vol"]) if row else 0.0

            # 30-day cumulative volume
            async with db.execute(
                "SELECT COALESCE(SUM(volume_usd), 0.0) as vol FROM trades WHERE timestamp >= ?",
                (time_30d_ago,),
            ) as cursor:
                row = await cursor.fetchone()
                volume_30d = float(row["vol"]) if row else 0.0

            # Total stats across all time
            async with db.execute(
                """
                SELECT 
                    COUNT(*) as total_trades,
                    COALESCE(SUM(volume_usd), 0.0) as total_volume,
                    COALESCE(SUM(maker_fee_paid), 0.0) as total_fees,
                    COALESCE(SUM(taker_fee_saved), 0.0) as total_saved,
                    COALESCE(SUM(realized_pnl), 0.0) as total_pnl
                FROM trades
                """
            ) as cursor:
                row = await cursor.fetchone()
                total_trades = int(row["total_trades"]) if row else 0
                total_volume = float(row["total_volume"]) if row else 0.0
                total_fees = float(row["total_fees"]) if row else 0.0
                total_saved = float(row["total_saved"]) if row else 0.0
                total_pnl = float(row["total_pnl"]) if row else 0.0

            # Last 5 trades for activity log
            recent_trades: List[Dict[str, Any]] = []
            async with db.execute(
                """
                SELECT timestamp, pair, side, price, qty, volume_usd, realized_pnl
                FROM trades ORDER BY id DESC LIMIT 5
                """
            ) as cursor:
                rows = await cursor.fetchall()
                for r in rows:
                    recent_trades.append({
                        "time": time.strftime("%H:%M:%S", time.localtime(r["timestamp"])),
                        "pair": r["pair"],
                        "side": r["side"],
                        "price": r["price"],
                        "qty": r["qty"],
                        "volume": r["volume_usd"],
                        "pnl": r["realized_pnl"],
                    })

        target_vol = float(config.target_30d_volume_usd)
        progress_pct = (volume_30d / target_vol * 100.0) if target_vol > 0 else 0.0

        return {
            "volume_24h": volume_24h,
            "volume_30d": volume_30d,
            "target_30d_volume": target_vol,
            "vip_progress_pct": min(progress_pct, 100.0),
            "total_trades": total_trades,
            "total_volume": total_volume,
            "total_fees_paid": total_fees,
            "total_taker_saved": total_saved,
            "total_pnl": total_pnl,
            "recent_trades": recent_trades,
        }


telemetry = TelemetryEngine()
