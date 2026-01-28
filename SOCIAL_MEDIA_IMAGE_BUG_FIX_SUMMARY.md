# Social Media Image Bug - Quick Summary

## ✅ Problem Diagnosed

**Issue**: Twitter/X card previews not showing images when articles are shared.

**Root Cause**: The Python code was only passing image **URLs** to WordPress, but Yoast SEO requires WordPress **attachment IDs** to properly generate social media meta tags.

## ✅ Python Code Fixed (Deployed)

### Files Modified:

1. **`yoast_bridge_client.py`** (lines 14-50)
   - Added `opengraph_image_id` parameter
   - Added `twitter_image_id` parameter
   - Added debug logging for image IDs

2. **`main.py`** (lines 566-578, 1100-1112)
   - Updated both `yoast_sync_post()` calls to pass `media_id`
   - Passes the same media_id for both OpenGraph and Twitter images

### Server Status:
- ✅ **Restarted**: Server running on port 9000
- ✅ **Changes Applied**: New code is active
- ✅ **Health Check**: Passed

## ⏳ WordPress Plugin Update Required

The WordPress Yoast bridge plugin (`/wp-json/barna/v1/yoast-sync`) needs to be updated to handle the new attachment ID fields.

### What the Plugin Needs to Do:

The plugin must now accept these additional fields:
```json
{
  "opengraph-image-id": 67890,
  "twitter-image-id": 67890
}
```

And set these WordPress post meta fields:
```php
update_post_meta($post_id, '_yoast_wpseo_opengraph-image-id', $opengraph_image_id);
update_post_meta($post_id, '_yoast_wpseo_twitter-image-id', $twitter_image_id);
```

**See `SOCIAL_MEDIA_IMAGE_FIX.md` for complete WordPress plugin code.**

## 🧪 Testing (After WordPress Plugin Update)

1. **Process a new article** with an image
2. **Check console logs** for:
   ```
   Setting OpenGraph image ID: 67890
   Setting Twitter card image ID: 67890
   Yoast sync payload: {...}
   ```
3. **Verify WordPress meta fields**:
   ```sql
   SELECT meta_key, meta_value
   FROM wp_postmeta
   WHERE post_id = [POST_ID]
   AND meta_key LIKE '%yoast_wpseo%image%';
   ```
   Should show both `-id` and URL fields populated.

4. **Test with Twitter Card Validator**:
   - https://cards-dev.twitter.com/validator
   - Enter article URL
   - Verify image preview appears

## 📊 Expected Results

### Before Fix:
- ❌ No image in Twitter/X preview
- ❌ Only `_yoast_wpseo_opengraph-image` (URL) set
- ❌ Yoast couldn't find the image

### After Fix:
- ✅ Image appears in Twitter/X preview
- ✅ `_yoast_wpseo_opengraph-image-id` (attachment ID) set
- ✅ `_yoast_wpseo_twitter-image-id` (attachment ID) set
- ✅ Yoast generates proper meta tags

## 📝 Next Steps

1. **Update WordPress Yoast bridge plugin** with code from `SOCIAL_MEDIA_IMAGE_FIX.md`
2. **Test with a new article**
3. **Verify Twitter/X preview works**
4. **Optionally re-sync old articles** to add social images

## 🔍 How It Works Now

```
Python Code Flow:
1. upload_media_from_url() → returns (media_id, source_url)
2. yoast_sync_post() → sends BOTH:
   - opengraph-image: "https://..." (URL)
   - opengraph-image-id: 67890 (attachment ID)
   - twitter-image: "https://..." (URL)
   - twitter-image-id: 67890 (attachment ID)

WordPress Plugin (TO BE UPDATED):
3. Receives payload with image IDs
4. Sets Yoast meta fields:
   - _yoast_wpseo_opengraph-image-id
   - _yoast_wpseo_twitter-image-id
5. Yoast generates meta tags using attachment IDs

Result:
6. Twitter/X sees proper og:image and twitter:image tags
7. Image preview works!
```

## 📚 Documentation Files

- `SOCIAL_MEDIA_IMAGE_FIX.md` - Complete technical documentation
- `SOCIAL_MEDIA_IMAGE_BUG_FIX_SUMMARY.md` - This summary

The Python bug is now fixed! Once the WordPress plugin is updated, social media image previews will work correctly. 🎉
