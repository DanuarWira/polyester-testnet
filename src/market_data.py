"""Market Data and Order Book Service Module."""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Dict, List, NamedTuple, Optional
from src.client import client_manager
from src.config import config

logger = logging.getLogger("polyester.market_data")


class OrderBookSnapshot(NamedTuple):
    """Normalized snapshot of orderbook state."""

    pair: str
    best_bid: Decimal
    best_ask: Decimal
    mid_price: Decimal
    spread_pct: Decimal
    bids: List[tuple[Decimal, Decimal]]
    asks: List[tuple[Decimal, Decimal]]
    timestamp: float


class MarketDataManager:
    """Provides orderbook snapshots and mid-price tracking."""

    def __init__(self) -> None:
        self._cache: Dict[str, OrderBookSnapshot] = {}

    def _parse_price(self, val: object) -> Decimal:
        """Safely parse price from Price object, string, or float with 1e9 protocol normalization."""
        if hasattr(val, "ticks"):
            # Polyester wire price ticks are scaled by 1e9 (nano-ticks)
            return Decimal(val.ticks) / Decimal("1e9")
        if hasattr(val, "as_decimal"):
            raw = val.as_decimal()
            # If still scaled by 1000 due to SDK 1e6 scale vs 1e9 wire scale
            if raw > Decimal("500000"):
                return raw / Decimal("1000")
            return raw
        if val is None:
            return Decimal("0.0")
        try:
            raw = Decimal(str(val))
            if raw > Decimal("500000"):
                return raw / Decimal("1000")
            return raw
        except Exception:
            return Decimal("0.0")

    def _parse_qty(self, val: object) -> Decimal:
        """Safely parse quantity from Quantity object, string, or float."""
        if hasattr(val, "as_decimal"):
            try:
                return val.as_decimal()
            except Exception:
                pass
        if hasattr(val, "format"):
            try:
                return Decimal(val.format())
            except Exception:
                pass
        if val is None:
            return Decimal("0.0")
        return Decimal(str(val))

    async def get_orderbook(self, pair: str) -> OrderBookSnapshot:
        """Fetch and normalize order book for a given symbol."""
        now = time.time()

        if config.dry_run:
            # Simulated realistic market prices for dry-run testing
            sim_prices = {
                "BTC-USDT": (Decimal("67450.00"), Decimal("67460.00")),
                "ETH-USDT": (Decimal("2580.00"), Decimal("2581.50")),
                "BNB-USDT": (Decimal("590.00"), Decimal("590.80")),
            }
            best_bid, best_ask = sim_prices.get(pair, (Decimal("100.00"), Decimal("100.20")))
            mid_price = (best_bid + best_ask) / Decimal("2.0")
            spread = (best_ask - best_bid) / mid_price
            snapshot = OrderBookSnapshot(
                pair=pair,
                best_bid=best_bid,
                best_ask=best_ask,
                mid_price=mid_price,
                spread_pct=spread,
                bids=[(best_bid, Decimal("0.5"))],
                asks=[(best_ask, Decimal("0.5"))],
                timestamp=now,
            )
            self._cache[pair] = snapshot
            return snapshot

        client = await client_manager.get_client()

        try:
            ob = await client.orderbook.get(symbol=pair, depth=20)
            parsed_bids: List[tuple[Decimal, Decimal]] = []
            parsed_asks: List[tuple[Decimal, Decimal]] = []

            for b in ob.bids:
                p = self._parse_price(b.price)
                q = self._parse_qty(b.qty)
                if p > 0:
                    parsed_bids.append((p, q))

            for a in ob.asks:
                p = self._parse_price(a.price)
                q = self._parse_qty(a.qty)
                if p > 0:
                    parsed_asks.append((p, q))

            best_bid = parsed_bids[0][0] if parsed_bids else Decimal("0.0")
            best_ask = parsed_asks[0][0] if parsed_asks else Decimal("0.0")

            # Fallback to market overview if book is empty
            if best_bid <= 0 or best_ask <= 0:
                overview = await client.market_overview.list(limit=50)
                for m in overview.markets:
                    if m.symbol == pair:
                        last_p = self._parse_price(m.last_price)
                        if last_p > 0:
                            best_bid = last_p * Decimal("0.9995")
                            best_ask = last_p * Decimal("1.0005")
                            break

            mid = (best_bid + best_ask) / Decimal("2.0") if (best_bid > 0 and best_ask > 0) else Decimal("1.0")
            spread = ((best_ask - best_bid) / mid) if mid > 0 else Decimal("0.0")

            snapshot = OrderBookSnapshot(
                pair=pair,
                best_bid=best_bid,
                best_ask=best_ask,
                mid_price=mid,
                spread_pct=spread,
                bids=parsed_bids,
                asks=parsed_asks,
                timestamp=now,
            )
            self._cache[pair] = snapshot
            return snapshot

        except Exception as e:
            logger.warning(f"Error fetching orderbook for {pair}: {e}")
            if pair in self._cache:
                return self._cache[pair]
            # Minimal fallback
            fallback = OrderBookSnapshot(
                pair=pair,
                best_bid=Decimal("0.0"),
                best_ask=Decimal("0.0"),
                mid_price=Decimal("0.0"),
                spread_pct=Decimal("0.0"),
                bids=[],
                asks=[],
                timestamp=now,
            )
            return fallback


market_data = MarketDataManager()
