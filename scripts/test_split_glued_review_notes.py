"""split_glued_review_notes 的拆分与清理规则测试（不联网）。"""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import split_glued_review_notes as s  # noqa: E402


class SplitRules(unittest.TestCase):
    def test_splits_on_roman_two_and_cleans_artifacts(self):
        got, split = s.split_excerpt("上课有点催眠。Ⅱ水水水ⅡI 老师挺好，课讲的不太清楚。Ⅱ水中贵族，选他 游泳健将Ⅱ自学口Ⅱ")
        self.assertTrue(split)
        self.assertEqual(got, ["上课有点催眠。", "水水水", "老师挺好，课讲的不太清楚。", "水中贵族，选他游泳健将", "自学"])

    def test_drops_fragments_shorter_than_two_chars(self):
        got, split = s.split_excerpt("好Ⅱ很好的老师")
        self.assertTrue(split)
        self.assertEqual(got, ["很好的老师"])

    def test_plain_excerpt_keeps_id_and_only_loses_pdf_gaps(self):
        got, split = s.split_excerpt("给分 很高 Python 作业多")
        self.assertFalse(split)
        self.assertEqual(got, ["给分很高 Python 作业多"])

    def test_latin_spaces_are_kept(self):
        self.assertEqual(s.clean_text("作业 8587 分 OK"), "作业 8587 分 OK")


if __name__ == "__main__":
    unittest.main()
