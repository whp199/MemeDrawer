import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional
import typer
from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, MofNCompleteColumn, ProgressColumn
from rich.live import Live

from memedrawer.config import AppConfig, load_config, save_config, get_config_paths
from memedrawer.sorter import SorterEngine
from memedrawer.maid_art import get_mimi_speech, get_banner, mimi_quote

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

_banner_shown = False

def show_banner_once():
    global _banner_shown
    if not _banner_shown:
        console.print(get_banner())
        _banner_shown = True

def _records_path() -> Path:
    _, global_path = get_config_paths()
    return global_path.parent / "records.json"

def load_records() -> dict:
    """Loads lifetime fun-stats records (best mpm, total memes sorted)."""
    try:
        with open(_records_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_records(records: dict):
    try:
        path = _records_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4)
    except Exception:
        pass

def make_bar_table(counts: dict, title: str, max_rows: int = 12, bar_width: int = 24) -> Table:
    """Renders folder counts as a simple horizontal bar chart."""
    table = Table(title=title, show_header=False, box=None, padding=(0, 1))
    table.add_column("Folder", style="cyan", no_wrap=True)
    table.add_column("Bar")
    table.add_column("Count", style="bold green", justify="right")
    top = list(counts.items())[:max_rows]
    if not top:
        return table
    max_count = max(count for _, count in top)
    for name, count in top:
        bar_len = max(1, round(count / max_count * bar_width))
        table.add_row(name, Text("▰" * bar_len, style="#ff77aa"), str(count))
    return table

@app.command()
def init():
    """Interactive wizard to configure MemeDrawer settings."""
    console.print(get_mimi_speech(mimi_quote("welcome"), expression="happy"))
    
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
    show_banner_once()
    welcome_msg = mimi_quote("dry_run") if dry_run else mimi_quote("welcome")
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
    # 1. Mimi cleaning speech (her mood tracks how the run is going)
    # 2. Progress bar
    # 3. "Drawer filling up" folder counts
    # 4. Running table of recent actions
    recent_actions: List[tuple[str, str, str, Optional[str]]] = []  # (Filename, Success/Status, Action/Details, Commentary)
    folder_counts: Counter = Counter()
    start_speech = mimi_quote("sorting_start")

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
        # Mimi panel: her mood follows the run (cleaning normally, frazzled after an error)
        speech = start_speech
        expression = "cleaning"
        if len(recent_actions) > 0:
            last_file, status, details, commentary = recent_actions[-1]
            if "ERROR" in status:
                expression = "frazzled"
                speech = f"Oh no! [bold cyan]{last_file}[/bold cyan] gave me trouble: {details}"
            elif with_comments and commentary:
                speech = f"Just processed [bold cyan]{last_file}[/bold cyan]! Mimi says: \"[bold #ff77aa]{commentary}[/bold #ff77aa]\""
            else:
                speech = f"Just processed [bold cyan]{last_file}[/bold cyan] -> {details}"

        mimi_panel = get_mimi_speech(speech, expression=expression)

        renderables = [mimi_panel, progress]

        # Drawer panel: watch the folders fill up in real time
        if folder_counts:
            drawer = make_bar_table(dict(folder_counts.most_common(6)), title=None, max_rows=6)
            renderables.append(Panel(drawer, title="📂 Drawer Filling Up", title_align="left", border_style="cyan"))

        # Recent actions table
        table = Table(title="Cleaning Activity Log", show_header=True, expand=True)
        table.add_column("File", style="cyan", ratio=3)
        table.add_column("Status", style="bold", ratio=2)
        table.add_column("Details", style="green", ratio=5)

        # Show last 5 actions
        for item in recent_actions[-5:]:
            table.add_row(item[0], item[1], item[2])

        renderables.append(table)
        return Group(*renderables)

    # Callback when a file is processed
    def progress_callback(file_path: Path, success: bool, details: str, classification=None, target_path=None):
        status_str = "[bold green]OK[/bold green]" if success else "[bold red]ERROR[/bold red]"
        # Trim details if very long
        trimmed_details = details if len(details) < 60 else details[:57] + "..."
        commentary = getattr(classification, "commentary", None) if classification else None
        recent_actions.append((file_path.name, status_str, trimmed_details, commentary))
        if success and target_path is not None:
            rel_parent = Path(target_path).relative_to(directory).parent
            folder_key = str(rel_parent) if str(rel_parent) != "." else "(root)"
            folder_counts[folder_key] += 1
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

    # Folder tree: show the tidy drawer at a glance
    folder_file_counts: dict = {}
    for res in summary["results"]:
        if res["action"] in ("moved", "would move", "skipped (already sorted)"):
            folder = Path(res["new_path"]).relative_to(directory).parent
            folder_file_counts[folder] = folder_file_counts.get(folder, 0) + 1

    if folder_file_counts:
        tree = Tree(f"📂 [bold #ff77aa]{directory.name}[/bold #ff77aa]")
        nodes: dict = {}

        def node_for(folder: Path):
            if str(folder) == ".":
                return tree
            if folder not in nodes:
                nodes[folder] = node_for(folder.parent).add(f"📁 [cyan]{folder.name}[/cyan]")
            return nodes[folder]

        # Create nodes deepest-last so parents exist, then attach counts to labels
        for folder in sorted(folder_file_counts, key=lambda p: (len(p.parts), str(p))):
            node = node_for(folder)
            count = folder_file_counts[folder]
            if node is tree:
                tree.label = f"{tree.label}  [green]({count} in root)[/green]"
            else:
                node.label = f"{node.label} [green]({count})[/green]"

        console.print(Panel(tree, title="🗄️ Your Tidy Drawer", title_align="left", border_style="#ff77aa"))

    # Fun stats & lifetime records
    boards = Counter(
        res["board"] for res in summary["results"]
        if res.get("board") and res["action"] != "error"
    )
    task = progress.tasks[0]
    mpm = (task.finished_speed or 0) * 60

    records = load_records()
    new_record = summary["total"] >= 5 and mpm > records.get("best_mpm", 0)
    if new_record:
        records["best_mpm"] = round(mpm, 1)
    if not dry_run:
        records["lifetime_sorted"] = records.get("lifetime_sorted", 0) + summary["success"]
    if new_record or not dry_run:
        save_records(records)

    fun_table = Table(title="✨ Fun Stats", show_header=False, box=None, padding=(0, 1))
    fun_table.add_column("Stat", style="cyan")
    fun_table.add_column("Value", style="bold green")
    def meme_count(n: int) -> str:
        return f"{n} meme" + ("s" if n != 1 else "")

    if boards:
        board_name, board_count = boards.most_common(1)[0]
        fun_table.add_row("🌶️ Spiciest board", f"{board_name} ({meme_count(board_count)})")
    if folder_file_counts:
        biggest = max(folder_file_counts.items(), key=lambda kv: kv[1])
        biggest_name = str(biggest[0]) if str(biggest[0]) != "." else "(root)"
        fun_table.add_row("🗃️ Most stuffed folder", f"{biggest_name} ({meme_count(biggest[1])})")
    if mpm > 0:
        record_note = "  [bold #ff77aa]NEW RECORD![/bold #ff77aa]" if new_record else ""
        fun_table.add_row("⚡ Cleaning speed", f"{mpm:.1f} memes/minute{record_note}")
    if records.get("best_mpm"):
        fun_table.add_row("🏆 All-time speed record", f"{records['best_mpm']} memes/minute")
    if records.get("lifetime_sorted"):
        fun_table.add_row("🧹 Memes Mimi has sorted for you", str(records["lifetime_sorted"]))
    if fun_table.row_count:
        console.print(Panel(fun_table, border_style="cyan"))
    if new_record:
        console.print(get_mimi_speech(mimi_quote("record"), expression="celebrate", title="New Record!"))

    # Success speech: Mimi celebrates a perfect run, worries when everything failed
    if summary["error"] == 0:
        msg = mimi_quote("celebrate")
        expr = "celebrate"
    elif summary["error"] == summary["total"] and summary["total"] > 0:
        first_error = next((res["explanation"] for res in summary["results"] if res["action"] == "error"), "")
        msg = f"{mimi_quote('endpoint_error')}\n[dim]{first_error}[/dim]"
        expr = "surprised"
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
def stats(
    directory: Path = typer.Argument(..., help="Sorted meme library to analyze"),
    show_duplicates: bool = typer.Option(True, "--duplicates/--no-duplicates", help="Scan for duplicate memes (same file content)")
):
    """Analyze your sorted meme library: folder breakdown and duplicates. No AI calls needed."""
    show_banner_once()

    if not directory.exists() or not directory.is_dir():
        console.print(get_mimi_speech(f"Master, the path [bold red]{directory}[/bold red] doesn't seem to exist or is not a directory. Please check it!", "sad"))
        raise typer.Exit(code=1)

    console.print(get_mimi_speech(mimi_quote("stats"), expression="happy"))

    config = load_config()
    engine = SorterEngine(directory.resolve(), config, dry_run=True)
    data = engine.library_stats()

    if data["total"] == 0:
        console.print(get_mimi_speech("Master, this drawer is completely empty! Not a single meme to count.", "surprised"))
        return

    console.print(Panel(
        make_bar_table(data["folder_counts"], title=None),
        title=f"🗄️ Drawer Inventory — {data['total']} memes",
        title_align="left",
        border_style="#ff77aa"
    ))

    if show_duplicates:
        dupes = data["duplicate_groups"]
        if dupes:
            group_word = "group" if len(dupes) == 1 else "groups"
            dupe_table = Table(title=f"👯 Duplicate Memes ({len(dupes)} {group_word})", show_header=True)
            dupe_table.add_column("#", style="dim", justify="right")
            dupe_table.add_column("Copies", style="bold yellow", justify="right")
            dupe_table.add_column("Files", style="cyan")
            for idx, group in enumerate(dupes, 1):
                paths = "\n".join(str(p.relative_to(directory.resolve())) for p in group)
                dupe_table.add_row(str(idx), str(len(group)), paths)
            console.print(dupe_table)

            wasted = sum(len(g) - 1 for g in dupes)
            copies = "copy" if wasted == 1 else "copies"
            console.print(get_mimi_speech(
                f"{mimi_quote('duplicates')}\nYou could free up [bold yellow]{wasted}[/bold yellow] redundant {copies}, Master.",
                expression="surprised"
            ))
        else:
            console.print(get_mimi_speech(mimi_quote("no_duplicates"), expression="proud"))


@app.command()
def undo():
    """Revert the last sorting operation."""
    console.print(get_mimi_speech(mimi_quote("undo"), expression="happy"))
    
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
    show_banner_once()
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
