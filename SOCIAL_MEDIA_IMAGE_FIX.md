# Social Media Image Preview Bug Fix

## Problem
Twitter/X card previews are not showing images when articles are shared, despite the Python code uploading images correctly and passing the URLs to the Yoast sync endpoint.

## Root Cause
The Python code was only passing image **URLs** to the WordPress Yoast bridge plugin, but Yoast SEO requires the WordPress **attachment IDs** to properly set social media meta tags.

## Solution

### Part 1: Python Code Updates (COMPLETED)

#### Files Modified:

1. **`yoast_bridge_client.py`** (lines 14-50):
   - Added `opengraph_image_id` parameter
   - Added `twitter_image_id` parameter
   - These now get included in the payload sent to WordPress

2. **`main.py`** (lines 566-577, 1100-1112):
   - Updated both `yoast_sync_post()` calls to pass `media_id` as both:
     - `opengraph_image_id=media_id`
     - `twitter_image_id=media_id`

### Part 2: WordPress Plugin Updates (REQUIRED)

The WordPress Yoast bridge plugin at `/wp-json/barna/v1/yoast-sync` needs to be updated to handle the new attachment ID fields.

#### Required Changes to WordPress Plugin:

The plugin should now accept these additional fields in the POST payload:
```json
{
  "post_id": 12345,
  "focuskw": "terrace heaters",
  "title": "...",
  "metadesc": "...",
  "opengraph-image": "https://example.com/wp-content/uploads/2024/01/image.jpg",
  "twitter-image": "https://example.com/wp-content/uploads/2024/01/image.jpg",
  "opengraph-image-id": 67890,
  "twitter-image-id": 67890
}
```

#### WordPress Plugin Code to Add:

```php
// In the Yoast bridge plugin handler:

// Get the image IDs from the payload
$opengraph_image_id = isset($request['opengraph-image-id']) ? intval($request['opengraph-image-id']) : null;
$twitter_image_id = isset($request['twitter-image-id']) ? intval($request['twitter-image-id']) : null;

// Update Yoast meta fields with attachment IDs
if ($opengraph_image_id) {
    // Set OpenGraph image ID (this is what Yoast actually uses)
    update_post_meta($post_id, '_yoast_wpseo_opengraph-image-id', $opengraph_image_id);

    // Also set the URL for backwards compatibility
    if (isset($request['opengraph-image'])) {
        update_post_meta($post_id, '_yoast_wpseo_opengraph-image', $request['opengraph-image']);
    }
}

if ($twitter_image_id) {
    // Set Twitter card image ID (this is what Yoast actually uses)
    update_post_meta($post_id, '_yoast_wpseo_twitter-image-id', $twitter_image_id);

    // Also set the URL for backwards compatibility
    if (isset($request['twitter-image'])) {
        update_post_meta($post_id, '_yoast_wpseo_twitter-image', $request['twitter-image']);
    }
}

// Force Yoast to regenerate meta tags
do_action('wpseo_save_compare_data', $post_id);
```

#### Yoast SEO Meta Fields Reference:

Yoast SEO uses these WordPress post meta fields:
- `_yoast_wpseo_opengraph-image-id` - OpenGraph image attachment ID (PRIMARY)
- `_yoast_wpseo_opengraph-image` - OpenGraph image URL (fallback)
- `_yoast_wpseo_twitter-image-id` - Twitter card image attachment ID (PRIMARY)
- `_yoast_wpseo_twitter-image` - Twitter card image URL (fallback)

**Important**: Yoast prioritizes the `-id` fields over the URL fields when generating meta tags.

## Testing

### Before Testing:
1. Deploy the updated WordPress plugin code
2. Restart the Python server (changes already deployed)

### Test Procedure:
1. Process a new article with an image
2. Check the console logs for output like:
   ```
   Setting OpenGraph image ID: 67890
   Setting Twitter card image ID: 67890
   ```
3. Check the WordPress post meta in the database:
   ```sql
   SELECT meta_key, meta_value
   FROM wp_postmeta
   WHERE post_id = [POST_ID]
   AND meta_key LIKE '%yoast_wpseo%image%';
   ```
4. View the article's HTML source and verify meta tags:
   ```html
   <meta property="og:image" content="https://..." />
   <meta name="twitter:image" content="https://..." />
   ```
5. Test with Twitter Card Validator:
   - Go to https://cards-dev.twitter.com/validator
   - Enter the article URL
   - Verify the image preview appears

## Expected Results

### Before Fix:
- ❌ Twitter/X card shows no image
- ❌ `_yoast_wpseo_opengraph-image-id` not set
- ❌ `_yoast_wpseo_twitter-image-id` not set
- ⚠️ Only URL fields set (which Yoast ignores)

### After Fix:
- ✅ Twitter/X card shows the featured image
- ✅ `_yoast_wpseo_opengraph-image-id` contains attachment ID
- ✅ `_yoast_wpseo_twitter-image-id` contains attachment ID
- ✅ Both URL and ID fields properly set
- ✅ Meta tags appear correctly in HTML

## Deployment Status

- ✅ **Python Code**: Updated and ready to deploy
- ⏳ **WordPress Plugin**: Awaiting update (see Part 2 above)

## Notes

- The Python code converts AVIF/WebP images to JPG for better social media compatibility (wordpress_client.py:236-264)
- If WordPress still saves as .avif, a warning is logged (line 299)
- The `media_id` returned from `upload_media_from_url()` is the WordPress attachment ID needed for Yoast
- Both OpenGraph and Twitter use the same attachment ID since they're the same image

## Reference Links

- [Yoast SEO Meta Field Documentation](https://developer.yoast.com/customization/apis/metadata-api/)
- [Twitter Card Validator](https://cards-dev.twitter.com/validator)
- [OpenGraph Protocol](https://ogp.me/)
