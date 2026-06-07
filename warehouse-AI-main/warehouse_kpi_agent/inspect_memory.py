#!/usr/bin/env python3
"""Memory Database Inspector.

Utility script to inspect conversation sessions and checkpoints from SQLite.

Usage:
    python inspect_memory.py list               # List all sessions
    python inspect_memory.py history <thread_id> # Show conversation history
    python inspect_memory.py clear <thread_id>   # Clear specific session
    python inspect_memory.py clear-all           # Clear all sessions
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from app.config.memory import (
    list_sessions,
    get_session_history,
    clear_session,
    clear_all_sessions,
    MEMORY_DB_PATH,
)

console = Console()


def cmd_list_sessions(args):
    """List all conversation sessions."""
    console.print(Panel(
        f"[cyan]Memory Database:[/cyan] {MEMORY_DB_PATH}",
        title="Session Inspector",
        expand=False
    ))
    
    sessions = list_sessions(limit=args.limit)
    
    if not sessions:
        console.print("[yellow]No sessions found.[/yellow]")
        return
    
    table = Table(title=f"Conversation Sessions (Last {args.limit})")
    table.add_column("Thread ID", style="cyan", no_wrap=True)
    table.add_column("Checkpoints", justify="right", style="green")
    table.add_column("Last Checkpoint ID", style="magenta")
    table.add_column("Last Namespace", style="blue")
    
    for session in sessions:
        table.add_row(
            session["thread_id"][:36],  # Truncate if long
            str(session["checkpoint_count"]),
            session["last_checkpoint_id"],
            session["last_checkpoint_ns"] or "N/A"
        )
    
    console.print(table)
    console.print(f"\n[dim]Total: {len(sessions)} session(s)[/dim]")


def cmd_session_history(args):
    """Show checkpoint history for a specific session."""
    thread_id = args.thread_id
    
    console.print(Panel(
        f"[cyan]Session:[/cyan] {thread_id}",
        title="Conversation History",
        expand=False
    ))
    
    checkpoints = get_session_history(thread_id)
    
    if not checkpoints:
        console.print(f"[yellow]No checkpoints found for session: {thread_id}[/yellow]")
        return
    
    table = Table(title=f"Checkpoints for {thread_id[:36]}")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Checkpoint ID", style="cyan")
    table.add_column("Namespace", style="blue")
    table.add_column("Parent ID", style="magenta")
    table.add_column("Type", style="green")
    
    for i, cp in enumerate(checkpoints, 1):
        table.add_row(
            str(i),
            cp["checkpoint_id"],
            cp["checkpoint_ns"] or "N/A",
            cp["parent_checkpoint_id"] or "None",
            cp["type"] or "N/A"
        )
    
    console.print(table)
    console.print(f"\n[dim]Total: {len(checkpoints)} checkpoint(s)[/dim]")


def cmd_clear_session(args):
    """Clear a specific session."""
    thread_id = args.thread_id
    
    if not args.yes:
        response = console.input(
            f"[yellow]Are you sure you want to delete session {thread_id}? (yes/no):[/yellow] "
        )
        if response.lower() != "yes":
            console.print("[dim]Cancelled.[/dim]")
            return
    
    success = clear_session(thread_id)
    
    if success:
        console.print(f"[green]✔ Session cleared: {thread_id}[/green]")
    else:
        console.print(f"[red]✖ Failed to clear session: {thread_id}[/red]")


def cmd_clear_all(args):
    """Clear all sessions."""
    if not args.yes:
        response = console.input(
            "[red]WARNING: This will delete ALL conversation history! Continue? (yes/no):[/red] "
        )
        if response.lower() != "yes":
            console.print("[dim]Cancelled.[/dim]")
            return
    
    success = clear_all_sessions()
    
    if success:
        console.print("[green]✔ All sessions cleared.[/green]")
    else:
        console.print("[red]✖ Failed to clear sessions.[/red]")


def main():
    parser = argparse.ArgumentParser(
        description="Inspect warehouse KPI agent conversation memory"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all sessions")
    list_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of sessions to show (default: 50)"
    )
    list_parser.set_defaults(func=cmd_list_sessions)
    
    # History command
    history_parser = subparsers.add_parser("history", help="Show session history")
    history_parser.add_argument("thread_id", help="Session/thread ID to inspect")
    history_parser.set_defaults(func=cmd_session_history)
    
    # Clear command
    clear_parser = subparsers.add_parser("clear", help="Clear a specific session")
    clear_parser.add_argument("thread_id", help="Session/thread ID to clear")
    clear_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    clear_parser.set_defaults(func=cmd_clear_session)
    
    # Clear-all command
    clear_all_parser = subparsers.add_parser("clear-all", help="Clear all sessions")
    clear_all_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    clear_all_parser.set_defaults(func=cmd_clear_all)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    args.func(args)


if __name__ == "__main__":
    main()
