# Step-by-Step: Fix Social Media Images in WordPress

## Overview
You need to update your WordPress Yoast bridge plugin to accept attachment IDs from the Python app. This will fix Twitter/X card previews not showing images.

---

## Step 1: Locate Your WordPress Plugin

1. **Log into your WordPress server via SSH or FTP**

2. **Navigate to the plugins directory:**
   ```bash
   cd /path/to/wordpress/wp-content/plugins/
   ```

3. **Find the Barna Yoast Bridge plugin:**
   ```bash
   ls -la
   # Look for a folder like "barna-yoast-bridge" or similar
   ```

4. **If you can't find it**, search for the endpoint registration:
   ```bash
   grep -r "barna/v1/yoast-sync" /path/to/wordpress/wp-content/
   ```

**Common locations:**
- `/wp-content/plugins/barna-yoast-bridge/`
- `/wp-content/themes/[your-theme]/functions.php` (if it's in theme)
- `/wp-content/mu-plugins/` (must-use plugins)

---

## Step 2: Find the Yoast Sync Endpoint Handler

Look for code that looks like this:

```php
register_rest_route('barna/v1', '/yoast-sync', array(
    'methods' => 'POST',
    'callback' => 'some_function_name',
    // ...
));
```

Or search for it:
```bash
grep -r "yoast-sync" /path/to/wordpress/wp-content/plugins/your-plugin/
```

---

## Step 3: Backup the Plugin File

**CRITICAL: Always backup before editing!**

```bash
# Example if the file is barna-yoast-bridge.php
cp barna-yoast-bridge.php barna-yoast-bridge.php.backup.$(date +%Y%m%d)
```

---

## Step 4: Edit the Plugin File

Open the file in your editor:

```bash
nano barna-yoast-bridge.php
# or
vim barna-yoast-bridge.php
# or use your preferred editor
```

---

## Step 5: Add the Image ID Handling Code

Find the function that handles the `/yoast-sync` endpoint. It will look something like:

```php
function handle_yoast_sync($request) {
    $post_id = $request['post_id'];
    $focuskw = $request['focuskw'];
    $title = $request['title'];
    $metadesc = $request['metadesc'];

    // Update existing Yoast meta fields
    update_post_meta($post_id, '_yoast_wpseo_focuskw', $focuskw);
    update_post_meta($post_id, '_yoast_wpseo_title', $title);
    update_post_meta($post_id, '_yoast_wpseo_metadesc', $metadesc);

    // Maybe some more code here...
}
```

**Add this code BEFORE the return statement (usually at the end):**

```php
    // Handle OpenGraph image
    if (isset($request['opengraph-image-id']) && !empty($request['opengraph-image-id'])) {
        $opengraph_image_id = intval($request['opengraph-image-id']);
        update_post_meta($post_id, '_yoast_wpseo_opengraph-image-id', $opengraph_image_id);

        // Also update the URL if provided
        if (isset($request['opengraph-image']) && !empty($request['opengraph-image'])) {
            update_post_meta($post_id, '_yoast_wpseo_opengraph-image', sanitize_url($request['opengraph-image']));
        }
    }

    // Handle Twitter card image
    if (isset($request['twitter-image-id']) && !empty($request['twitter-image-id'])) {
        $twitter_image_id = intval($request['twitter-image-id']);
        update_post_meta($post_id, '_yoast_wpseo_twitter-image-id', $twitter_image_id);

        // Also update the URL if provided
        if (isset($request['twitter-image']) && !empty($request['twitter-image'])) {
            update_post_meta($post_id, '_yoast_wpseo_twitter-image', sanitize_url($request['twitter-image']));
        }
    }
```

**Complete example of what it should look like:**

```php
function handle_yoast_sync($request) {
    $post_id = $request['post_id'];
    $focuskw = $request['focuskw'];
    $title = $request['title'];
    $metadesc = $request['metadesc'];

    // Update existing Yoast meta fields
    update_post_meta($post_id, '_yoast_wpseo_focuskw', $focuskw);
    update_post_meta($post_id, '_yoast_wpseo_title', $title);
    update_post_meta($post_id, '_yoast_wpseo_metadesc', $metadesc);

    // NEW CODE: Handle OpenGraph image
    if (isset($request['opengraph-image-id']) && !empty($request['opengraph-image-id'])) {
        $opengraph_image_id = intval($request['opengraph-image-id']);
        update_post_meta($post_id, '_yoast_wpseo_opengraph-image-id', $opengraph_image_id);

        if (isset($request['opengraph-image']) && !empty($request['opengraph-image'])) {
            update_post_meta($post_id, '_yoast_wpseo_opengraph-image', sanitize_url($request['opengraph-image']));
        }
    }

    // NEW CODE: Handle Twitter card image
    if (isset($request['twitter-image-id']) && !empty($request['twitter-image-id'])) {
        $twitter_image_id = intval($request['twitter-image-id']);
        update_post_meta($post_id, '_yoast_wpseo_twitter-image-id', $twitter_image_id);

        if (isset($request['twitter-image']) && !empty($request['twitter-image'])) {
            update_post_meta($post_id, '_yoast_wpseo_twitter-image', sanitize_url($request['twitter-image']));
        }
    }

    return array('success' => true, 'post_id' => $post_id);
}
```

---

## Step 6: Save and Upload the File

**If editing locally (via FTP/SFTP):**
1. Save the file
2. Upload it back to the server
3. Overwrite the old file

**If editing on server (via SSH):**
1. Save the file (`:wq` in vim, `Ctrl+X` then `Y` in nano)

---

## Step 7: Clear WordPress Caches

```bash
# If using WP-CLI
wp cache flush

# Or via WordPress admin:
# Go to your caching plugin and click "Clear Cache"
# Common plugins: WP Super Cache, W3 Total Cache, etc.
```

**Or via WordPress admin dashboard:**
1. Go to your caching plugin settings
2. Click "Clear Cache" or "Purge All Caches"

---

## Step 8: Test the Fix

### A. Process a Test Article

From your Python app directory:

```bash
cd /Users/m4owen/01.\ Apps/13.\ CodeX/04.\ Extract\'n\'Source\'n\'Write\'n\'Enhance\'n\'publish

# Process a test article (adjust the path to your test file)
python3 main.py output/test-article.json
```

### B. Check the Python Logs

Look for these lines in the output:

```
Uploaded featured image (media ID 67890, URL: https://...)
Setting OpenGraph image: https://...
Setting OpenGraph image ID: 67890
Setting Twitter card image: https://...
Setting Twitter card image ID: 67890
Yoast sync payload: {...}
Yoast sync succeeded: {...}
```

If you see the image ID lines, Python is sending the data correctly! ✅

### C. Verify WordPress Database

**Option 1: Via WP-CLI**
```bash
wp db query "SELECT meta_key, meta_value FROM wp_postmeta WHERE post_id = YOUR_POST_ID AND meta_key LIKE '%yoast_wpseo%image%'"
```

**Option 2: Via phpMyAdmin**
1. Open phpMyAdmin
2. Select your WordPress database
3. Run this query (replace `12345` with your post ID):

```sql
SELECT meta_key, meta_value
FROM wp_postmeta
WHERE post_id = 12345
AND meta_key LIKE '%yoast_wpseo%image%'
ORDER BY meta_key;
```

**You should see:**
```
_yoast_wpseo_opengraph-image       | https://example.com/.../image.jpg
_yoast_wpseo_opengraph-image-id    | 67890
_yoast_wpseo_twitter-image         | https://example.com/.../image.jpg
_yoast_wpseo_twitter-image-id      | 67890
```

✅ If you see both the URL AND the ID fields, it's working!

### D. Check the Article HTML Source

1. Visit your article in a browser
2. View Page Source (Right-click → "View Page Source")
3. Search for `og:image` (Ctrl/Cmd+F)

**You should see:**
```html
<meta property="og:image" content="https://example.com/wp-content/uploads/2024/01/image.jpg" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
<meta name="twitter:image" content="https://example.com/wp-content/uploads/2024/01/image.jpg" />
<meta name="twitter:card" content="summary_large_image" />
```

✅ If you see these meta tags with real image URLs, Yoast is generating them correctly!

### E. Test with Twitter Card Validator

1. Go to https://cards-dev.twitter.com/validator
2. Enter your article URL
3. Click "Preview card"

**Expected result:** You should see the image preview! 🎉

---

## Step 9: Test on Twitter/X

1. **Copy your article URL**
2. **Open Twitter/X** (x.com)
3. **Paste the URL** into a new post
4. **Wait 2-3 seconds** for the preview to load

**You should see:**
- ✅ Article title
- ✅ Article description
- ✅ **Featured image preview** ← This was broken before!

---

## Troubleshooting

### Problem: Python logs don't show "Setting OpenGraph image ID"

**Solution:** The Python server needs to be restarted (it already was in our case).

```bash
ps aux | grep uvicorn
# Find the process ID
kill [PID]
# Start it again
cd /Users/m4owen/01.\ Apps/13.\ CodeX/04.\ Extract\'n\'Source\'n\'Write\'n\'Enhance\'n\'publish
uvicorn agent0_gui.app:app --host 0.0.0.0 --port 9000 --reload
```

### Problem: Database shows only URL fields, not ID fields

**Solution:** The WordPress plugin wasn't updated correctly. Double-check Step 5.

### Problem: Meta tags don't appear in HTML

**Solution:**
1. Clear WordPress cache
2. Try viewing in incognito/private mode
3. Check if Yoast SEO plugin is active: `wp plugin list` or check WordPress admin

### Problem: Twitter still doesn't show preview

**Solutions:**
1. **Clear Twitter's cache:** Add `?v=2` to the end of your URL and try again
2. **Wait 5-10 minutes** - Twitter caches card data
3. **Check image format:** Make sure image is JPG (Python converts it, but verify)
4. **Check image size:** Twitter requires at least 300x157px
5. **Use absolute URLs:** Make sure `WP_BASE_URL` in config doesn't have trailing slash

### Problem: "Failed to fetch card" in Twitter validator

**Solutions:**
1. Make sure article is published (not draft)
2. Make sure site is publicly accessible (not localhost)
3. Check robots.txt isn't blocking Twitter bot
4. Verify SSL certificate is valid if using HTTPS

---

## Quick Reference: Yoast Meta Fields

WordPress post meta fields used by Yoast SEO for social images:

| Field Name | Type | Purpose |
|------------|------|---------|
| `_yoast_wpseo_opengraph-image` | URL | OpenGraph image URL (fallback) |
| `_yoast_wpseo_opengraph-image-id` | Integer | OpenGraph image attachment ID (PRIMARY) |
| `_yoast_wpseo_twitter-image` | URL | Twitter card image URL (fallback) |
| `_yoast_wpseo_twitter-image-id` | Integer | Twitter card image attachment ID (PRIMARY) |

Yoast **prioritizes the `-id` fields** when generating meta tags.

---

## Success Checklist

- [ ] Found and backed up WordPress plugin file
- [ ] Added image ID handling code
- [ ] Cleared WordPress cache
- [ ] Processed a test article
- [ ] Verified Python logs show image IDs
- [ ] Verified database has both URL and ID fields
- [ ] Verified HTML source has og:image meta tags
- [ ] Twitter Card Validator shows image preview
- [ ] Actual Twitter/X post shows image preview

Once all items are checked, the bug is fixed! 🎉

---

## Need Help?

If you get stuck:

1. **Check Python logs:** Look for errors or missing image ID messages
2. **Check WordPress debug log:** Enable `WP_DEBUG` in `wp-config.php`
3. **Check plugin file syntax:** Use `php -l barna-yoast-bridge.php` to check for syntax errors
4. **Verify plugin is active:** In WordPress admin → Plugins

---

## File Locations Reference

- **Python code (already updated):**
  - `yoast_bridge_client.py` - Lines 14-50
  - `main.py` - Lines 566-578, 1100-1112

- **WordPress plugin (needs update):**
  - `/wp-content/plugins/barna-yoast-bridge/` (or similar)
  - Look for the file handling `/wp-json/barna/v1/yoast-sync`

- **Documentation:**
  - `SOCIAL_MEDIA_IMAGE_FIX.md` - Technical details
  - `SOCIAL_MEDIA_IMAGE_BUG_FIX_SUMMARY.md` - Summary
  - `WORDPRESS_PLUGIN_UPDATE_STEPS.md` - This file
