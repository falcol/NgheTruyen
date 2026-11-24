import unittest

from bs4 import BeautifulSoup

from crawler.shuba69 import Shuba69Crawler


class Shuba69Tests(unittest.TestCase):
    def test_extracts_chapter_without_ads(self):
        soup = BeautifulSoup(
            '<div class="txtnav"><h1>第1章 标题</h1><div class="txtinfo">日期</div>'
            '第1章 标题<br>' + '正文内容' * 30 + '<div class="contentadv">广告</div>'
            '<br>（全文完）<br>(本章完)</div>', "html.parser"
        )
        chapter = Shuba69Crawler()._extract_chapter(soup)
        self.assertEqual(chapter["title"], "第1章 标题")
        self.assertEqual(chapter["paragraphs"], ["正文内容" * 30, "（全文完）"])

    def test_catalog_orders_numbered_chapters_and_skips_notices(self):
        crawler = Shuba69Crawler()
        crawler.fetch = lambda url: BeautifulSoup(
            '<div id="catalog"><h1>书名最新章节</h1>'
            '<a href="/txt/42/2">第2章 第二</a>'
            '<a href="/txt/42/3">完本感言</a>'
            '<a href="/txt/42/1">第1章 第一</a></div>', "html.parser"
        )
        self.assertEqual(crawler._predict_urls("https://www.69shuba.com/book/42/", 0, 0), [
            (0, "https://www.69shuba.com/txt/42/1"),
            (1, "https://www.69shuba.com/txt/42/2"),
        ])
        self.assertEqual(crawler._story_title, "书名")


if __name__ == "__main__":
    unittest.main()
