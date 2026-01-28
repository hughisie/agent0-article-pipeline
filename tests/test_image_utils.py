import unittest

from image_utils import extract_image_url_from_article, extract_image_urls_from_article


class TestImageUtils(unittest.TestCase):
    def test_extract_image_from_article_fields(self):
        article = {"image_url": "https://example.com/image.jpg"}
        self.assertEqual(extract_image_url_from_article(article), "https://example.com/image.jpg")

    def test_extract_images_from_list_field(self):
        article = {"image_urls": ["https://example.com/a.jpg", "https://example.com/b.jpg"]}
        self.assertEqual(
            extract_image_urls_from_article(article),
            ["https://example.com/a.jpg", "https://example.com/b.jpg"],
        )

    def test_extract_image_from_markdown(self):
        article = {}
        raw = "![Alt](https://example.com/pic.png)"
        self.assertEqual(extract_image_url_from_article(article, raw), "https://example.com/pic.png")

    def test_extract_images_from_markdown(self):
        article = {}
        raw = "![Alt](https://example.com/pic.png)\n![Alt2](https://example.com/pic2.png)"
        self.assertEqual(
            extract_image_urls_from_article(article, raw),
            ["https://example.com/pic.png", "https://example.com/pic2.png"],
        )


if __name__ == "__main__":
    unittest.main()
