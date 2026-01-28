from blocks_utils import PROMO_BLOCK, add_inline_image_block


def test_spacer_inserted_before_image_after_promo() -> None:
    content = PROMO_BLOCK + "\n\n<!-- wp:paragraph -->\n<p>Intro</p>\n<!-- /wp:paragraph -->\n"
    updated = add_inline_image_block(content, "https://example.com/image.jpg", "Alt text", spacer_height=24)
    promo_idx = updated.find(PROMO_BLOCK)
    spacer_idx = updated.find("<!-- wp:spacer", promo_idx)
    image_idx = updated.find("<!-- wp:image", promo_idx)
    assert spacer_idx != -1
    assert image_idx != -1
    assert spacer_idx < image_idx
