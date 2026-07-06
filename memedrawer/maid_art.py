from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text

# ASCII Art representations of Mimi with different expressions
MIMI_ART = {
    "happy": """
   (\\_/)
  ( ^.^ )  * Mimi *
  / >♥< \\
 (_______)
""",
    "cleaning": [
        """
   (\\_/)
  ( o.o )  * Mimi *
  / >🧹  \\
 (_______)
""",
        """
   (\\_/)
  ( -.- )  * Mimi *
   \\  🧹> \\
 (_______)
""",
        """
   (\\_/)
  ( o.o )  * Mimi *
   \\ >🧹/ 
 (_______)
"""
    ],
    "sad": """
   (\\_/)
  ( ;.; )  * Mimi *
  / >💧< \\
 (_______)
""",
    "proud": """
   (\\_/)
  (  *.* )  * Mimi *
  / >🌟< \\
 (_______)
"""
}

MIMI_QUOTES = {
    "welcome": [
        "Welcome home, Master! The meme drawer is quite a mess, isn't it? Let me tidy it up for you!",
        "Master, did you save all these memes again? Don't worry, Mimi is here to organize them!",
        "A tidy drawer makes a happy Master! I'm ready to organize your image collection."
    ],
    "sorting_start": [
        "Starting the cleaning now! Please rest while Mimi does the hard work... 🧹",
        "Let's see what treasures you have saved here, Master! Processing...",
        "Dusting off the files and asking the AI spirits for guidance!"
    ],
    "sorting_progress": "Cleaning image {index} of {total}: [bold cyan]{filename}[/bold cyan]...",
    "sorting_success": [
        "Master! I've finished organizing the drawer! Everything is in its proper place now. ✨",
        "Tada! Your memes are perfectly sorted! Mimi is so glad to be of service!",
        "All clean! I even renamed them so you can find them easily next time."
    ],
    "dry_run": [
        "Master, this is just a practice run (dry-run). I won't move anything yet, just showing you my plan!",
        "Here is what I plan to do when you let me clean for real, Master!"
    ],
    "error": [
        "Oh no, Master! Something went wrong... Mimi is so sorry! 💧",
        "A-ara... the AI backend didn't respond correctly. Let's check the settings."
    ],
    "undo": [
        "Reverting my last cleanup! Putting all your memes back exactly where they were, Master.",
        "Undoing changes... Mimi is returning the drawer to its original state."
    ]
}

def get_mimi_speech(text: str, expression: str = "happy", title: str = "Mimi the Meme Maid") -> Panel:
    """Creates a beautiful Rich Panel combining Mimi's ASCII art and her speech."""
    art = MIMI_ART.get(expression, MIMI_ART["happy"])
    
    # If the art has multiple animation frames, select one based on current time
    if isinstance(art, list):
        import time
        frame_idx = int(time.time() * 4) % len(art)
        art = art[frame_idx]
        
    art = art.strip("\n")
    
    # We use Columns to display Mimi next to her speech bubble
    art_text = Text(art, style="bold #ff77aa")
    speech_text = Text.from_markup(text, style="italic")
    
    # Wrap speech in a panel that looks like a speech bubble
    speech_panel = Panel(
        speech_text,
        title=title,
        title_align="left",
        border_style="cyan",
        expand=True
    )
    
    # Combine art and bubble using Columns
    return Panel(
        Columns([art_text, speech_panel], padding=(0, 2), expand=True),
        border_style="#ff77aa",
        padding=(1, 2)
    )
