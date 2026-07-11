import os
import re
import json
import asyncio
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from memedrawer.config import AppConfig, get_config_paths
from memedrawer.classifier import LLMClassifier, ClassificationResult

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

def get_file_hash(path: Path) -> str:
    """Computes SHA256 of the first 1MB of the file (fast hashing)."""
    hasher = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            # We only read up to 1MB for speed
            chunk = f.read(1024 * 1024)
            hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""

class SorterEngine:
    def __init__(self, target_dir: Path, config: AppConfig, dry_run: bool = False, rename: bool = True):
        self.target_dir = target_dir.resolve()
        self.config = config
        self.dry_run = dry_run
        self.rename = rename
        self.classifier = LLMClassifier(config)
        
        # Load local cache (stored inside the target folder to keep it portable)
        self.cache_path = self.target_dir / ".memedrawer_cache.json"
        self.cache = self._load_cache()

    def _load_cache(self) -> dict:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_cache(self):
        if self.dry_run:
            return
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=4)
        except Exception:
            pass

    def _iter_existing_dirs(self, root: Optional[Path] = None):
        """Yields every non-hidden subdirectory under root (default: target_dir),
        at any depth, as a Path relative to that root."""
        base = root or self.target_dir
        if not base.is_dir():
            return
        for dirpath, dirnames, _ in os.walk(base):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for d in dirnames:
                yield (Path(dirpath) / d).relative_to(base)

    def discover_existing_subfolders(self) -> Dict[str, List[str]]:
        """Scans the target directory and lists existing subdirectories under primary
        folders/boards. Descendants at any depth are included by name, so nested
        structures like pol/russia/putin are visible to the LLM too."""
        subfolders = {}
        if not self.target_dir.exists() or not self.target_dir.is_dir():
            return subfolders

        root_children = []
        for path in self.target_dir.iterdir():
            if path.is_dir() and not path.name.startswith("."):
                # e.g., path is target_dir / "g" or target_dir / "politics"
                root_children.append(path.name)
                children = sorted({rel.name for rel in self._iter_existing_dirs(path)})
                if children:
                    subfolders[path.name] = children

        if root_children:
            subfolders[""] = sorted(root_children)

        return subfolders

    def scan_files(self, recursive: bool = False) -> List[Path]:
        """Scans the target directory for image files."""
        if not self.target_dir.exists() or not self.target_dir.is_dir():
            raise FileNotFoundError(f"Target directory {self.target_dir} does not exist.")
            
        pattern = "**/*" if recursive else "*"
        found_files = []
        
        for p in self.target_dir.glob(pattern):
            # Ignore hidden files, cache files, and directory folders themselves
            if p.name.startswith(".") or p.is_dir():
                continue
            if p.suffix.lower() in IMAGE_EXTENSIONS:
                found_files.append(p)
                
        return sorted(found_files)

    def _match_existing_dir(self, parent: Path, name: str) -> Optional[str]:
        """Returns the actual name of an existing subdirectory of parent matching name
        case-insensitively, or None if no such directory exists."""
        if not parent.is_dir():
            return None
        lowered = name.strip().lower()
        for child in parent.iterdir():
            if child.is_dir() and child.name.lower() == lowered:
                return child.name
        return None

    def _resolve_child_dir(self, parent: Path, name: str) -> Path:
        """Joins name under parent, reusing an existing directory of the same name
        (case-insensitive) instead of creating a differently-cased duplicate."""
        existing = self._match_existing_dir(parent, name)
        return parent / (existing if existing is not None else name.strip().lower())

    @staticmethod
    def _normalize_folder_name(name: str) -> str:
        return re.sub(r"[\s_\-]+", " ", name.strip().lower())

    def is_redundant_subcategory(self, result: ClassificationResult) -> bool:
        """True when the subcategory merely restates the category it lives under
        (e.g. politics/politics or pol -> 'politics'), which would create a useless subfolder."""
        if not result.subcategory:
            return False
        sub = self._normalize_folder_name(result.subcategory)
        candidates = [result.primary_folder or "", (result.board or "").strip("/")]
        for cand in candidates:
            cand = self._normalize_folder_name(cand)
            if cand and (sub == cand or sub.rstrip("s") == cand.rstrip("s")):
                return True
        return False

    def _locate_strict_subfolder(self, result: ClassificationResult) -> Optional[Path]:
        """Finds an existing folder matching the subcategory at ANY depth in the tree
        (e.g. pol/japan, pol/russia/putin, or a flat happy/ at the root).
        Preference order: a folder whose parent matches the classified category/board,
        then a root-level folder, then a unique match anywhere. Returns a path
        relative to target_dir, or None when there is no unambiguous match."""
        sub_lower = result.subcategory.strip().lower()
        candidates = [rel for rel in self._iter_existing_dirs() if rel.name.lower() == sub_lower]
        if not candidates:
            return None

        preferred_parents = set()
        if result.board:
            preferred_parents.add(result.board.strip("/").strip().lower())
        if result.primary_folder:
            preferred_parents.add(result.primary_folder.strip().lower())
        if result.primary_folder == "reaction images":
            preferred_parents.add(self.config.reaction_images_dir.strip().lower())

        parent_matches = [rel for rel in candidates
                          if len(rel.parts) > 1 and rel.parent.name.lower() in preferred_parents]
        if parent_matches:
            return min(parent_matches, key=lambda rel: (len(rel.parts), str(rel)))

        root_matches = [rel for rel in candidates if len(rel.parts) == 1]
        if root_matches:
            return root_matches[0]

        if len(candidates) == 1:
            return candidates[0]
        return None

    def determine_target_path(self, file_path: Path, result: ClassificationResult) -> Path:
        """Determines the target folder and file name based on LLM classification and config."""
        strict = self.config.strict_subfolders

        # 1. Base directory structure selection
        folder_path = None
        if strict and result.subcategory:
            # If strict subfolders is active, route into a matching existing folder at any depth
            located = self._locate_strict_subfolder(result)
            if located is not None:
                folder_path = self.target_dir / located

        if folder_path is None:
            if self.config.board_sorting and result.board:
                # e.g., /g/ -> we create a folder named "g"
                board_folder_name = result.board.strip("/")
                folder_path = self._resolve_child_dir(self.target_dir, board_folder_name)
                # If there's a subcategory inside the board
                if result.subcategory:
                    if (board_folder_name == "g" and result.primary_folder == "technology") or board_folder_name == "pol":
                        folder_path = self._resolve_child_dir(folder_path, result.subcategory)
            elif result.primary_folder == "reaction images":
                folder_path = self.target_dir / self.config.reaction_images_dir
                if result.subcategory:
                    folder_path = self._resolve_child_dir(folder_path, result.subcategory)
            else:
                # E.g. technology, gaming, anime, etc.
                folder_path = self._resolve_child_dir(self.target_dir, result.primary_folder)
                if result.subcategory:
                    folder_path = self._resolve_child_dir(folder_path, result.subcategory)

        # Strict mode must never create new directories: fall back to the deepest
        # existing ancestor, leaving unmatched files in the target root.
        if strict:
            while folder_path != self.target_dir and not folder_path.is_dir():
                folder_path = folder_path.parent

        # 2. Determine target filename
        original_ext = file_path.suffix.lower()
        if self.rename:
            base_name = result.suggested_filename
            # Clean base_name (just in case the LLM returned weird chars)
            base_name = "".join(c for c in base_name if c.isalnum() or c in ("-", "_")).strip().lower()
            # Remove 'meme' or 'memes' as standalone words (e.g. 'cat_meme' -> 'cat', 'meme_cat' -> 'cat')
            parts = re.split(r'([_-])', base_name)
            filtered_parts = [p for p in parts if p not in ('meme', 'memes')]
            cleaned = "".join(filtered_parts)
            # Standardise and collapse consecutive separators
            cleaned = re.sub(r'[_-]+', '_', cleaned)
            cleaned = cleaned.strip('_')
            if cleaned:
                base_name = cleaned
        else:
            base_name = file_path.stem

        if not base_name:
            base_name = "unnamed_meme"

        # 3. Handle collisions (e.g. happy_pepe.png already exists)
        target_file = folder_path / f"{base_name}{original_ext}"
        counter = 1
        
        # If we are doing a dry run, we must also simulate previous files that would be moved in this batch
        # But we'll just check what exists on disk for simplicity
        while target_file.exists():
            # If it's the exact same file (same path), don't treat it as a collision (it's already there)
            if target_file.resolve() == file_path.resolve():
                break
            target_file = folder_path / f"{base_name}_{counter}{original_ext}"
            counter += 1

        return target_file

    async def sort_files(self, files: List[Path], concurrency: int, progress_callback=None) -> Dict[str, Any]:
        """
        Sorts the list of files concurrently. 
        Calls progress_callback(file_path, success, details) after each file.
        """
        sem = asyncio.Semaphore(concurrency)
        loop = asyncio.get_running_loop()
        
        # We run the classifier in a ThreadPoolExecutor to prevent blocking the async loop
        executor = ThreadPoolExecutor(max_workers=concurrency)
        
        # Scan existing subfolders once at the start of sorting. In strict mode they are a
        # hard constraint; otherwise they steer the LLM toward reusing existing names.
        allowed_subs = self.discover_existing_subfolders()

        # In strict mode a subcategory is valid if a folder of that name exists anywhere
        # in the tree (routing later finds its actual location, e.g. pol/japan).
        existing_dir_names: Dict[str, str] = {}
        if self.config.strict_subfolders:
            for rel in self._iter_existing_dirs():
                existing_dir_names.setdefault(rel.name.lower(), rel.name)
        
        history_actions = []
        skipped_count = 0
        success_count = 0
        error_count = 0
        results_summary = []
        
        async def process_single_file(file_path: Path):
            nonlocal skipped_count, success_count, error_count
            async with sem:
                # 1. Compute Hash and check cache
                file_hash = get_file_hash(file_path)
                cached_res = None
                if file_hash and file_hash in self.cache:
                    try:
                        cached_res = ClassificationResult(**self.cache[file_hash])
                    except Exception:
                        pass # Ignore corrupted cache

                try:
                    if cached_res:
                        classification = cached_res
                    else:
                        # Call LLM in thread pool
                        classification = await loop.run_in_executor(
                            executor,
                            self.classifier.classify_image,
                            file_path,
                            allowed_subs,
                            self.config.strict_subfolders
                        )
                        # Save to cache
                        if file_hash and not self.dry_run:
                            self.cache[file_hash] = classification.model_dump()

                    # Drop subcategories that merely restate the category (e.g. pol/politics)
                    if self.is_redundant_subcategory(classification):
                        classification.subcategory = None

                    # Enforce strict subfolders if active: keep the subcategory only when a
                    # folder with that name exists somewhere in the tree (case-insensitive;
                    # snaps to the existing folder's exact name)
                    if self.config.strict_subfolders and classification.subcategory:
                        sub_lower = classification.subcategory.strip().lower()
                        classification.subcategory = existing_dir_names.get(sub_lower)

                    # Determine target location
                    target_path = self.determine_target_path(file_path, classification)
                    
                    # If target path is same as current path, no move is needed
                    if target_path.resolve() == file_path.resolve():
                        skipped_count += 1
                        info_str = f"Board: {classification.board or 'N/A'}, Category: {classification.primary_folder}/{classification.subcategory or ''}".rstrip('/')
                        results_summary.append({
                            "original_path": str(file_path),
                            "new_path": str(file_path),
                            "action": "skipped (already sorted)",
                            "explanation": info_str,
                            "board": classification.board,
                            "category": classification.primary_folder,
                            "commentary": getattr(classification, "commentary", None)
                        })
                        if progress_callback:
                            progress_callback(file_path, True, f"Skipped: {info_str}", classification, target_path)
                        return

                    # Execute move
                    action_detail = f"Moved to {target_path.relative_to(self.target_dir)}"
                    if not self.dry_run:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(file_path), str(target_path))
                        history_actions.append({
                            "original_path": str(file_path.resolve()),
                            "new_path": str(target_path.resolve())
                        })
                    
                    success_count += 1
                    info_str = f"Board: {classification.board or 'N/A'}, Category: {classification.primary_folder}/{classification.subcategory or ''}".rstrip('/')
                    results_summary.append({
                        "original_path": str(file_path),
                        "new_path": str(target_path),
                        "action": "moved" if not self.dry_run else "would move",
                        "explanation": info_str,
                        "board": classification.board,
                        "category": classification.primary_folder,
                        "commentary": getattr(classification, "commentary", None)
                    })
                    if progress_callback:
                        progress_callback(file_path, True, action_detail, classification, target_path)

                except Exception as e:
                    error_count += 1
                    results_summary.append({
                        "original_path": str(file_path),
                        "new_path": "",
                        "action": "error",
                        "explanation": str(e)
                    })
                    if progress_callback:
                        progress_callback(file_path, False, str(e), None, None)

        # Run tasks concurrently
        tasks = [process_single_file(f) for f in files]
        await asyncio.gather(*tasks)

        # Cleanup and Save
        executor.shutdown()
        self._save_cache()

        # Log to global history for undo operations
        if history_actions and not self.dry_run:
            self._write_history_entry(history_actions)

        return {
            "total": len(files),
            "success": success_count,
            "skipped": skipped_count,
            "error": error_count,
            "results": results_summary
        }

    def find_duplicates(self, files: Optional[List[Path]] = None) -> List[List[Path]]:
        """Groups images whose content hashes are identical. No LLM calls needed."""
        if files is None:
            files = self.scan_files(recursive=True)
        groups: Dict[str, List[Path]] = {}
        for f in files:
            file_hash = get_file_hash(f)
            if file_hash:
                groups.setdefault(file_hash, []).append(f)
        return [sorted(group) for group in groups.values() if len(group) > 1]

    def library_stats(self) -> Dict[str, Any]:
        """Analyzes the already-sorted library: per-folder counts and duplicate groups."""
        files = self.scan_files(recursive=True)
        folder_counts: Dict[str, int] = {}
        for f in files:
            rel = f.relative_to(self.target_dir)
            top = rel.parts[0] if len(rel.parts) > 1 else "(unsorted root)"
            folder_counts[top] = folder_counts.get(top, 0) + 1
        return {
            "total": len(files),
            "folder_counts": dict(sorted(folder_counts.items(), key=lambda kv: -kv[1])),
            "duplicate_groups": self.find_duplicates(files),
        }

    def _write_history_entry(self, actions: List[Dict[str, str]]):
        """Appends a new cleanup operation history entry to the global history file."""
        _, global_path = get_config_paths()
        history_path = global_path.parent / "history.json"
        
        history = []
        if history_path.exists():
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                pass
                
        # Append new entry
        history.append({
            "timestamp": datetime.now().isoformat(),
            "target_dir": str(self.target_dir),
            "actions": actions
        })
        
        # Keep only the last 10 operations to avoid bloating
        history = history[-10:]
        
        try:
            history_path.parent.mkdir(parents=True, exist_ok=True)
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=4)
        except Exception:
            pass

    @staticmethod
    def undo_last_operation() -> List[tuple[str, str]]:
        """
        Reverts the last sorted batch of files.
        Returns a list of tuples: (current_path, original_path) of reverted files.
        """
        _, global_path = get_config_paths()
        history_path = global_path.parent / "history.json"
        
        if not history_path.exists():
            raise FileNotFoundError("No operation history found. Cannot undo.")

        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            raise ValueError("History file is corrupted. Cannot undo.")

        if not history:
            raise ValueError("No sorting history recorded. Nothing to undo.")

        last_entry = history.pop() # Take the last operation
        actions = last_entry["actions"]
        reverted_files = []

        # Revert in reverse order to handle any dependency chains correctly
        for action in reversed(actions):
            current_path = Path(action["new_path"])
            original_path = Path(action["original_path"])
            
            if current_path.exists():
                # Ensure original parent folder exists
                original_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(current_path), str(original_path))
                reverted_files.append((str(current_path), str(original_path)))
                
                # Check if the folder we moved it out of is now empty, and delete it if it is
                # (but only if it's a subfolder under target_dir, not target_dir itself)
                parent_dir = current_path.parent
                target_dir = Path(last_entry["target_dir"])
                
                # Clean up empty parent directories up to target_dir
                while parent_dir != target_dir and parent_dir.is_dir() and not any(parent_dir.iterdir()):
                    try:
                        parent_dir.rmdir()
                        parent_dir = parent_dir.parent
                    except Exception:
                        break

        # Save remaining history
        try:
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=4)
        except Exception:
            pass

        return reverted_files
