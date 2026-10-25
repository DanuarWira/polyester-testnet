"""Grid Execution Worker for Single Trading Pair."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from decimal import Decimal
from typing import Dict, List, Optional
from src.client import client_manager
from src.config import config
from src.market_data import market_data
from src.risk import risk_engine
from src.telemetry import telemetry

logger = logging.getLogger("polyester.grid_worker")


class PairGridWorker:
    """Manages the grid lifecycle for a single trading pair."""

    def __init__(self, pair: str) -> None:
        self.pair = pair.upper()
        self.base_asset = self.pair.split("-")[0]
        self.quote_asset = self.pair.split("-")[1]

        self.is_running = False
        self.active_orders: Dict[str, dict] = {}
        self.held_base_qty: Decimal = Decimal("0.0")
        self.last_mid_price: Decimal = Decimal("0.0")
        self.status_message: str = "Inisialisasi..."
        self.circuit_broken: bool = False
        self.last_error: str = ""
        self.tick_size: Decimal = Decimal("0.01")
        self.step_size: Decimal = Decimal("0.000001")

    def _format_price(self, price: Decimal) -> str:
        """Format price string based on symbol magnitude."""
        if price >= Decimal("1000"):
            return f"{price:.2f}"
        elif price >= Decimal("10"):
            return f"{price:.3f}"
        else:
            return f"{price:.4f}"

    def _format_qty(self, qty: Decimal) -> str:
        """Format base quantity string."""
        if self.base_asset in ("BTC", "ETH"):
            return f"{qty:.5f}"
        elif self.base_asset in ("BNB", "SOL", "AVAX"):
            return f"{qty:.4f}"
        else:
            return f"{qty:.2f}"

    async def update_balances(self) -> None:
        """Fetch current held base asset balance."""
        if config.dry_run:
            return

        client = await client_manager.get_client()
        try:
            asset_map = {}
            if client.catalogs and client.catalogs.spot_config:
                for a in client.catalogs.spot_config.get("assets", []):
                    asset_map[a.get("ledgerId")] = a.get("asset")

            balances = await client.balances.list()
            bal_list = getattr(balances, "balances", getattr(balances, "items", []))
            for b in bal_list:
                asset_name = getattr(b, "asset", None) or asset_map.get(getattr(b, "asset_id", None))
                if asset_name and asset_name.upper() == self.base_asset:
                    # Parse trading bucket (scaled u128 with 18 decimals)
                    if hasattr(b, "trading") and b.trading is not None:
                        # Convert 18-decimal integer ticks to Decimal
                        self.held_base_qty = Decimal(b.trading) / Decimal("1e18")
                    break
        except Exception as e:
            logger.debug(f"[{self.pair}] Gagal memperbarui saldo: {e}")

    async def fetch_open_orders(self) -> List[dict]:
        """Fetch active open orders resting on the book for this pair."""
        if config.dry_run:
            return list(self.active_orders.values())

        client = await client_manager.get_client()
        try:
            resp = await client.orders.list_open(symbol=self.pair)
            orders: List[dict] = []
            for o in resp.orders:
                orders.append({
                    "order_id": str(getattr(o, "order_id", "")),
                    "client_order_id": str(getattr(o, "client_order_id", "")),
                    "side": str(getattr(o, "side", "")).lower(),
                    "price": Decimal(str(getattr(o, "price", "0"))),
                    "qty": Decimal(str(getattr(o, "qty", "0"))),
                })
            return orders
        except Exception as e:
            logger.debug(f"[{self.pair}] Error list open orders: {e}")
            return []

    async def cancel_order(self, order_id: str = "", client_order_id: str = "") -> None:
        """Cancel an open order."""
        if config.dry_run:
            self.active_orders.pop(client_order_id, None)
            return

        client = await client_manager.get_client()
        try:
            from polyester.models.order_key import OrderId, ClientOrderId
            if order_id:
                await client.orders.cancel(key=OrderId(order_id), symbol=self.pair)
            elif client_order_id:
                await client.orders.cancel(key=ClientOrderId(client_order_id), symbol=self.pair)
        except Exception as e:
            logger.debug(f"[{self.pair}] Gagal membatalkan order {client_order_id or order_id}: {e}")

    async def place_order(
        self,
        side: str,
        price: Decimal,
        qty: Decimal,
        level: int,
    ) -> Optional[dict]:
        """Place a limit Post-Only order aligned with pair tick and step size."""
        from decimal import ROUND_DOWN, ROUND_UP
        from polyester import Price

        rounding_mode = ROUND_DOWN if side == "buy" else ROUND_UP
        aligned_price = (price / self.tick_size).quantize(Decimal("1"), rounding=rounding_mode) * self.tick_size
        ticks = int(aligned_price * Decimal("1e9"))
        price_obj = Price.from_ticks(ticks, symbol=self.pair)

        aligned_qty = (qty / self.step_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * self.step_size
        qty_str = f"{aligned_qty:.8f}".rstrip("0").rstrip(".")

        if aligned_qty <= 0 or aligned_price <= 0:
            return None

        client_order_id = f"pg-{self.pair.lower()}-{side[0]}-{level}-{uuid.uuid4().hex[:6]}"

        if config.dry_run:
            # Simulate placing order
            order_info = {
                "order_id": f"sim-{uuid.uuid4().hex[:8]}",
                "client_order_id": client_order_id,
                "side": side,
                "price": aligned_price,
                "qty": aligned_qty,
                "time": time.time(),
            }
            self.active_orders[client_order_id] = order_info

            # Simulate occasional trade execution in dry run
            if len(self.active_orders) > config.grid_levels * 2:
                oldest_key = next(iter(self.active_orders))
                filled = self.active_orders.pop(oldest_key)
                await telemetry.record_fill(
                    pair=self.pair,
                    side=filled["side"],
                    price=filled["price"],
                    qty=filled["qty"],
                    order_id=filled["order_id"],
                    client_order_id=filled["client_order_id"],
                    realized_pnl=Decimal("0.05") * filled["price"] * filled["qty"],
                )
            return order_info

        client = await client_manager.get_client()
        try:
            res = await client.orders.create(
                symbol=self.pair,
                side=side,
                order_type="limit",
                tif="gtc",
                qty=qty_str,
                price=price_obj,
                post_only=True,
                client_order_id=client_order_id,
            )
            order_info = {
                "order_id": getattr(res, "order_id", ""),
                "client_order_id": client_order_id,
                "side": side,
                "price": aligned_price,
                "qty": aligned_qty,
                "time": time.time(),
            }
            self.active_orders[client_order_id] = order_info
            self.last_error = ""
            return order_info
        except Exception as e:
            err_str = str(e)
            if "does not allow spot trading" in err_str.lower() or "policy" in err_str.lower():
                self.last_error = "Izin 'Spot Trading' belum diaktifkan pada API Key di dashboard!"
            else:
                self.last_error = err_str[:45]
            logger.warning(f"[{self.pair}] Gagal memasang order {side.upper()} {qty_str}@{aligned_price}: {e}")
            return None

    async def reconcile_grid(self) -> None:
        """Core cycle: evaluate orderbook, calculate risk/skew, and align grid orders."""
        # 1. Fetch orderbook
        ob = await market_data.get_orderbook(self.pair)
        if ob.mid_price <= 0 or ob.best_bid <= 0 or ob.best_ask <= 0:
            self.status_message = "Menunggu orderbook pasar valid..."
            return

        self.last_mid_price = ob.mid_price

        # Update tick and step size from catalogs if available
        client = await client_manager.get_client()
        if client.catalogs and client.catalogs.spot_config:
            for p in client.catalogs.spot_config.get("pairs", []):
                if p.get("symbol") == self.pair:
                    if p.get("tickSize"):
                        self.tick_size = Decimal(str(p["tickSize"]))
                    if p.get("stepSize"):
                        self.step_size = Decimal(str(p["stepSize"]))
                    break

        # 2. Update held balances
        await self.update_balances()

        # 3. Calculate dynamic risk & skewing
        grid_params = risk_engine.calculate_grid_params(
            pair=self.pair,
            best_bid=ob.best_bid,
            best_ask=ob.best_ask,
            mid_price=ob.mid_price,
            held_base_qty=self.held_base_qty,
        )

        self.circuit_broken = grid_params.circuit_broken

        # 4. Handle Circuit Breaker
        if grid_params.circuit_broken:
            self.status_message = f"CIRCUIT BREAKER: {grid_params.circuit_reason}"
            # Cancel open orders for safety
            open_orders = await self.fetch_open_orders()
            for o in open_orders:
                await self.cancel_order(o["order_id"], o["client_order_id"])
            self.active_orders.clear()
            return

        # 5. Fetch current open orders on the book
        current_open = await self.fetch_open_orders()
        buy_orders = [o for o in current_open if o["side"] == "buy"]
        sell_orders = [o for o in current_open if o["side"] == "sell"]

        # 6. Generate desired grid levels
        desired_buys: List[tuple[Decimal, Decimal, int]] = []
        desired_sells: List[tuple[Decimal, Decimal, int]] = []

        for lvl in range(1, config.grid_levels + 1):
            level_dec = Decimal(str(lvl))

            # Buy level below best bid
            if grid_params.allow_buy:
                buy_px = ob.best_bid * (Decimal("1.0") - grid_params.buy_spread_pct * level_dec)
                buy_qty = grid_params.buy_order_size_usd / buy_px if buy_px > 0 else Decimal("0.0")
                desired_buys.append((buy_px, buy_qty, lvl))

            # Sell level above best ask
            if grid_params.allow_sell:
                sell_px = ob.best_ask * (Decimal("1.0") + grid_params.sell_spread_pct * level_dec)
                sell_qty = grid_params.sell_order_size_usd / sell_px if sell_px > 0 else Decimal("0.0")
                desired_sells.append((sell_px, sell_qty, lvl))

        # 7. Check if existing orders need pruning (too far from current mid)
        for o in current_open:
            price_dist = abs(o["price"] - ob.mid_price) / ob.mid_price
            # If order drifted more than 3% away from mid, cancel it
            if price_dist > Decimal("0.03"):
                await self.cancel_order(o["order_id"], o["client_order_id"])

        # 8. Place missing buy levels
        if grid_params.allow_buy and len(buy_orders) < config.grid_levels:
            for px, qty, lvl in desired_buys:
                # Check if there is already an order near this level (within 0.15%)
                has_near = any(abs(o["price"] - px) / px < Decimal("0.0015") for o in buy_orders)
                if not has_near:
                    await self.place_order(side="buy", price=px, qty=qty, level=lvl)
                    break  # Place one per cycle to maintain pacing

        # 9. Place missing sell levels
        if grid_params.allow_sell and len(sell_orders) < config.grid_levels:
            for px, qty, lvl in desired_sells:
                has_near = any(abs(o["price"] - px) / px < Decimal("0.0015") for o in sell_orders)
                if not has_near:
                    await self.place_order(side="sell", price=px, qty=qty, level=lvl)
                    break

        buys_count = len([o for o in self.active_orders.values() if o["side"] == "buy"])
        sells_count = len([o for o in self.active_orders.values() if o["side"] == "sell"])
        if buys_count == 0 and sells_count == 0 and self.last_error:
            self.status_message = f"Gagal Order: {self.last_error}"
        else:
            self.status_message = f"Grid Aktif ({buys_count}B / {sells_count}S) | Mid: ${self.last_mid_price:,.2f}"

    async def run(self) -> None:
        """Main execution loop for this pair's worker."""
        self.is_running = True
        logger.info(f"[{self.pair}] Worker grid dimulai.")

        while self.is_running:
            try:
                await self.reconcile_grid()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{self.pair}] Error pada siklus grid: {e}")
                self.status_message = f"Error: {e}"

            await asyncio.sleep(config.update_interval_seconds)

        # Cleanup on stop
        logger.info(f"[{self.pair}] Menghentikan worker...")
        open_orders = await self.fetch_open_orders()
        for o in open_orders:
            await self.cancel_order(o["order_id"], o["client_order_id"])
        self.active_orders.clear()
        self.is_running = False

    def stop(self) -> None:
        """Signal worker to stop gracefully."""
        self.is_running = False
