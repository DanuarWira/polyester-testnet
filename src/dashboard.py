"""Interactive Terminal UI Dashboard using Rich."""

from __future__ import annotations

from typing import Dict, List
from rich.align import Align
from rich.layout import Layout
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text
from src.config import config
from src.grid_worker import PairGridWorker


class BotDashboard:
    """Renders real-time telemetry, VIP progress, and active pair grids."""

    def __init__(self, workers: Dict[str, PairGridWorker]) -> None:
        self.workers = workers

    def generate_layout(self, metrics: dict) -> Layout:
        """Construct the complete multi-panel dashboard layout."""
        layout = Layout()

        # Split into Header, Body, and Footer
        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="vip_progress", size=5),
            Layout(name="main_tables", ratio=1),
            Layout(name="footer", size=3),
        )

        # Split main_tables horizontally into Pairs Grid and Financial Stats
        layout["main_tables"].split_row(
            Layout(name="pairs_table", ratio=3),
            Layout(name="stats_side", ratio=2),
        )

        # Split stats_side vertically into Financials and Recent Trades
        layout["stats_side"].split_column(
            Layout(name="financials", size=7),
            Layout(name="recent_trades", ratio=1),
        )

        # 1. Header Panel
        mode_text = "[bold yellow]DRY-RUN (SIMULATION)[/bold yellow]" if config.dry_run else "[bold green]LIVE TESTNET[/bold green]"
        acc_id = config.account_id if config.account_id else "Not Set"
        header_text = Text.assemble(
            (">> POLYESTER VIP VOLUME FARMING BOT <<\n", "bold cyan"),
            ("Environment: ", "dim"), (mode_text), (" | Account: ", "dim"), (f"{acc_id}", "bold white"),
            (" | Pairs: ", "dim"), (f"{', '.join(config.trading_pairs)}", "yellow"),
        )
        layout["header"].update(Panel(Align.center(header_text), style="cyan", border_style="bright_blue"))

        # 2. VIP 1 Progress Bar Panel
        vol_30d = metrics.get("volume_30d", 0.0)
        target_vol = metrics.get("target_30d_volume", 100000.0)
        pct = metrics.get("vip_progress_pct", 0.0)
        vol_24h = metrics.get("volume_24h", 0.0)

        progress_bar = ProgressBar(total=100.0, completed=pct, width=45)
        vip_table = Table.grid(expand=True)
        vip_table.add_column(ratio=2)
        vip_table.add_column(ratio=3)
        vip_table.add_column(ratio=2)

        vip_table.add_row(
            Text(f"30d Vol: ${vol_30d:,.2f} / ${target_vol:,.2f}", style="bold white"),
            progress_bar,
            Text(f"Progress VIP 1: {pct:.2f}% | 24h: ${vol_24h:,.2f}", style="bold green" if pct >= 100 else "bold yellow"),
        )
        layout["vip_progress"].update(
            Panel(vip_table, title="[bold magenta][VIP 1] Target Tracker: $100K 30-Day Volume[/bold magenta]", border_style="magenta")
        )

        # 3. Active Pairs Grid Table
        pairs_table = Table(expand=True, box=None)
        pairs_table.add_column("Pair", style="bold cyan", width=12)
        pairs_table.add_column("Mid Price", justify="right", style="white")
        pairs_table.add_column("Inventory USD", justify="right", style="yellow")
        pairs_table.add_column("Orders (B/S)", justify="center", style="bold")
        pairs_table.add_column("Status / Safety", style="dim")

        for pair, worker in self.workers.items():
            buys = len([o for o in worker.active_orders.values() if o["side"] == "buy"])
            sells = len([o for o in worker.active_orders.values() if o["side"] == "sell"])
            orders_str = f"[green]{buys}B[/green] / [red]{sells}S[/red]"
            inv_usd = worker.held_base_qty * worker.last_mid_price

            status_style = "bold red" if worker.circuit_broken else "green"
            pairs_table.add_row(
                pair,
                f"${worker.last_mid_price:,.2f}" if worker.last_mid_price > 0 else "Loading...",
                f"${inv_usd:,.2f}",
                orders_str,
                Text(worker.status_message, style=status_style),
            )

        layout["pairs_table"].update(
            Panel(pairs_table, title="[bold cyan][Grid] Multi-Pair Grid State[/bold cyan]", border_style="cyan")
        )

        # 4. Financial & Fee Optimization Panel
        total_pnl = metrics.get("total_pnl", 0.0)
        fees_paid = metrics.get("total_fees_paid", 0.0)
        taker_saved = metrics.get("total_taker_saved", 0.0)
        total_trades = metrics.get("total_trades", 0)

        pnl_color = "green" if total_pnl >= 0 else "red"
        pnl_text = Text.assemble(
            (f"Realized PnL: ", "bold"), (f"${total_pnl:+,.2f}\n", f"bold {pnl_color}"),
            (f"Maker Fees Paid: ", "dim"), (f"${fees_paid:,.2f}  |  ", "white"),
            (f"Taker Fees Saved: ", "bold green"), (f"${taker_saved:,.2f}\n", "bold green"),
            (f"Total Filled Trades: ", "dim"), (f"{total_trades} orders", "bold white"),
        )
        layout["financials"].update(
            Panel(pnl_text, title="[bold green][Finance] Fee & Profit Metrics[/bold green]", border_style="green")
        )

        # 5. Recent Trades Log Table
        trades_table = Table(expand=True, box=None)
        trades_table.add_column("Time", style="dim", width=8)
        trades_table.add_column("Pair", style="cyan", width=10)
        trades_table.add_column("Side", width=6)
        trades_table.add_column("Volume", justify="right", style="white")

        recent = metrics.get("recent_trades", [])
        if not recent:
            trades_table.add_row("-", "-", "Menunggu fill...", "-")
        else:
            for t in recent:
                side_color = "green" if t["side"] == "BUY" else "red"
                trades_table.add_row(
                    t["time"],
                    t["pair"],
                    Text(t["side"], style=f"bold {side_color}"),
                    f"${t['volume']:,.2f}",
                )

        layout["recent_trades"].update(
            Panel(trades_table, title="[bold yellow][History] Aktivitas Trade Terkini[/bold yellow]", border_style="yellow")
        )

        # 6. Footer Panel
        footer_text = Text("Tekan [Ctrl + C] untuk Graceful Shutdown (Semua open order otomatis dibatalkan)", style="bold red")
        layout["footer"].update(Panel(Align.center(footer_text), style="dim"))

        return layout
