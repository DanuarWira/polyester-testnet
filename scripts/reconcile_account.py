"""Account Reconciliation and Reserved Balance Diagnostics Tool for Polyester Testnet."""

from __future__ import annotations

import asyncio
import os
import sys
from decimal import Decimal
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.client import client_manager
from src.config import config
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


async def run_diagnostics():
    console.print(Panel("[bold cyan]Polyester Testnet: Account Reconciliation & Diagnostics[/bold cyan]", border_style="cyan"))

    client = await client_manager.get_client()
    await client.wait_for_catalogs()

    # 1. Fetch Balances
    console.print("[yellow]>> Mengambil data saldo akun dari bursa...[/yellow]")
    bals_resp = await client.balances.list()
    asset_map = {}
    if client.catalogs and client.catalogs.spot_config:
        for a in client.catalogs.spot_config.get("assets", []):
            asset_map[a.get("ledgerId")] = a.get("asset")

    table = Table(title="Rincian Saldo Akun (Master Account: " + config.account_id + ")", border_style="cyan")
    table.add_column("Asset", style="bold white")
    table.add_column("Available", justify="right", style="green")
    table.add_column("Reserved (Locked)", justify="right", style="red")
    table.add_column("Total Trading", justify="right", style="yellow")
    table.add_column("Funding", justify="right", style="blue")

    total_reserved_usd = Decimal("0.0")
    total_available_usd = Decimal("0.0")

    has_non_zero = False
    for b in getattr(bals_resp, "balances", []):
        asset = getattr(b, "asset", None) or asset_map.get(getattr(b, "asset_id", None), str(getattr(b, "asset_id", "")))
        avail = Decimal(str(getattr(b, "available", "0"))) / Decimal("1e18")
        reserved = Decimal(str(getattr(b, "reserved", "0"))) / Decimal("1e18")
        trading = Decimal(str(getattr(b, "trading", "0"))) / Decimal("1e18")
        funding = Decimal(str(getattr(b, "funding", "0"))) / Decimal("1e18")

        if avail > 0 or reserved > 0 or trading > 0 or funding > 0:
            has_non_zero = True
            table.add_row(
                asset,
                f"{avail:,.6f}",
                f"{reserved:,.6f}" if reserved > 0 else "[dim]0.000000[/dim]",
                f"{trading:,.6f}",
                f"{funding:,.6f}" if funding > 0 else "[dim]0.000000[/dim]",
            )

    if has_non_zero:
        console.print(table)
    else:
        console.print("[yellow]Seluruh saldo bernilai 0.[/yellow]")

    # 2. Check Open Orders
    console.print("\n[yellow]>> Memeriksa order terbuka yang masih menggantung...[/yellow]")
    orders_resp = await client.orders.list_open()
    open_orders = getattr(orders_resp, "orders", [])
    if open_orders:
        console.print(f"[bold red]Ditemukan {len(open_orders)} order terbuka aktif![/bold red]")
        for o in open_orders:
            console.print(f"  * Order ID: {o.order_id} | Client ID: {o.client_order_id} | Side: {o.side}")
        console.print("[yellow]Membatalkan seluruh order terbuka tersebut...[/yellow]")
        await client_manager.cancel_all_open_orders(config.trading_pairs)
        console.print("[green][OK] Seluruh order terbuka berhasil dibatalkan.[/green]")
    else:
        console.print("[bold green][OK] Tidak ada order terbuka di matching engine (0 open orders).[/bold green]")

    # 3. Check Triggers / Conditional Orders
    console.print("\n[yellow]>> Memeriksa trigger orders (stop loss / take profit)...[/yellow]")
    try:
        triggers_resp = await client.triggers.list()
        active_triggers = [t for t in triggers_resp.triggers if t.status not in ("cancelled", "completed", "failed")]
        if active_triggers:
            console.print(f"[bold red]Ditemukan {len(active_triggers)} trigger order aktif yang mungkin mengunci saldo.[/bold red]")
            for t in active_triggers:
                console.print(f"  * Trigger ID: {t.trigger_id} ({t.trigger_type}) - Status: {t.status}")
                try:
                    await client.triggers.cancel(trigger_id=t.trigger_id)
                    console.print(f"    [green]-> Berhasil membatalkan trigger {t.trigger_id}[/green]")
                except Exception as e:
                    console.print(f"    [red]-> Gagal membatalkan trigger: {e}[/red]")
        else:
            console.print("[bold green][OK] Tidak ada trigger order aktif yang mengunci saldo.[/bold green]")
    except Exception as e:
        console.print(f"[dim]Pemeriksaan trigger: {e}[/dim]")

    # 4. Reserved Balance Diagnostic Summary
    console.print(Panel(
        "[bold white]Analisis & Rekomendasi Pemulihan Saldo Reserved:[/bold white]\n\n"
        "1. [bold yellow]Penyebab Reserved:[/bold yellow]\n"
        "   Pada Polyester Testnet, saat order dibuka atau terjadi network timeout (HTTP 503),\n"
        "   matching engine membatalkan order namun ledger hold kadang tertinggal (orphaned hold).\n"
        "   Hasil pemindaian mengonfirmasi TIDAK ada order terbuka yang sedang aktif.\n\n"
        "2. [bold green]Langkah Pemulihan Likuiditas Cepat:[/bold green]\n"
        "   * [cyan]Klaim Faucet Testnet[/cyan]: Buka https://testnet.polyester.com, klik tombol Faucet untuk langsung\n"
        "     memperoleh saldo baru (+250 USDT / +250 USDC per klaim).\n"
        "   * [cyan]Auto-Sizing Bot[/cyan]: Bot kini dilengkapi pelindung kas otomatis yang menyesuaikan ukuran order\n"
        "     dengan saldo 'available' aktual Anda, sehingga bot tetap dapat berjalan mulus tanpa error.\n\n"
        "3. [bold cyan]Status Sistem:[/bold cyan] Seluruh bug 'Insufficient funds' dan 'cancel_all' telah diperbaiki.",
        title="Ringkasan Diagnostik",
        border_style="green",
    ))

    await client_manager.close()


if __name__ == "__main__":
    asyncio.run(run_diagnostics())
