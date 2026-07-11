import random
import time
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text

# ASCII Art representations of Mimi with different expressions
MIMI_ART = {
    "happy": r"""
   .-~✿~-.
  { ^ ◡ ^ }  * Mimi *
  /)  ♥  (\
   |=====|
  /_______\
""",
    "cleaning": [
        r"""
   .-~✿~-.
  { o . o }  * Mimi *
  🧹)  ♥  (\
   |=====|
  /_______\
""",
        r"""
   .-~✿~-.
  { -.‿.- }  * Mimi *
  /)  ♥  (🧹
   |=====|
  /_______\
""",
        r"""
   .-~✿~-.
  { o.‿.o }  * Mimi *
  /) ♥ 🧹(\
   |=====|
  /_______\
""",
    ],
    "sad": r"""
   .-~✿~-.
  { ;  ;  }  * Mimi *
  /)  💧 (\
   |=====|
  /_______\
""",
    "proud": r"""
   .-~✿~-.
  { ✧ ◡ ✧ }  * Mimi *
  /)  🌟 (\
   |=====|
  /_______\
""",
    "surprised": r"""
   .-~✿~-.  !
  { O . O }  * Mimi *
  /)  ♥  (\
   |=====|
  /_______\
""",
    "frazzled": r"""
   .-~✿~-. 💦
  { @ ~ @ }  * Mimi *
  /)  ♥  (\
   |=====|
  /_______\
""",
    "celebrate": r"""
🎉 .-~✿~-. 🎉
  { > ▽ < }  * Mimi *
  \(  ♥  )/
   |=====|
  /_______\
""",
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
    "celebrate": [
        "All done, Master! Every single meme is tucked into its proper drawer! ✨",
        "Sparkling clean! Mimi didn't drop a single meme today! 🎉",
        "Mission complete! Your meme collection has never looked so organized!"
    ],
    "dry_run": [
        "Master, this is just a practice run (dry-run). I won't move anything yet, just showing you my plan!",
        "Here is what I plan to do when you let me clean for real, Master!"
    ],
    "error": [
        "Oh no, Master! Something went wrong... Mimi is so sorry! 💧",
        "A-ara... the AI backend didn't respond correctly. Let's check the settings."
    ],
    "endpoint_error": [
        "Master, I couldn't reach the AI spirits at all! Please check that your local LLM server (LM-Studio, Ollama...) is running, then let's try again!",
    ],
    "undo": [
        "Reverting my last cleanup! Putting all your memes back exactly where they were, Master.",
        "Undoing changes... Mimi is returning the drawer to its original state."
    ],
    "stats": [
        "Let me take inventory of your meme drawer, Master!",
        "Time to count the collection! Mimi loves a good stocktake. 📋",
    ],
    "record": [
        "A NEW SORTING RECORD, Master! Mimi is getting faster every day! ⚡",
        "Incredible speed! That's the fastest Mimi has ever cleaned this drawer!"
    ],
    "duplicates": [
        "Master... you saved the same meme more than once. Shall we tidy those up someday? 💦",
        "Mimi found some twins in the drawer! Duplicate memes detected!"
    ],
    "no_duplicates": [
        "Not a single duplicate! Master keeps a very disciplined collection!",
        "No twins found — every meme in your drawer is unique! ✨"
    ],
}

def mimi_quote(key: str) -> str:
    """Picks a random quote for the situation so Mimi doesn't repeat herself every run."""
    quotes = MIMI_QUOTES.get(key, "")
    if isinstance(quotes, list):
        return random.choice(quotes)
    return quotes

# "MEME DRAWER" in a compact box-drawing figlet style
BANNER_LINES = [
    "╔╦╗╔═╗╔╦╗╔═╗  ╔╦╗╦═╗╔═╗╦ ╦╔═╗╦═╗",
    "║║║║╣ ║║║║╣    ║║╠╦╝╠═╣║║║║╣ ╠╦╝",
    "╩ ╩╚═╝╩ ╩╚═╝  ═╩╝╩╚═╩ ╩╚╩╝╚═╝╩╚═",
]
BANNER_COLORS = ["#ff77aa", "#d98cc9", "#66d9ef"]

def get_banner() -> Text:
    """Gradient MEME DRAWER splash logo in Mimi's pink-to-cyan palette."""
    banner = Text()
    for line, color in zip(BANNER_LINES, BANNER_COLORS):
        banner.append(line + "\n", style=f"bold {color}")
    banner.append("   ✨ Your memes, lovingly sorted by Mimi the maid ✨\n", style="italic #ff9fc6")
    return banner

def get_mimi_speech(text: str, expression: str = "happy", title: str = "Mimi the Meme Maid") -> Panel:
    """Creates a beautiful Rich Panel combining Mimi's ASCII art and her speech."""
    art = MIMI_ART.get(expression, MIMI_ART["happy"])

    # If the art has multiple animation frames, select one based on current time
    if isinstance(art, list):
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
