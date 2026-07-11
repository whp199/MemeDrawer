# 🧹 MemeDrawer

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

MemeDrawer is a beautiful, intuitive Python CLI application designed to organize and rename large, messy folders of memes, image macros, and reaction images. It uses local multimodal LLMs (via LM-Studio, Ollama, llama.cpp, etc.) to analyze images, classify them into appropriate categories (such as 4chan boards like `/g/` or `/pol/`, or emotions like `reaction images/happy`), and rename them descriptively.

MemeDrawer features a cute anime maid mascot, **Mimi**, who guides you through the process with custom interactive dialogue and beautiful terminal visuals using `rich`.

---

## ✨ Features

- **🧠 Local Multimodal LLM Classification**: Connects to local OpenAI-compatible endpoints (like LM-Studio, Ollama, llama.cpp).
- **⚡ Low Latency Optimization**: Preprocesses and compresses images in-memory (down to max 800px width/height JPEGs) to minimize upload bandwidth and inference times.
- **🚀 High Throughput / Concurrency Control**: Process multiple images in parallel. Easily configurable to sequential mode (`--concurrency 1` or `--sequential`) to prevent consumer GPUs from bottlenecking when using local models.
- **📁 Strict Subfolders Restriction**: Optionally restrict sorting strictly to pre-existing subfolders at **any depth** — a flat `happy/`, `sad/`, `smug/` reaction library, nested topics like `pol/trump`, `pol/japan`, `pol/russia`, even deeper trees like `pol/russia/putin`. Matching is case-insensitive and finds the right parent even when the AI's category label differs from your folder name. In strict mode MemeDrawer never creates any new directory — files that don't match an existing folder simply stay in the root.
- **🧹 Folder Sprawl Prevention**: Existing subfolders are shown to the model so it reuses them (case-insensitively) instead of inventing near-duplicates, and subcategories that just restate their category (e.g. `pol/politics`) are dropped automatically.
- **🔄 Safety First (Undo Log & Cache)**:
  - Keep track of sorted files in a local cache database to skip duplicate classifications on re-runs.
  - Run with `--dry-run` to preview actions.
  - Revert the last cleanup operation instantly with the `undo` command.
- **🌸 Mimi the Maid UI**: Gradient splash banner, live "drawer filling up" dashboard, activity logs, and ASCII art of your personal maid — whose mood follows the run (cleaning, frazzled by errors, celebrating a perfect finish).
- **🏆 Fun Stats & Records**: End-of-run folder tree of your tidy drawer, spiciest board of the session, memes-per-minute speed records, and a lifetime sorted-memes counter.
- **📊 Library Stats & Duplicate Finder**: `stats` command shows a bar-chart inventory of your sorted drawer and finds duplicate memes by content hash — no AI calls needed.

---

## 🛠️ Installation & Running (No global pip needed)

MemeDrawer is packaged using `uv` (Astral's fast Python packaging tool written in Rust). This makes running the app on Gentoo or other Linux distributions extremely easy without needing global `pip` or risk polluting your system package manager (Portage).

### 1. Install `uv`
If you don't have `uv` installed:
- **Gentoo (Portage)**:
  ```bash
  sudo emerge dev-python/uv
  ```
- **Standalone Installer**:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

### 2. Run MemeDrawer (Zero Setup)
Simply navigate to the project directory and run:
```bash
# Run the interactive drag-and-drop cleaning mode
uv run python main.py

# Or run specific CLI commands directly
uv run python main.py sort /path/to/memes -w
```
*`uv` will automatically fetch the correct Python version, configure an isolated virtual environment, download the required dependencies defined in `pyproject.toml`, and run the app in one command.*

---

## 🚀 Commands

### 1. Initialize Configuration
Set up your local AI provider configurations (endpoint URL, API key, model name), and default naming/sorting rules:
```bash
uv run python main.py init
```

### 2. View Configuration Status
Verify your active settings and check if Mimi is ready to clean:
```bash
uv run python main.py status
```

### 3. Sort a Directory
Organize and rename files in a messy folder:
```bash
# Preview what Mimi would do (dry run)
uv run python main.py sort /path/to/memes -d

# Execute sorting (parallel requests)
uv run python main.py sort /path/to/memes

# Execute sorting sequentially (recommended for local models)
uv run python main.py sort /path/to/memes --sequential

# Scan folders recursively
uv run python main.py sort /path/to/memes --recursive

# Sort without renaming files
uv run python main.py sort /path/to/memes --no-rename

# Sort and ask Mimi to make cute comments on each meme
uv run python main.py sort /path/to/memes --with-comments

# Sort using only pre-existing subfolders (strict mode)
uv run python main.py sort /path/to/memes --strict-subfolders

# Force strict mode off for one run if it's enabled in your config
uv run python main.py sort /path/to/memes --no-strict-subfolders
```

After sorting, Mimi shows a folder tree of your tidy drawer plus fun stats: the spiciest board of the run, your cleaning speed in memes-per-minute (with an all-time speed record 🏆), and the lifetime count of memes she has sorted for you.

### 4. Analyze Your Library (no AI needed)
Get a bar-chart inventory of your sorted drawer and find duplicate memes (identical file content, even under different names):
```bash
uv run python main.py stats /path/to/memes

# Skip the duplicate scan
uv run python main.py stats /path/to/memes --no-duplicates
```

### 5. Revert the Last Sort Operation
Puts all moved files back in their original folders and restores their original filenames:
```bash
uv run python main.py undo
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
