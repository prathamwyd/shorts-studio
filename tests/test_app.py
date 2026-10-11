import unittest
from app import make_storyboard, safe_project_title, clean_text

class StoryboardTests(unittest.TestCase):
    def test_storyboard_has_expected_number_of_scenes_and_duration(self):
        result = make_storyboard("A dragon finds a lost city", "story", 30)
        self.assertEqual(result["aspect_ratio"], "9:16")
        self.assertEqual(len(result["scenes"]), 4)
        self.assertEqual(sum(scene["duration"] for scene in result["scenes"]), 30)

    def test_all_supported_styles_work(self):
        for style in ("pov", "story", "cartoon", "satisfying", "cinematic"):
            with self.subTest(style=style):
                self.assertEqual(make_storyboard("A tiny robot", style, 15)["style"], style)

    def test_invalid_prompt_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "video idea"):
            make_storyboard("   ", "story", 30)

    def test_invalid_style_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "supported"):
            make_storyboard("A tiny robot", "unknown", 30)

    def test_invalid_duration_is_rejected(self):
        for duration in (9, 61, True, 15.5):
            with self.subTest(duration=duration):
                with self.assertRaises(ValueError):
                    make_storyboard("A tiny robot", "story", duration)

    def test_prompt_length_is_bounded(self):
        result = make_storyboard("x" * 900, "story", 30)
        self.assertLessEqual(len(result["title"]), 68)

    def test_filename_is_sanitized(self):
        self.assertEqual(safe_project_title("../../My Video!!"), "My-Video")

    def test_text_normalization(self):
        self.assertEqual(clean_text("  hello\n   world "), "hello world")

if __name__ == "__main__":
    unittest.main()
