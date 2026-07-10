import asyncio
import os
import sys
from pathlib import Path
from typing import List, Optional
import typer
from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, MofNCompleteColumn, ProgressColumn
from rich.live import Live

from memedrawer.config import AppConfig, load_config, save_config, get_config_paths
from memedrawer.sorter import SorterEngine
from memedrawer.maid_art import get_mimi_speech, MIMI_QUOTES

class MemesPerMinuteColumn(ProgressColumn):
    """Renders processing rate as memes-per-minute (MPM)."""
    def render(self, task) -> Text:
        speed = task.finished_speed or task.speed
        if speed is None:
            return Text("0.0 mpm", style="progress.data.speed")
        mpm = speed * 60.0
        return Text(f"{mpm:.1f} mpm", style="progress.data.speed")

class MemeETAColumn(ProgressColumn):
    """Renders calculated ETA based on the current MPM rate."""
    def render(self, task) -> Text:
        if task.finished:
            return Text("ETA: 00:00", style="progress.remaining")
        speed = task.finished_speed or task.speed
        if speed is None or speed <= 0:
            return Text("ETA: --:--", style="progress.remaining")
        
        remaining = task.total - task.completed
        eta_seconds = remaining / speed
        
        hours, remainder = divmod(int(eta_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            eta_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            eta_str = f"{minutes:02d}:{seconds:02d}"
            
        return Text(f"ETA: {eta_str}", style="progress.remaining")

app = typer.Typer(help="MemeDrawer: A beautiful CLI tool to sort and rename your messy meme folders with Mimi the maid!")
console = Console()

@app.command()
def init():
    """Interactive wizard to configure MemeDrawer settings."""
    console.print(get_mimi_speech(MIMI_QUOTES["welcome"][0], expression="happy"))
    
    current_config = load_config()
    # 1. Select provider (always "local" for local models)
    provider = "local"
    
    openai_key = current_config.openai_api_key
    openai_url = current_config.openai_base_url
    openai_model = current_config.openai_model
    
    openai_url = typer.prompt(
        "Enter local OpenAI-compatible endpoint URL (e.g., LM-Studio, Ollama)",
        default=openai_url
    )
    openai_key = typer.prompt(
        "Enter API Key (press Enter if none/local)",
        default=openai_key or "",
        hide_input=True
    )
    if not openai_key:
        openai_key = None
    openai_model = typer.prompt(
        "Enter local model name",
        default=openai_model
    )

    # Common Settings
    rename = typer.confirm("Would you like Mimi to rename memes descriptively by default?", default=current_config.rename_files)
    
    concurrency = typer.prompt(
        "Enter maximum parallel requests (concurrency=1 is highly recommended for local endpoints)",
        default=current_config.concurrency or 1,
        type=int
    )
    
    board_sorting = typer.confirm("Sort images into 4chan board folders (e.g. /g/, /pol/) if applicable?", default=current_config.board_sorting)
    strict_subfolders = typer.confirm("Only sort files into existing subfolders (strict mode)?", default=current_config.strict_subfolders)

    # Save globally
    new_config = AppConfig(
        provider=provider,
        openai_api_key=openai_key,
        openai_base_url=openai_url,
        openai_model=openai_model,
        concurrency=concurrency,
        rename_files=rename,
        board_sorting=board_sorting,
        strict_subfolders=strict_subfolders
    )
    
    global_path = save_config(new_config, local=False)
    
    console.print(get_mimi_speech(
        f"Thank you, Master! I've saved your configurations to [bold cyan]{global_path}[/bold cyan]. I'm ready to tidy up whenever you need me!",
        expression="proud"
    ))

@app.command()
def status():
    """View current MemeDrawer configurations."""
    config = load_config()
    local_path, global_path = get_config_paths()
    
    table = Table(title="MemeDrawer Active Configuration", show_header=True, header_style="bold magenta")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Config Path (Global)", str(global_path) if global_path.exists() else "Not created (runs on defaults)")
    table.add_row("Config Path (Local)", str(local_path) if local_path.exists() else "None (using global/default)")
    table.add_row("Active Provider", config.provider)
    
    table.add_row("OpenAI Base URL", config.openai_base_url)
    table.add_row("OpenAI Model", config.openai_model)
    table.add_row("OpenAI API Key", "Configured (Hidden)" if config.openai_api_key else "None (or local bypass)")
        
    table.add_row("Default Concurrency", str(config.concurrency))
    table.add_row("Rename Files By Default", "Yes" if config.rename_files else "No")
    table.add_row("Board-level Sorting (/g/, /pol/)", "Yes" if config.board_sorting else "No")
    table.add_row("Strict Subfolders Sorting", "Yes" if config.strict_subfolders else "No")
    table.add_row("Reaction Folder Name", config.reaction_images_dir)
    
    console.print(table)
    console.print(get_mimi_speech("Your settings look perfect! Mimi is ready to sweep some files.", "happy"))

@app.command()
def sort(
    directory: Path = typer.Argument(..., help="Directory full of messy memes to organize"),
    dry_run: bool = typer.Option(False, "--dry-run", "-d", help="Dry run: preview actions without modifying files"),
    no_rename: bool = typer.Option(False, "--no-rename", help="Do not rename files, only sort them into subdirectories"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Scan the directory recursively for images"),
    concurrency: Optional[int] = typer.Option(None, "--concurrency", "-c", help="Override the concurrent requests limit"),
    sequential: bool = typer.Option(False, "--sequential", "-s", help="Force sequential processing (concurrency=1), recommended for local LLMs"),
    with_comments: bool = typer.Option(False, "--with-comments", "-w", help="Ask Mimi to make cute comments on each meme based on its content"),
    strict_subfolders: Optional[bool] = typer.Option(None, "--strict-subfolders/--no-strict-subfolders", help="Only sort files into existing subfolders (never create new directories); leave others in the root. Overrides the saved config.")
):
    """Sort and rename images in a folder using Mimi's cleaning skills."""
    config = load_config()

    # Overrides
    if strict_subfolders is not None:
        config.strict_subfolders = strict_subfolders

    rename = config.rename_files and not no_rename
    active_concurrency = config.concurrency
    if sequential:
        active_concurrency = 1
    elif concurrency is not None:
        active_concurrency = concurrency

    if not directory.exists() or not directory.is_dir():
        console.print(get_mimi_speech(f"Master, the path [bold red]{directory}[/bold red] doesn't seem to exist or is not a directory. Please check it!", "sad"))
        raise typer.Exit(code=1)

    directory = directory.resolve()

    # Initialize Engine
    engine = SorterEngine(directory, config, dry_run=dry_run, rename=rename)
    
    # Greet
    welcome_msg = MIMI_QUOTES["dry_run"][0] if dry_run else MIMI_QUOTES["welcome"][1]
    console.print(get_mimi_speech(welcome_msg, expression="happy"))
    
    # Scan files
    try:
        files = engine.scan_files(recursive=recursive)
    except Exception as e:
        console.print(get_mimi_speech(f"I couldn't scan the folder, Master. Error: {e}", "sad"))
        raise typer.Exit(code=1)

    if not files:
        console.print(get_mimi_speech("Master, I couldn't find any images in that folder to sort! (Support: JPG, PNG, WEBP, GIF, BMP)", "happy"))
        return

    console.print(f"[bold green]Found {len(files)} images to process.[/bold green]")
    if dry_run:
        console.print("[yellow]Running in DRY-RUN mode. No files will be moved or renamed.[/yellow]\n")

    # We will show a live dashboard containing:
    # 1. Mimi cleaning speech
    # 2. Progress bar
    # 3. Running table of recent actions
    recent_actions: List[tuple[str, str, str, Optional[str]]] = []  # (Filename, Success/Status, Action/Details, Commentary)
    
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        MemesPerMinuteColumn(),
        MemeETAColumn(),
        console=console
    )
    
    task_id = progress.add_task("[bold cyan]Cleaning Meme Drawer...", total=len(files))
    
    # Create the Live View Group
    def make_live_render():
        # Mimi panel
        speech = MIMI_QUOTES["sorting_start"][0]
        if len(recent_actions) > 0:
            last_file, status, details, commentary = recent_actions[-1]
            if with_comments and commentary:
                speech = f"Just processed [bold cyan]{last_file}[/bold cyan]! Mimi says: \"[bold #ff77aa]{commentary}[/bold #ff77aa]\""
            else:
                speech = f"Just processed [bold cyan]{last_file}[/bold cyan] -> {details}"
            
        mimi_panel = get_mimi_speech(speech, expression="cleaning")
        
        # Recent actions table
        table = Table(title="Cleaning Activity Log", show_header=True, expand=True)
        table.add_column("File", style="cyan", ratio=3)
        table.add_column("Status", style="bold", ratio=2)
        table.add_column("Details", style="green", ratio=5)
        
        # Show last 5 actions
        for item in recent_actions[-5:]:
            table.add_row(item[0], item[1], item[2])
            
        return Group(mimi_panel, progress, table)

    # Callback when a file is processed
    def progress_callback(file_path: Path, success: bool, details: str, classification=None):
        status_str = "[bold green]OK[/bold green]" if success else "[bold red]ERROR[/bold red]"
        # Trim details if very long
        trimmed_details = details if len(details) < 60 else details[:57] + "..."
        commentary = getattr(classification, "commentary", None) if classification else None
        recent_actions.append((file_path.name, status_str, trimmed_details, commentary))
        progress.advance(task_id)
        # Update the live display with the new logs and Mimi speech
        live.update(make_live_render())

    # Execute async loop
    async def run_sort():
        return await engine.sort_files(files, concurrency=active_concurrency, progress_callback=progress_callback)

    with Live(make_live_render(), console=console, refresh_per_second=4) as live:
        progress.start()
        # Run sorting logic in async loop
        try:
            summary = asyncio.run(run_sort())
        except Exception as e:
            live.stop()
            console.print(get_mimi_speech(f"Master, an unexpected error occurred during execution: {e}", "sad"))
            raise typer.Exit(code=1)
        finally:
            progress.stop()

    # Final reports
    console.print("\n")
    console.print("[bold magenta]━━━ Cleaning Summary Report ━━━[/bold magenta]")
    
    summary_table = Table(show_header=True, header_style="bold yellow")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Count", style="green")
    
    summary_table.add_row("Total Scanned Images", str(summary["total"]))
    summary_table.add_row("Successfully Sorted", str(summary["success"]))
    summary_table.add_row("Skipped (Already sorted)", str(summary["skipped"]))
    summary_table.add_row("Failed (Errors)", str(summary["error"]))
    
    console.print(summary_table)
    
    # Detail table for what changed
    if summary["success"] > 0 or summary["error"] > 0:
        details_table = Table(title="Sorted Files Details", show_header=True)
        details_table.add_column("Original Name", style="cyan")
        details_table.add_column("Classification & Location", style="green")
        if with_comments:
            details_table.add_column("Mimi's Commentary", style="bold #ff77aa")
        details_table.add_column("Details", style="italic")
        
        for res in summary["results"]:
            if res["action"] == "error":
                row = [
                    Path(res["original_path"]).name,
                    "[red]FAILED[/red]"
                ]
                if with_comments:
                    row.append("N/A")
                row.append(res["explanation"])
                details_table.add_row(*row)
            elif res["action"] == "moved":
                orig_name = Path(res["original_path"]).name
                rel_dest = Path(res["new_path"]).relative_to(directory)
                row = [
                    orig_name,
                    f"Moved to [bold]{rel_dest}[/bold]"
                ]
                if with_comments:
                    row.append(res.get("commentary") or "N/A")
                row.append(res["explanation"])
                details_table.add_row(*row)
            elif res["action"] == "would move":
                orig_name = Path(res["original_path"]).name
                rel_dest = Path(res["new_path"]).relative_to(directory)
                row = [
                    orig_name,
                    f"Would move to [yellow]{rel_dest}[/yellow]"
                ]
                if with_comments:
                    row.append(res.get("commentary") or "N/A")
                row.append(res["explanation"])
                details_table.add_row(*row)
        
        console.print(details_table)

    # Success speech
    if summary["error"] == 0:
        msg = MIMI_QUOTES["sorting_success"][0]
        expr = "proud"
    else:
        msg = f"Master, I completed the sorting with {summary['error']} errors. I tried my very best! Please check the details above."
        expr = "sad"
        
    console.print(get_mimi_speech(msg, expression=expr))

    # Determine favorite meme from the session's cached comments
    if with_comments:
        meme_comments = []
        for last_file, status, details, commentary in recent_actions:
            if "OK" in status and commentary and commentary != "N/A":
                meme_comments.append({
                    "filename": last_file,
                    "commentary": commentary
                })
        
        if meme_comments:
            console.print("\n")
            with console.status("[bold pink]Mimi is thinking about her favorite meme...[/bold pink]"):
                try:
                    favorite_speech = engine.classifier.determine_favorite_meme(meme_comments)
                except Exception as e:
                    favorite_speech = f"I liked all of them so much, Master! Especially {meme_comments[0]['filename']}!"
            
            if favorite_speech:
                console.print(get_mimi_speech(
                    f"Oh, by the way, Master! {favorite_speech}",
                    expression="proud",
                    title="Mimi's Favorite Meme"
                ))

@app.command()
def undo():
    """Revert the last sorting operation."""
    console.print(get_mimi_speech(MIMI_QUOTES["undo"][0], expression="happy"))
    
    try:
        reverted = SorterEngine.undo_last_operation()
        if not reverted:
            console.print(get_mimi_speech("Master, there was nothing to undo or the last operations are already reverted!", "happy"))
            return
            
        table = Table(title="Reverted Files", show_header=True)
        table.add_column("Restored From Path", style="yellow")
        table.add_column("Restored To Original Path", style="green")
        
        for curr, orig in reverted:
            table.add_row(curr, orig)
            
        console.print(table)
        console.print(get_mimi_speech("Everything is back to how it was! Master's meme drawer is messy once again, but that's okay!", "proud"))
        
    except Exception as e:
        console.print(get_mimi_speech(f"Master, I couldn't undo the changes. Error: {e}", "sad"))

def run_interactive_entry():
    console.print(get_mimi_speech(
        "Welcome home, Master! Mimi is here to help you clean up your meme drawer!\n\n"
        "[bold #ff77aa]Please drag and drop your meme folder here[/bold #ff77aa] (or type its path) and press [bold green]Enter[/bold green]:",
        expression="happy"
    ))
    
    while True:
        try:
            folder_input = input("Meme Folder: ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[red]Goodbye, Master![/red]")
            return
            
        if not folder_input:
            console.print("[yellow]Please enter a valid path, Master![/yellow]")
            continue
            
        # Clean quotes added by drag-and-drop
        folder_path_str = folder_input.strip().strip("'\"")
        # Handle macOS/Linux terminal space escaping
        if os.name != 'nt':
            folder_path_str = folder_path_str.replace('\\ ', ' ')
            
        folder_path = Path(folder_path_str)
        
        if not folder_path.exists():
            console.print(f"[bold red]Mimi couldn't find that path:[/bold red] {folder_path_str}. Please try again!")
            continue
        if not folder_path.is_dir():
            console.print(f"[bold red]That path is not a directory, Master:[/bold red] {folder_path_str}. Please drag a folder!")
            continue
            
        break
        
    # Check if configured
    local_path, global_path = get_config_paths()
    is_configured = local_path.exists() or global_path.exists()
    
    # If not configured, run interactive wizard
    if not is_configured:
        console.print(get_mimi_speech(
            "It looks like we haven't set up our AI helper yet. Let's do that quickly so Mimi can get to work!",
            expression="happy"
        ))
        init()
        
    config = load_config()
        
    # Now ask to sort!
    console.print(get_mimi_speech(
        f"Wonderful! Mimi is going to clean up [bold cyan]{folder_path}[/bold cyan] now.\n"
        "Would you like to run a dry-run first to preview changes, or sort immediately?",
        expression="proud"
    ))
    
    mode = typer.prompt(
        "Enter mode (sort / dry-run / cancel)",
        default="sort"
    ).strip().lower()
    
    if mode == "cancel":
        console.print("[yellow]Operation cancelled by Master.[/yellow]")
        return
        
    dry_run = (mode == "dry-run")
    
    # Ask if they want comments
    with_comments = typer.confirm("Would you like Mimi to comment on each meme in a cute way?", default=True)
    
    # Ask if they want strict subfolders
    strict_subfolders = typer.confirm("Would you like to restrict sorting strictly to pre-existing subfolders?", default=config.strict_subfolders)
    
    # Run the sort command logic!
    sort(
        directory=folder_path,
        dry_run=dry_run,
        no_rename=False,
        recursive=False,
        concurrency=None,
        sequential=False,
        with_comments=with_comments,
        strict_subfolders=strict_subfolders
    )

def main():
    if len(sys.argv) == 1:
        # Run custom interactive entry point for drag-and-drop users
        run_interactive_entry()
    else:
        app()

if __name__ == "__main__":
    main()
