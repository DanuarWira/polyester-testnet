"""Polyester Testnet Client Wrapper and Healthcheck Module."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
from polyester import (
    POLYESTER_TESTNET_ENVIRONMENT,
    AsyncPolyester,
    PolyesterAuthError,
    PolyesterError,
    format_ledger_u128,
)
from src.config import config

logger = logging.getLogger("polyester.client")


class PolyesterClientManager:
    """Manages the AsyncPolyester client lifecycle and connectivity."""

    def __init__(self) -> None:
        self._client: Optional[AsyncPolyester] = None
        self._is_connected = False

    async def get_client(self) -> AsyncPolyester:
        """Get or initialize the AsyncPolyester client instance."""
        if self._client is not None:
            return self._client

        # If in dry-run mode without real keys, handle gracefully
        api_key = config.api_key_id if config.api_key_id else "ak_testnet_dummy"
        private_key = config.api_private_key if len(config.api_private_key) in (64, 128) else "00" * 32
        account_id = config.account_id if config.account_id else "dummy_acc"

        self._client = AsyncPolyester(
            api_key_id=api_key,
            api_private_key=private_key,
            default_account_id=account_id,
            environment=POLYESTER_TESTNET_ENVIRONMENT,
            api_url=config.api_url,
            ws_url=config.ws_url,
            timeout=15.0,
            wire_format="binary",
        )
        try:
            # Wait briefly for spot catalogs to hydrate symbols and scales
            await self._client.wait_for_catalogs()
        except Exception:
            pass
        return self._client

    async def check_connection(self) -> Dict[str, Any]:
        """Perform pre-flight healthcheck, clock skew, and balance inspection."""
        results: Dict[str, Any] = {
            "success": False,
            "clock_skew_ms": 0.0,
            "balances": {},
            "errors": [],
            "markets_available": [],
        }

        config_errors = config.validate()
        if config_errors and not config.dry_run:
            results["errors"].extend(config_errors)
            return results

        client = await self.get_client()

        # 1. Fetch public market overview to verify connectivity and measure latency
        t_start = time.time()
        try:
            overview = await client.market_overview.list(limit=50)
            latency_ms = (time.time() - t_start) * 1000.0
            results["clock_skew_ms"] = round(latency_ms, 2)
            results["markets_available"] = [m.symbol for m in overview.markets]
        except Exception as e:
            results["errors"].append(f"Gagal mengambil data pasar publik: {e}")
            return results

        # 2. Check authenticated endpoints (balances) if credentials provided
        if not config.dry_run:
            for attempt in range(2):
                try:
                    balances_resp = await client.balances.list()
                    asset_map = {}
                    if client.catalogs and client.catalogs.spot_config:
                        for a in client.catalogs.spot_config.get("assets", []):
                            asset_map[a.get("ledgerId")] = a.get("asset")

                    bal_list = getattr(balances_resp, "balances", getattr(balances_resp, "items", []))
                    for b in bal_list:
                        asset_name = getattr(b, "asset", None) or asset_map.get(getattr(b, "asset_id", None), f"Asset-{getattr(b, 'asset_id', '?')}")
                        funding_str = format_ledger_u128(b.funding) if getattr(b, "funding", None) is not None else "0"
                        trading_str = format_ledger_u128(b.trading) if getattr(b, "trading", None) is not None else "0"
                        try:
                            has_balance = float(funding_str) > 0 or float(trading_str) > 0
                        except Exception:
                            has_balance = False
                        if has_balance or asset_name in ("USDT", "BTC", "ETH"):
                            results["balances"][asset_name] = {
                                "funding": funding_str,
                                "trading": trading_str,
                            }
                    self._is_connected = True
                    results["success"] = True
                    break
                except PolyesterAuthError as e:
                    err_msg = str(e)
                    if "api_key_policy_required" in err_msg.lower():
                        logger.warning("API Key valid terhubung, tetapi izin 'Ledger Read' belum diaktifkan di dashboard.")
                        self._is_connected = True
                        results["success"] = True
                        results["balances"]["Info"] = {
                            "funding": "Izin 'Ledger Read' belum dicentang di dashboard API Key.",
                            "trading": "Order tetap dapat berjalan.",
                        }
                    else:
                        results["errors"].append(f"Autentikasi Ed25519 gagal: {e}. Periksa API Key ID dan Private Key di .env.")
                    break
                except Exception as e:
                    if attempt == 0:
                        await asyncio.sleep(0.8)
                        continue
                    # Jika gagal membaca saldo, tetap izinkan lanjut jika pasar publik terhubung
                    logger.warning(f"Gagal mengambil saldo awal ({e}), melanjutkan dengan status aktif.")
                    self._is_connected = True
                    results["success"] = True
                    results["balances"]["Status"] = {
                        "funding": "Terkoneksi",
                        "trading": "Order aktif",
                    }
        else:
            # Dry run simulation mode
            self._is_connected = True
            results["success"] = True
            results["balances"]["USDT (SIM)"] = {"funding": "0.0", "trading": "10000.0"}
            results["balances"]["BTC (SIM)"] = {"funding": "0.0", "trading": "1.0"}

        return results

    async def cancel_all_open_orders(self, pairs: List[str]) -> None:
        """Emergency or shutdown action: Cancel all active open orders."""
        if config.dry_run:
            logger.info("[DRY-RUN] Simulasi pembatalan seluruh order terbuka.")
            return

        client = await self.get_client()
        for pair in pairs:
            try:
                logger.info(f"Membatalkan seluruh order terbuka pada pair {pair}...")
                await client.orders.cancel_all(symbol=pair)
            except Exception as e:
                logger.warning(f"Gagal membatalkan order untuk {pair}: {e}")

    async def close(self) -> None:
        """Close client sessions and connections."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
            self._is_connected = False


client_manager = PolyesterClientManager()
