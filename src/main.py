"""Main Application Entry Point and Orchestrator."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Dict, List

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        if sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr.encoding.lower() != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.live import Live
from src.client import client_manager
from src.config import config
from src.dashboard import BotDashboard
from src.grid_worker import PairGridWorker
from src.telemetry import telemetry

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.data_dir / "bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("polyester.main")
console = Console(force_terminal=True, legacy_windows=False)


class PolyesterBotOrchestrator:
    """Manages multi-pair grid workers, dashboard updates, and graceful termination."""

    def __init__(self) -> None:
        self.workers: Dict[str, PairGridWorker] = {}
        self.worker_tasks: List[asyncio.Task] = []
        self.is_running = False
        self.dashboard = BotDashboard(self.workers)

    async def preflight_checks(self) -> bool:
        """Validate settings and test connection to Polyester Testnet."""
        console.print("[bold cyan]Memulai Pre-flight Healthcheck Polyester Testnet...[/bold cyan]")

        # Check configuration
        validation_errors = config.validate()
        if validation_errors and not config.dry_run:
            console.print("[bold red][X] Konfigurasi belum lengkap:[/bold red]")
            for err in validation_errors:
                console.print(f"  * [yellow]{err}[/yellow]")
            console.print("\n[cyan]Tip: Salin .env.example menjadi .env lalu isi kredensial API Anda, atau jalankan dalam mode simulasi dengan DRY_RUN=true di .env.[/cyan]\n")
            return False

        # Check network connectivity
        conn_check = await client_manager.check_connection()
        if not conn_check["success"] and not config.dry_run:
            console.print("[bold red][X] Koneksi atau autentikasi ke Polyester Testnet gagal:[/bold red]")
            for err in conn_check["errors"]:
                console.print(f"  * [yellow]{err}[/yellow]")
            return False

        console.print(f"[bold green][OK] Terhubung ke Polyester Testnet[/bold green] (Latency: {conn_check.get('clock_skew_ms', 0)} ms)")

        if conn_check.get("balances"):
            console.print("[dim]Saldo Akun:[/dim]")
            for asset, b in conn_check["balances"].items():
                console.print(f"  * [white]{asset}[/white]: Trading=[green]{b['trading']}[/green], Funding=[yellow]{b['funding']}[/yellow]")

        return True

    async def run(self) -> None:
        """Start multi-pair workers and interactive terminal dashboard."""
        # 1. Preflight
        passed = await self.preflight_checks()
        if not passed:
            return

        # 2. Initialize Telemetry Database and sync trade history from exchange
        await telemetry.initialize()
        client = await client_manager.get_client()
        initial_synced = await telemetry.sync_from_exchange(client)
        if initial_synced > 0:
            console.print(f"[bold green][OK] Berhasil menyinkronkan {initial_synced} riwayat transaksi dari bursa Polyester[/bold green]")

        # 3. Spawn workers per trading pair
        for pair in config.trading_pairs:
            worker = PairGridWorker(pair)
            self.workers[pair] = worker
            task = asyncio.create_task(worker.run(), name=f"worker-{pair}")
            self.worker_tasks.append(task)

        self.is_running = True
        logger.info(f"Bot aktif dengan {len(self.workers)} pasangan trading: {list(self.workers.keys())}")

        # 4. Live Dashboard Loop
        sync_counter = 0
        with Live(
            self.dashboard.generate_layout(await telemetry.get_metrics()),
            refresh_per_second=2,
            screen=True,
        ) as live:
            while self.is_running:
                try:
                    sync_counter += 1
                    # Periodically sync newly filled trades from exchange every 4 seconds
                    if sync_counter % 4 == 0:
                        await telemetry.sync_from_exchange(client)
                    metrics = await telemetry.get_metrics()
                    live.update(self.dashboard.generate_layout(metrics))
                    await asyncio.sleep(1.0)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error pada loop dashboard: {e}")
                    await asyncio.sleep(1.0)

        # 5. Shutdown cleanup
        await self.shutdown()

    async def shutdown(self) -> None:
        """Cancel active orders and stop worker tasks safely."""
        console.print("\n[bold yellow]Sedang mematikan bot secara aman (Graceful Shutdown)...[/bold yellow]")
        self.is_running = False

        # 1. Stop workers
        for worker in self.workers.values():
            worker.stop()

        # Allow workers brief time to finish order cancellations
        await asyncio.sleep(0.5)

        # 2. Cancel any remaining open orders on testnet
        await client_manager.cancel_all_open_orders(list(self.workers.keys()))

        # 3. Cancel and await worker background tasks
        for task in self.worker_tasks:
            task.cancel()
        await asyncio.gather(*self.worker_tasks, return_exceptions=True)

        # 4. Close client connections
        await client_manager.close()
        console.print("[bold green][OK] Seluruh open order dibatalkan & koneksi ditutup dengan aman. Sampai jumpa![/bold green]\n")


def setup_signal_handlers(orchestrator: PolyesterBotOrchestrator) -> None:
    """Handle Ctrl+C (SIGINT) on Windows and POSIX systems."""
    def handle_exit(*args):
        orchestrator.is_running = False

    try:
        signal.signal(signal.SIGINT, handle_exit)
        signal.signal(signal.SIGTERM, handle_exit)
    except Exception:
        pass


def main() -> None:
    """CLI entry point."""
    orchestrator = PolyesterBotOrchestrator()
    setup_signal_handlers(orchestrator)
    try:
        asyncio.run(orchestrator.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
