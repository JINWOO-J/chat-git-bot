import unittest
import sys
import os

# Add the parent directory to the path so we can import md_lint
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import md_lint

class TestMdLint(unittest.TestCase):
    def test_is_markdown_file(self):
        # Test with valid markdown file extensions
        self.assertTrue(md_lint.is_markdown_file("test.md"))
        self.assertTrue(md_lint.is_markdown_file("test.markdown"))
        self.assertTrue(md_lint.is_markdown_file("test.mdown"))
        self.assertTrue(md_lint.is_markdown_file("test.mkdn"))
        
        # Test with invalid file extensions
        self.assertFalse(md_lint.is_markdown_file("test.txt"))
        self.assertFalse(md_lint.is_markdown_file("test.py"))
        self.assertFalse(md_lint.is_markdown_file("test"))
        
        # Test with edge cases
        self.assertTrue(md_lint.is_markdown_file("test.MD"))  # Uppercase
        self.assertTrue(md_lint.is_markdown_file("test.Markdown"))  # Mixed case

    def test_check_file_trailing_space(self):
        # Test file with trailing spaces
        file_path = os.path.join(os.path.dirname(__file__), 'test_files', 'trailing_space.md')
        issues = md_lint.check_file(file_path, 120, False)
        # Find the issue related to trailing space
        trailing_space_issues = [issue for issue in issues if issue.code == "W-TRAIL"]
        self.assertEqual(len(trailing_space_issues), 1)
        self.assertIn("트레일링 공백", trailing_space_issues[0].message)
        
    def test_check_file_long_line(self):
        # Test file with a long line
        file_path = os.path.join(os.path.dirname(__file__), 'test_files', 'long_line.md')
        issues = md_lint.check_file(file_path, 120, False)
        # Find the issue related to line length
        long_line_issues = [issue for issue in issues if issue.code == "W-LINELEN"]
        self.assertEqual(len(long_line_issues), 1)
        self.assertIn("줄 길이", long_line_issues[0].message)
        
    def test_check_file_tab_character(self):
        # Test file with a tab character
        file_path = os.path.join(os.path.dirname(__file__), 'test_files', 'tab_character.md')
        issues = md_lint.check_file(file_path, 120, False)
        # Find the issue related to tab character
        tab_issues = [issue for issue in issues if issue.code == "W-TAB"]
        self.assertEqual(len(tab_issues), 1)
        self.assertIn("탭 문자가 감지되었습니다", tab_issues[0].message)
        
    def test_check_file_heading_issues(self):
        # Test file with heading issues
        file_path = os.path.join(os.path.dirname(__file__), 'test_files', 'heading_issues.md')
        issues = md_lint.check_file(file_path, 120, False)
        
        # Check for heading space issue
        heading_space_issues = [issue for issue in issues if issue.code == "E-HEADSPACE"]
        self.assertGreaterEqual(len(heading_space_issues), 2) # At least two headings with space issues
        
        # Check for multiple H1 issue
        multi_h1_issues = [issue for issue in issues if issue.code == "W-MULTIH1"]
        self.assertEqual(len(multi_h1_issues), 1)
        self.assertIn("H1 헤딩이 2개 이상입니다", multi_h1_issues[0].message)

if __name__ == '__main__':
    unittest.main()