"""Warehouse KPI Agent — Interactive CLI.

Usage:
    python -m app.main [--load-data]

Flags:
    --load-data   Load (or reload) all CSV files into MongoDB before starting.
"""

import argparse
import logging
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule

# ── Bootstrap: triggers sys.path setup & .env loading ─────────────────────────
import app.config.settings  # noqa: F401
from app.config.memory import create_session_id, get_session_config
from app.graph.graph_builder import graph

console = Console(width=110)
logger = logging.getLogger(__name__)

_HELP_TEXT = """[dim]
Examples:
  • What is the fill rate for WH-01 in January 2025?
  • Show all KPIs for warehouse WH-02 from 2025-01-01 to 2025-03-31
  • Analyse the employee productivity data
  • Give me an overview of all warehouse collections
  • What is the stockout percentage?

Type [bold]exit[/bold] or [bold]quit[/bold] to leave.
Type [bold]help[/bold] to show this message.
[/dim]"""


def _load_data(force: bool = True) -> None:
    """Load CSV data into MongoDB."""
    from app.db.data_loader import load_all

    console.print(Panel(
        "[yellow]Loading CSV data into MongoDB…[/yellow]",
        title="Data Loader",
        expand=False,
    ))
    try:
        load_all(force_reload=force)
        console.print("[green]✔ Data loaded successfully.[/green]\n")
    except Exception as exc:
        console.print(f"[red]✖ Data load failed: {exc}[/red]\n")
        sys.exit(1)


def _run_query(user_query: str, session_id: str) -> None:
    """Invoke the LangGraph pipeline for a single user query with memory.
    
    Args:
        user_query: User's question
        session_id: Thread ID for conversation memory
    """
    initial_state = {
        "user_query": user_query,
        "conversation_history": [],  # Will be populated from checkpointer
    }
    
    # Config with thread_id for checkpointing
    config = get_session_config(session_id)

    with console.status("[bold green]Thinking…[/bold green]", spinner="dots"):
        try:
            final_state = graph.invoke(initial_state, config)
        except Exception as exc:
            logger.exception("Graph invocation error")
            console.print(f"[red]Unexpected error: {exc}[/red]")
            return

    response = final_state.get("formatted_response", "")
    if response:
        console.print(Markdown(response))
    else:
        console.print("[dim]No response generated.[/dim]")

    # Surface non-fatal errors after the response
    errors = final_state.get("errors") or []
    if errors:
        for err in errors:
            console.print(f"[dim yellow]Note: {err}[/dim yellow]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Warehouse KPI Agent CLI")
    parser.add_argument(
        "--load-data",
        action="store_true",
        help="Load / reload CSV data into MongoDB before starting the agent.",
    )
    args = parser.parse_args()

    if args.load_data:
        _load_data(force=True)

    console.print(_HELP_TEXT)
    
    # ── Create session for conversation memory ─────────────────────────────────
    session_id = create_session_id()
    console.print(f"[dim]Session ID: {session_id}[/dim]\n")

    # ── REPL loop ──────────────────────────────────────────────────────────────
    while True:
        try:
            user_input = Prompt.ask("[bold green]You[/bold green]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user_input:
            continue

        lower = user_input.lower()
        if lower in ("exit", "quit", "q", "bye"):
            console.print("[dim]Goodbye.[/dim]")
            break
        if lower in ("help", "?"):
            console.print(_HELP_TEXT)
            continue
        if lower == "new session":
            session_id = create_session_id()
            console.print(f"[green]✔ New session started: {session_id}[/green]")
            continue

        console.print(Rule())
        _run_query(user_input, session_id)
        console.print(Rule())


if __name__ == "__main__":
    main()
