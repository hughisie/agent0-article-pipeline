# Upload Instructions - Fix Social Media Images

## ✅ File to Upload

**Upload this file:**
```
/Users/m4owen/01. Apps/13. CodeX/04. Extract'n'Source'n'Write'n'Enhance'n'publish/Yoast WP Files/barna-yoast-bridge.php
```

**To this location on your WordPress server:**
```
/wp-content/plugins/barna-yoast-bridge/barna-yoast-bridge.php
```
(Or wherever your plugin is installed - could be in `/wp-content/mu-plugins/`)

---

## 📋 Step-by-Step Upload

### Option A: Via FTP/SFTP (Recommended)

1. **Open your FTP/SFTP client** (FileZilla, Cyberduck, etc.)

2. **Connect to your WordPress server**

3. **Navigate to:** `/wp-content/plugins/barna-yoast-bridge/`
   (Or search for the folder containing `barna-yoast-bridge.php`)

4. **Backup the old file first:**
   - Download the current `barna-yoast-bridge.php` to your computer
   - Rename it to `barna-yoast-bridge.php.backup`

5. **Upload the new file:**
   - Upload the updated file from:
     `/Users/m4owen/01. Apps/13. CodeX/04. Extract'n'Source'n'Write'n'Enhance'n'publish/Yoast WP Files/barna-yoast-bridge.php`
   - Overwrite the existing file

6. **Verify file permissions:** Should be `644` or `-rw-r--r--`

### Option B: Via SSH/Terminal

```bash
# 1. Connect to your server
ssh your-username@your-server.com

# 2. Navigate to the plugin directory
cd /path/to/wordpress/wp-content/plugins/barna-yoast-bridge/

# 3. Backup the current file
cp barna-yoast-bridge.php barna-yoast-bridge.php.backup.$(date +%Y%m%d)

# 4. Exit SSH and upload from your local machine
exit

# 5. Upload the new file (from your Mac)
scp "/Users/m4owen/01. Apps/13. CodeX/04. Extract'n'Source'n'Write'n'Enhance'n'publish/Yoast WP Files/barna-yoast-bridge.php" your-username@your-server.com:/path/to/wordpress/wp-content/plugins/barna-yoast-bridge/

# 6. Verify it worked
ssh your-username@your-server.com
grep -n "opengraph-image-id" /path/to/wordpress/wp-content/plugins/barna-yoast-bridge/barna-yoast-bridge.php
# Should show line numbers with the new code
```

### Option C: Via WordPress Admin (if using File Manager plugin)

1. Go to WordPress Admin → Plugins → File Manager (or similar)
2. Navigate to `/wp-content/plugins/barna-yoast-bridge/`
3. Download `barna-yoast-bridge.php` as backup
4. Delete or rename the old file
5. Upload the new file from your computer

---

## 🧪 Test After Upload

### 1. Process a Test Article

From your Mac terminal:

```bash
cd "/Users/m4owen/01. Apps/13. CodeX/04. Extract'n'Source'n'Write'n'Enhance'n'publish"

# Process any article with an image
python3 main.py path/to/your/test-article.json
```

### 2. Check Python Logs

Look for these lines (should appear now):
```
Uploaded featured image (media ID 67890, URL: https://...)
Setting OpenGraph image: https://...
Setting OpenGraph image ID: 67890  ← NEW!
Setting Twitter card image: https://...
Setting Twitter card image ID: 67890  ← NEW!
Yoast sync payload: {'post_id': ..., 'opengraph-image-id': 67890, ...}
Yoast sync succeeded: {'ok': True, 'stored_meta': {..., 'opengraph_image_id': '67890', ...}}
```

✅ **If you see the image ID lines, it's working!**

### 3. Check WordPress Database

**Via phpMyAdmin or wp-cli:**

```sql
SELECT meta_key, meta_value
FROM wp_postmeta
WHERE post_id = YOUR_POST_ID
AND meta_key LIKE '%yoast_wpseo%image%'
ORDER BY meta_key;
```

**Expected result:**
```
_yoast_wpseo_opengraph-image       | https://yoursite.com/.../image.jpg
_yoast_wpseo_opengraph-image-id    | 67890  ← NEW!
_yoast_wpseo_twitter-image         | https://yoursite.com/.../image.jpg
_yoast_wpseo_twitter-image-id      | 67890  ← NEW!
```

✅ **If you see the `-id` fields, it's working!**

### 4. View Page Source

1. Visit your article in a browser
2. Right-click → View Page Source
3. Search for `og:image` (Ctrl/Cmd+F)

**You should see:**
```html
<meta property="og:image" content="https://yoursite.com/.../image.jpg" />
<meta name="twitter:image" content="https://yoursite.com/.../image.jpg" />
```

✅ **If you see these meta tags, Yoast is generating them!**

### 5. Test Twitter Card Preview

1. Go to: https://cards-dev.twitter.com/validator
2. Enter your article URL
3. Click "Preview card"

✅ **You should see the image preview!** 🎉

### 6. Test on Real Twitter/X

1. Copy your article URL
2. Open Twitter/X (x.com)
3. Paste the URL in a new post
4. Wait 2-3 seconds

✅ **The image preview should appear!** 🎉

---

## 📝 What Changed in the File

The updated file now:

1. **Accepts image ID parameters** (lines 99-108):
   - `opengraph-image-id`
   - `twitter-image-id`

2. **Sets Yoast meta fields** (lines 207-246):
   - `_yoast_wpseo_opengraph-image-id` (PRIMARY - what Yoast uses)
   - `_yoast_wpseo_opengraph-image` (URL for fallback)
   - `_yoast_wpseo_twitter-image-id` (PRIMARY - what Yoast uses)
   - `_yoast_wpseo_twitter-image` (URL for fallback)

3. **Returns image values in response** (lines 313-317, 384-388):
   - Both sync and status endpoints now return image data

---

## ❓ Troubleshooting

### Python logs don't show image IDs

- Make sure Python server was restarted (it already was)
- Check the server is running: `curl http://localhost:9000/api/health`

### Database doesn't show image IDs

- Verify you uploaded the correct file
- Check file permissions: `ls -la barna-yoast-bridge.php` (should be 644)
- Clear WordPress cache
- Check for PHP errors: Enable `WP_DEBUG` in `wp-config.php`

### Twitter still doesn't show preview

- Clear Twitter's cache: Add `?v=2` to the URL
- Wait 5-10 minutes (Twitter caches card data)
- Make sure article is published (not draft)
- Verify image is JPG format (Python converts it automatically)

---

## ✅ Success Checklist

- [ ] Backed up old `barna-yoast-bridge.php` file
- [ ] Uploaded new `barna-yoast-bridge.php` file
- [ ] Verified file permissions (644)
- [ ] Processed a test article with image
- [ ] Python logs show "Setting OpenGraph image ID: XXXXX"
- [ ] Database has `_yoast_wpseo_opengraph-image-id` field
- [ ] HTML source has `<meta property="og:image" ...>` tag
- [ ] Twitter Card Validator shows image preview
- [ ] Real Twitter/X post shows image preview

Once all items are checked, the bug is fixed! 🎉

---

## 📞 Need Help?

If something goes wrong:

1. **Restore the backup:**
   ```bash
   cd /path/to/wordpress/wp-content/plugins/barna-yoast-bridge/
   cp barna-yoast-bridge.php.backup barna-yoast-bridge.php
   ```

2. **Check PHP syntax:**
   ```bash
   php -l barna-yoast-bridge.php
   ```

3. **Check WordPress error logs:**
   - Usually in `/wp-content/debug.log` (if `WP_DEBUG` is enabled)

4. **Verify plugin is active:**
   - WordPress Admin → Plugins
   - Or via CLI: `wp plugin list`

---

**That's it! Just upload the file and test.** 🚀
