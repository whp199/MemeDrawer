import unittest
import tempfile
import os
import shutil
from pathlib import Path
from PIL import Image

from memedrawer.config import AppConfig, save_config, load_config
from memedrawer.classifier import prepare_image, ClassificationResult
from memedrawer.sorter import SorterEngine, get_file_hash


class TestMemeDrawerConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.prev_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)

    def tearDown(self):
        os.chdir(self.prev_cwd)
        self.temp_dir.cleanup()

    def test_config_save_load(self):
        # Create custom configuration
        config = AppConfig(
            provider="openai",
            openai_model="custom-gemma",
            concurrency=2,
            rename_files=False
        )
        
        # Save as local configuration in the temp cwd
        save_config(config, local=True)
        
        # Verify local file exists
        local_path = Path(self.temp_dir.name) / "memedrawer_config.json"
        self.assertTrue(local_path.exists())
        
        # Load it back
        loaded = load_config()
        self.assertEqual(loaded.provider, "openai")
        self.assertEqual(loaded.openai_model, "custom-gemma")
        self.assertEqual(loaded.concurrency, 2)
        self.assertFalse(loaded.rename_files)


class TestImagePreprocessing(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.img_path = Path(self.temp_dir.name) / "test_large.png"
        
        # Create a large test image (1200x800)
        img = Image.new("RGB", (1200, 800), color="red")
        img.save(self.img_path, format="PNG")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_prepare_image(self):
        compressed_bytes, mime_type = prepare_image(self.img_path, max_size=800)
        
        # Verify output is valid JPEG or PNG bytes and smaller dimension
        self.assertEqual(mime_type, "image/jpeg")
        self.assertGreater(len(compressed_bytes), 0)
        
        # Load the bytes back with PIL to verify dimensions
        import io
        img = Image.open(io.BytesIO(compressed_bytes))
        width, height = img.size
        
        # Check aspect ratio was kept and max dimension is exactly 800
        self.assertEqual(width, 800)
        self.assertEqual(height, 533)


class TestSorterLogic(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.target_dir = Path(self.temp_dir.name)
        
        # Configuration setup
        self.config = AppConfig(
            board_sorting=True,
            reaction_images_dir="reaction images"
        )
        
        # Create engine
        self.engine = SorterEngine(self.target_dir, self.config, dry_run=False, rename=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_determine_target_path_board(self):
        # 1. Image fits a 4chan board (e.g. /g/ for technology)
        result = ClassificationResult(
            board="/g/",
            primary_folder="technology",
            subcategory="programming",
            suggested_filename="gemma_cpp_compiling"
        )
        
        file_path = self.target_dir / "rand_input.jpg"
        target = self.engine.determine_target_path(file_path, result)
        
        # Path should be target_dir / "g" / "programming" / "gemma_cpp_compiling.jpg"
        expected = self.target_dir / "g" / "programming" / "gemma_cpp_compiling.jpg"
        self.assertEqual(target.resolve(), expected.resolve())

    def test_determine_target_path_reaction(self):
        # 2. Image is a generic reaction face
        result = ClassificationResult(
            board=None,
            primary_folder="reaction images",
            subcategory="smug",
            suggested_filename="smug_maid_smile"
        )
        
        file_path = self.target_dir / "temp_reaction.png"
        target = self.engine.determine_target_path(file_path, result)
        
        # Path should be target_dir / "reaction images" / "smug" / "smug_maid_smile.png"
        expected = self.target_dir / "reaction images" / "smug" / "smug_maid_smile.png"
        self.assertEqual(target.resolve(), expected.resolve())

    def test_determine_target_path_collision(self):
        # 3. Handle naming collision
        result = ClassificationResult(
            board=None,
            primary_folder="gaming",
            subcategory=None,
            suggested_filename="dark_souls_death"
        )
        
        file_path = self.target_dir / "input_game.png"
        
        # Pre-create the target file and an extra suffix to test sequential renaming
        dest_folder = self.target_dir / "gaming"
        dest_folder.mkdir(parents=True, exist_ok=True)
        (dest_folder / "dark_souls_death.png").touch()
        (dest_folder / "dark_souls_death_1.png").touch()
        
        target = self.engine.determine_target_path(file_path, result)
        
        # Expected target should be dark_souls_death_2.png
        expected = dest_folder / "dark_souls_death_2.png"
        self.assertEqual(target.resolve(), expected.resolve())

    def test_determine_target_path_pol_subcategory(self):
        # Politics image with subcategory
        result = ClassificationResult(
            board="/pol/",
            primary_folder="politics",
            subcategory="trump",
            suggested_filename="trump_speech"
        )
        file_path = self.target_dir / "rand_pol.jpg"
        target = self.engine.determine_target_path(file_path, result)
        expected = self.target_dir / "pol" / "trump" / "trump_speech.jpg"
        self.assertEqual(target.resolve(), expected.resolve())

    def test_determine_target_path_art(self):
        # Works of fine art
        result = ClassificationResult(
            board="/art/",
            primary_folder="art",
            subcategory=None,
            suggested_filename="mona_lisa"
        )
        file_path = self.target_dir / "painting.png"
        target = self.engine.determine_target_path(file_path, result)
        expected = self.target_dir / "art" / "mona_lisa.png"
        self.assertEqual(target.resolve(), expected.resolve())

    def test_determine_target_path_tg(self):
        # Magic the gathering cards
        result = ClassificationResult(
            board="/tg/",
            primary_folder="tg",
            subcategory=None,
            suggested_filename="black_lotus"
        )
        file_path = self.target_dir / "card.jpg"
        target = self.engine.determine_target_path(file_path, result)
        expected = self.target_dir / "tg" / "black_lotus.jpg"
        self.assertEqual(target.resolve(), expected.resolve())

    def test_determine_target_path_no_rename(self):
        # When rename is False, it should preserve the exact filename stem
        self.engine.rename = False
        result = ClassificationResult(
            board="/g/",
            primary_folder="technology",
            subcategory="programming",
            suggested_filename="gemma_cpp_compiling"
        )
        file_path = self.target_dir / "My Awesome Image 2026.PNG"
        target = self.engine.determine_target_path(file_path, result)
        expected = self.target_dir / "g" / "programming" / "My Awesome Image 2026.png"
        self.assertEqual(target.resolve(), expected.resolve())
        self.engine.rename = True

    def test_determine_target_path_strip_meme(self):
        # Redundant 'meme' or 'memes' stripping from suggested filename
        result1 = ClassificationResult(
            board=None,
            primary_folder="gaming",
            subcategory=None,
            suggested_filename="funny_cat_meme"
        )
        target1 = self.engine.determine_target_path(self.target_dir / "input.jpg", result1)
        self.assertEqual(target1.name, "funny_cat.jpg")

        result2 = ClassificationResult(
            board=None,
            primary_folder="gaming",
            subcategory=None,
            suggested_filename="meme_doge_screaming"
        )
        target2 = self.engine.determine_target_path(self.target_dir / "input.jpg", result2)
        self.assertEqual(target2.name, "doge_screaming.jpg")

        result3 = ClassificationResult(
            board=None,
            primary_folder="gaming",
            subcategory=None,
            suggested_filename="cool_memes_face"
        )
        target3 = self.engine.determine_target_path(self.target_dir / "input.jpg", result3)
        self.assertEqual(target3.name, "cool_face.jpg")

        result4 = ClassificationResult(
            board=None,
            primary_folder="gaming",
            subcategory=None,
            suggested_filename="meme"
        )
        target4 = self.engine.determine_target_path(self.target_dir / "input.jpg", result4)
        self.assertEqual(target4.name, "meme.jpg")  # Should fallback to not strip if it leaves empty string



class TestSorterOperationsAndUndo(unittest.TestCase):
    def setUp(self):
        # We need a clean temp dir for testing actual file movements
        self.temp_dir = tempfile.TemporaryDirectory()
        self.target_dir = Path(self.temp_dir.name)
        
        # Ensure clean environment for history config
        self.prev_home = os.environ.get("HOME")
        os.environ["HOME"] = self.temp_dir.name
        
        # Create mock input files
        self.file1 = self.target_dir / "image1.jpg"
        self.file2 = self.target_dir / "image2.png"
        
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(self.file1, format="JPEG")
        img.save(self.file2, format="PNG")
        
        self.config = AppConfig(
            provider="openai",
            board_sorting=True,
            concurrency=1
        )
        self.engine = SorterEngine(self.target_dir, self.config, dry_run=False, rename=True)

    def tearDown(self):
        if self.prev_home:
            os.environ["HOME"] = self.prev_home
        self.temp_dir.cleanup()

    def test_sorting_and_undo(self):
        # Mock classify_image in SorterEngine
        class MockClassifier:
            def __init__(self):
                self.calls = 0
            def classify_image(self, file_path: Path, *args, **kwargs) -> ClassificationResult:
                self.calls += 1
                if file_path.suffix == ".jpg":
                    return ClassificationResult(
                        board="/g/",
                        primary_folder="technology",
                        subcategory="coding",
                        suggested_filename="g_board_meme",
                        commentary="Coding is fun, Master!"
                    )
                else:
                    return ClassificationResult(
                        board=None,
                        primary_folder="reaction images",
                        subcategory="happy",
                        suggested_filename="happy_reaction",
                        commentary="You look happy, Master!"
                    )

        self.engine.classifier = MockClassifier()
        
        # Run sorting
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        files = [self.file1, self.file2]
        summary = loop.run_until_complete(self.engine.sort_files(files, concurrency=1))
        
        # Verify counts
        self.assertEqual(summary["success"], 2)
        self.assertEqual(summary["error"], 0)
        
        # Verify file locations
        new_file1 = self.target_dir / "g" / "coding" / "g_board.jpg"
        new_file2 = self.target_dir / "reaction images" / "happy" / "happy_reaction.png"
        self.assertTrue(new_file1.exists())
        self.assertTrue(new_file2.exists())
        self.assertFalse(self.file1.exists())
        self.assertFalse(self.file2.exists())

        # Test Undo!
        reverted = SorterEngine.undo_last_operation()
        self.assertEqual(len(reverted), 2)
        
        # Verify files are back in original spot
        self.assertTrue(self.file1.exists())
        self.assertTrue(self.file2.exists())
        self.assertFalse(new_file1.exists())
        self.assertFalse(new_file2.exists())
        
        # Verify empty folders were cleaned up
        self.assertFalse((self.target_dir / "g" / "coding").exists())
        self.assertFalse((self.target_dir / "g").exists())
        self.assertFalse((self.target_dir / "reaction images" / "happy").exists())
        self.assertFalse((self.target_dir / "reaction images").exists())

    def test_discover_existing_subfolders(self):
        # Create some directories under target_dir
        (self.target_dir / "g" / "linux").mkdir(parents=True, exist_ok=True)
        (self.target_dir / "g" / "coding").mkdir(parents=True, exist_ok=True)
        (self.target_dir / "pol" / "trump").mkdir(parents=True, exist_ok=True)
        (self.target_dir / "anime").mkdir(parents=True, exist_ok=True)
        
        subs = self.engine.discover_existing_subfolders()
        self.assertEqual(subs.get("g"), ["coding", "linux"])
        self.assertEqual(subs.get("pol"), ["trump"])
        self.assertNotIn("anime", subs)

    def test_strict_subfolders_enforcement(self):
        self.engine.config.strict_subfolders = True
        
        # Only allow 'coding' under 'g' (e.g. create g/coding)
        (self.target_dir / "g" / "coding").mkdir(parents=True, exist_ok=True)
        
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        file1 = self.target_dir / "input_strict.png"
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(file1, format="PNG")
        
        class MockStrictClassifier:
            def classify_image(self, file_path, allowed_subs=None):
                return ClassificationResult(
                    board="/g/",
                    primary_folder="technology",
                    subcategory="linux",
                    suggested_filename="tux"
                )
        self.engine.classifier = MockStrictClassifier()
        
        # Run sorting
        loop.run_until_complete(self.engine.sort_files([file1], concurrency=1))
        
        # Verify tuxedo image went to target_dir / "g" / "tux.png" (root of board "g") instead of "g/linux"
        expected = self.target_dir / "g" / "tux.png"
        self.assertTrue(expected.exists())
        self.assertFalse((self.target_dir / "g" / "linux").exists())
        
        self.engine.config.strict_subfolders = False


class TestAnimationAndCommentary(unittest.TestCase):
    def test_maid_art_animation(self):
        from memedrawer.maid_art import get_mimi_speech
        # Verify calling animated pose does not crash and yields output
        panel1 = get_mimi_speech("Cleaning speech...", expression="cleaning")
        self.assertIsNotNone(panel1)
        
        # Verify commentary schema instantiation
        res = ClassificationResult(
            board=None,
            primary_folder="gaming",
            suggested_filename="gaming_time",
            commentary="Let's play, Master!"
        )
        self.assertEqual(res.commentary, "Let's play, Master!")

    def test_callback_receives_classification(self):
        # Verify that sorter engine passes classification result to progress callback
        temp_dir = tempfile.TemporaryDirectory()
        target_dir = Path(temp_dir.name)
        file1 = target_dir / "test_img.png"
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(file1, format="PNG")
        
        config = AppConfig(provider="openai")
        engine = SorterEngine(target_dir, config, dry_run=True, rename=True)
        
        callback_called = []
        def custom_callback(file_path, success, details, classification=None):
            callback_called.append((file_path, success, details, classification))
            
        class MockClassifier:
            def classify_image(self, file_path: Path, *args, **kwargs) -> ClassificationResult:
                return ClassificationResult(
                    board=None,
                    primary_folder="gaming",
                    subcategory=None,
                    suggested_filename="gaming_time",
                    commentary="Test comment"
                )
        engine.classifier = MockClassifier()
        
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        loop.run_until_complete(engine.sort_files([file1], concurrency=1, progress_callback=custom_callback))
        
        self.assertEqual(len(callback_called), 1)
        f_path, success, details, classification = callback_called[0]
        self.assertTrue(success)
        self.assertIsNotNone(classification)
        self.assertEqual(classification.commentary, "Test comment")
        
        temp_dir.cleanup()

    def test_determine_favorite_meme(self):
        from memedrawer.classifier import LLMClassifier
        config = AppConfig(provider="openai")
        classifier = LLMClassifier(config)
        
        # Mock get_text_completion
        classifier.get_text_completion = lambda prompt: "My favorite was funny_cat.png because it's adorable!"
        
        comments = [
            {"filename": "funny_cat.png", "commentary": "Cute kitten!"},
            {"filename": "pepe.jpg", "commentary": "Feels good man!"}
        ]
        
        fav = classifier.determine_favorite_meme(comments)
        self.assertEqual(fav, "My favorite was funny_cat.png because it's adorable!")
        
        # Test empty comments handling
        self.assertEqual(classifier.determine_favorite_meme([]), "")

    def test_robust_llm_json_parsing(self):
        from memedrawer.classifier import sanitize_llm_dict
        
        # Test mapping with varied keys and casing
        raw = {
            "PRIMARYfolder": "cooking",
            "FILENAME": "yummy_food",
            "Comment": "This looks delicious, Master!",
            "BoardCode": "/ck/",
            "Topic": "recipe"
        }
        
        sanitized = sanitize_llm_dict(raw)
        self.assertEqual(sanitized["primary_folder"], "cooking")
        self.assertEqual(sanitized["suggested_filename"], "yummy_food")
        self.assertEqual(sanitized["commentary"], "This looks delicious, Master!")
        self.assertEqual(sanitized["board"], "/ck/")
        self.assertEqual(sanitized["subcategory"], "recipe")
        
        # Test defaults for missing values
        empty_sanitized = sanitize_llm_dict({})
        self.assertEqual(empty_sanitized["primary_folder"], "miscellaneous")
        self.assertEqual(empty_sanitized["suggested_filename"], "unnamed_meme")
        self.assertIsNone(empty_sanitized["board"])
        self.assertIsNone(empty_sanitized["subcategory"])
        self.assertIsNone(empty_sanitized["commentary"])


if __name__ == "__main__":
    unittest.main()
