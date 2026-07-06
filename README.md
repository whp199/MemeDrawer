# 🧹 MemeDrawer (Meme Drawer)

![MemeDrawer Ad Banner](memedrawer_ad.jpg)

> **"Uh oh, Mimi found your meme drawer!"**
> 
> *"Master! I found your... meme drawer! Let me tidy it up for you!"*

```text
   (\_/)
  ( ^.^ )  * Mimi *
  / >♥< \
 (_______)
```

MemeDrawer is a beautiful, intuitive Python CLI application designed to organize and rename large, messy folders of memes, image macros, and reaction images. It uses multimodal LLMs (either local models via LM-Studio/Ollama or cloud models like Google Gemini) to analyze images, classify them into appropriate categories (such as 4chan boards like `/g/` or `/pol/`, or emotions like `reaction images/happy`), and rename them descriptively.

MemeDrawer features a cute anime maid mascot, **Mimi**, who guides you through the process with custom interactive dialogue and beautiful terminal visuals using `rich`.

---

## ✨ Features

- **🧠 Multimodal LLM Classification**: Connects to Google Gemini (highly recommended for speed/accuracy) or local OpenAI-compatible endpoints (like LM-Studio).
- **⚡ Low Latency Optimization**: Preprocesses and compresses images in-memory (down to max 800px width/height JPEGs) to minimize upload bandwidth and inference times.
- **🚀 High Throughput / Concurrency Control**: Process multiple images in parallel. Easily configurable to sequential mode (`--concurrency 1` or `--sequential`) to prevent consumer GPUs from bottlenecking when using local models.
- **🔄 Safety First (Undo Log & Cache)**:
  - Keep track of sorted files in a local cache database to skip duplicate classifications on re-runs.
  - Run with `--dry-run` to preview actions.
  - Revert the last cleanup operation instantly with the `undo` command.
- **🌸 Mimi the Maid UI**: Beautiful progress bars, status dashboards, activity logs, and ASCII art of your personal maid assisting you.

---

## 🛠️ Installation

MemeDrawer is packaged using `uv` for modern, fast Python package management.

1. **Clone the repository** (or run inside the project workspace directory).
2. **Install dependencies** (or let `uv` handle running the app):
   ```bash
   uv pip install -e .
   ```
   *This makes the `memedrawer` command available globally in your virtual environment.*

---

## 🚀 Commands

### 1. Initialize Configuration
Set up your AI provider (Gemini vs. Local LM-Studio), API Keys, and default naming/sorting rules:
```bash
memedrawer init
```

### 2. View Configuration Status
Verify your active settings and check if Mimi is ready to clean:
```bash
memedrawer status
```

### 3. Sort a Directory
Organize and rename files in a messy folder:
```bash
# Preview what Mimi would do (dry run)
memedrawer sort /path/to/memes -d

# Execute sorting (parallel requests)
memedrawer sort /path/to/memes

# Execute sorting sequentially (recommended for local models)
memedrawer sort /path/to/memes --sequential

# Scan folders recursively
memedrawer sort /path/to/memes --recursive

# Sort without renaming files
memedrawer sort /path/to/memes --no-rename

# Sort and ask Mimi to make cute comments on each meme
memedrawer sort /path/to/memes --with-comments
```

### 4. Revert the Last Sort Operation
Puts all moved files back in their original folders and restores their original filenames:
```bash
memedrawer undo
```

---

## 📂 Sorting Rules Structure

Mimi cleans your drawer into the following folder structure:
- **Board Directories**: If an image belongs to a specific topic, it gets sorted into standard board directories:
  - Technology/Coding/Hardware -> `g/` (with optional sub-folder like `g/programming/`)
  - Video Games -> `v/`
  - Politics/News -> `pol/`
  - Anime/Manga -> `a/`
  - Finance/Crypto -> `biz/`
- **Reaction Images**: If it is a generic reaction face/macro, it goes into:
  - `reaction images/{emotion}/` (e.g., `reaction images/happy/`, `reaction images/sad/`, `reaction images/smug/`).
- **Other General Directories**: E.g., `gaming/`, `technology/`, `cat memes/`, `wallpapers/`.
- **Descriptive Names**: Files are renamed based on visual content (e.g. `sad_pepe_crying.jpg`, `wojak_feels_bad.png`). If names collide, a counter is appended (e.g., `sad_pepe_crying_1.jpg`).

---

## 🧪 Testing

To run the automated test suite and ensure all features function correctly:
```bash
uv run python -m unittest tests/test_memedrawer.py
```
