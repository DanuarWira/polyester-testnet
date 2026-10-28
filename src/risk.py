"""Risk Management, Dynamic Inventory Skewing, and Circuit Breaker Module."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Dict, NamedTuple, Tuple
from src.config import config


class GridParameters(NamedTuple):
    """Calculated dynamic parameters for placing a pair's grid orders."""

    allow_buy: bool
    allow_sell: bool
    buy_spread_pct: Decimal
    sell_spread_pct: Decimal
    buy_order_size_usd: Decimal
    sell_order_size_usd: Decimal
    circuit_broken: bool
    circuit_reason: str


class RiskEngine:
    """Calculates inventory skewing and monitors volatility safety thresholds."""

    def __init__(self) -> None:
        self.max_inventory_usd = config.max_inventory_usd_per_pair
        self.circuit_breaker_spread = config.circuit_breaker_spread_pct
        self.base_spread = config.grid_spread_pct
        self.base_order_size = config.order_size_usdt

        # Track recent prices per pair for sudden dump/pump detection
        self._price_history: Dict[str, list[Tuple[float, Decimal]]] = {}

    def record_price(self, pair: str, mid_price: Decimal) -> None:
        """Record mid-price timestamp for short-term volatility tracking."""
        now = time.time()
        if pair not in self._price_history:
            self._price_history[pair] = []

        history = self._price_history[pair]
        history.append((now, mid_price))

        # Keep only the last 5 minutes of price points
        cutoff = now - 300
        self._price_history[pair] = [(t, p) for t, p in history if t >= cutoff]

    def check_circuit_breaker(
        self,
        pair: str,
        best_bid: Decimal,
        best_ask: Decimal,
        mid_price: Decimal,
    ) -> Tuple[bool, str]:
        """Verify whether market conditions violate safety limits."""
        if best_bid <= 0 or best_ask <= 0 or best_ask <= best_bid:
            return True, "Order book kosong, tidak valid, atau crossed"

        # 1. Market spread check
        market_spread = (best_ask - best_bid) / mid_price
        if market_spread > self.circuit_breaker_spread:
            return (
                True,
                f"Market spread melebar tajam ({market_spread:.2%} > limit {self.circuit_breaker_spread:.2%})",
            )

        # 2. Sudden price spike/crash check (5% movement in <= 60 seconds)
        now = time.time()
        history = self._price_history.get(pair, [])
        for t, old_price in history:
            if now - t <= 60 and old_price > 0:
                change = abs((mid_price - old_price) / old_price)
                if change >= Decimal("0.05"):
                    return True, f"Volatilitas ekstrem: Perubahan harga {change:.2%} dalam <60 detik"

        return False, ""

    def calculate_grid_params(
        self,
        pair: str,
        best_bid: Decimal,
        best_ask: Decimal,
        mid_price: Decimal,
        held_base_qty: Decimal,
    ) -> GridParameters:
        """Calculate dynamically skewed buy/sell spreads and sizes based on inventory."""
        self.record_price(pair, mid_price)

        # Check circuit breaker
        circuit_broken, circuit_reason = self.check_circuit_breaker(
            pair, best_bid, best_ask, mid_price
        )
        if circuit_broken:
            return GridParameters(
                allow_buy=False,
                allow_sell=False,
                buy_spread_pct=self.base_spread,
                sell_spread_pct=self.base_spread,
                buy_order_size_usd=self.base_order_size,
                sell_order_size_usd=self.base_order_size,
                circuit_broken=True,
                circuit_reason=circuit_reason,
            )

        # Current inventory value in USD
        base_value_usd = held_base_qty * mid_price
        target_inventory_usd = self.max_inventory_usd / Decimal("2.0")

        # Inventory skew ratio from -1.0 to 1.0
        # Positive: holding too much base coin -> skew higher to sell, widen buys
        # Negative: holding too little base coin -> skew lower to buy, widen sells
        if target_inventory_usd > 0:
            skew = (base_value_usd - target_inventory_usd) / target_inventory_usd
            skew = max(Decimal("-0.8"), min(Decimal("0.8"), skew))
        else:
            skew = Decimal("0.0")

        # Minimum maker spread to ensure order sits safely behind best bid/ask
        min_spread = Decimal("0.0010")  # 0.10%

        # Dynamic spreads
        # When skew > 0: buy_spread increases, sell_spread decreases (closer to mid)
        buy_spread = max(min_spread, self.base_spread * (Decimal("1.0") + skew))
        sell_spread = max(min_spread, self.base_spread * (Decimal("1.0") - skew * Decimal("0.5")))

        # Dynamic order sizes
        buy_size = max(Decimal("10.0"), self.base_order_size * (Decimal("1.0") - skew * Decimal("0.5")))
        sell_size = max(Decimal("10.0"), self.base_order_size * (Decimal("1.0") + skew * Decimal("0.5")))

        # Hard inventory limits
        allow_buy = base_value_usd < self.max_inventory_usd
        allow_sell = base_value_usd >= Decimal("5.0")

        reason = "" if allow_buy else f"Batas inventaris tercapai ({base_value_usd:.2f} USD >= {self.max_inventory_usd:.2f} USD)"

        return GridParameters(
            allow_buy=allow_buy,
            allow_sell=allow_sell,
            buy_spread_pct=buy_spread,
            sell_spread_pct=sell_spread,
            buy_order_size_usd=buy_size,
            sell_order_size_usd=sell_size,
            circuit_broken=False,
            circuit_reason=reason,
        )

    def calculate_quick_churn_params(
        self,
        pair: str,
        best_bid: Decimal,
        best_ask: Decimal,
        mid_price: Decimal,
        held_base_qty: Decimal,
        available_quote_usd: Decimal = Decimal("999999"),
        min_notional_usd: Decimal = Decimal("5.0"),
    ) -> GridParameters:
        """Calculate tight-maker parameters with asymmetric offloading for quick turnover."""
        self.record_price(pair, mid_price)

        # Check circuit breaker
        circuit_broken, circuit_reason = self.check_circuit_breaker(
            pair, best_bid, best_ask, mid_price
        )
        if circuit_broken:
            return GridParameters(
                allow_buy=False,
                allow_sell=False,
                buy_spread_pct=Decimal("0.0"),
                sell_spread_pct=Decimal("0.0"),
                buy_order_size_usd=self.base_order_size,
                sell_order_size_usd=self.base_order_size,
                circuit_broken=True,
                circuit_reason=circuit_reason,
            )

        base_value_usd = held_base_qty * mid_price

        # Asymmetric Aggressive Offloading:
        # If we hold enough base coin (> 70% of standard order size), prioritize selling
        # and pause buying so capital recycles cleanly back to USDT.
        if base_value_usd >= self.base_order_size * Decimal("0.7"):
            allow_buy = False
            allow_sell = True
            reason = f"Offloading Inventaris (${base_value_usd:.2f}) -> USDT"
            sell_size = min(base_value_usd, self.base_order_size * Decimal("1.5"))
            buy_size = Decimal("0.0")
        elif base_value_usd >= min_notional_usd:
            # Hold some base coin (above minimum $5 notional): allow two-sided quoting
            allow_buy = True
            allow_sell = True
            reason = "Two-Sided Churning Aktif"
            sell_size = base_value_usd
            buy_size = self.base_order_size
        else:
            # Dust or no base coin: buy to initiate new round-trip, do NOT attempt dust sell
            allow_buy = True
            allow_sell = False
            reason = "Membuka Posisi Baru (Buy Best Bid)"
            buy_size = self.base_order_size
            sell_size = Decimal("0.0")

        # Hard ceiling safety
        if base_value_usd >= self.max_inventory_usd:
            allow_buy = False
            allow_sell = True
            reason = f"Batas Inventaris Maksimal Tercapai (${base_value_usd:.2f})"

        # Global Portfolio USDT Capital Guard
        if allow_buy and available_quote_usd < buy_size * Decimal("1.02"):
            if available_quote_usd >= Decimal("15.0"):
                # Dynamically scale buy size to available USDT balance
                buy_size = (available_quote_usd * Decimal("0.95")).quantize(Decimal("0.01"))
                reason += f" | Skala Modal Dinamis (${buy_size:.2f})"
            else:
                allow_buy = False
                reason = f"Menunggu Likuiditas USDT (${available_quote_usd:.2f} < ${min_notional_usd:.2f})"

        return GridParameters(
            allow_buy=allow_buy,
            allow_sell=allow_sell,
            buy_spread_pct=Decimal("0.0"),  # 0 spread = peg exactly at best bid
            sell_spread_pct=Decimal("0.0"), # 0 spread = peg exactly at best ask
            buy_order_size_usd=buy_size,
            sell_order_size_usd=sell_size,
            circuit_broken=False,
            circuit_reason=reason,
        )


risk_engine = RiskEngine()
