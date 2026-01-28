<?php
/**
 * Plugin Name: Barna Yoast Bridge
 * Description: Custom REST endpoints to sync Yoast SEO meta and trigger indexable rebuilds
 * Version: 1.0.0
 * Author: Barna.News
 * 
 * This MU-plugin provides two REST endpoints:
 * - POST /wp-json/barna/v1/yoast-sync - Set Yoast meta and trigger indexable rebuild
 * - GET /wp-json/barna/v1/yoast-status - Verify Yoast meta values are stored
 */

if (!defined('ABSPATH')) {
    exit;
}

class Barna_Yoast_Bridge {
    
    /**
     * Yoast meta key mappings
     */
    private static $meta_keys = [
        'focuskw'      => '_yoast_wpseo_focuskw',
        'title'        => '_yoast_wpseo_title',
        'metadesc'     => '_yoast_wpseo_metadesc',
        'twitter_title' => '_yoast_wpseo_twitter-title',
        'twitter_desc'  => '_yoast_wpseo_twitter-description',
        'og_title'      => '_yoast_wpseo_opengraph-title',
        'og_desc'       => '_yoast_wpseo_opengraph-description',
    ];
    
    /**
     * Initialize the plugin
     */
    public static function init() {
        add_action('rest_api_init', [__CLASS__, 'register_routes']);
    }
    
    /**
     * Register REST API routes
     */
    public static function register_routes() {
        // POST /wp-json/barna/v1/yoast-sync
        register_rest_route('barna/v1', '/yoast-sync', [
            'methods'             => 'POST',
            'callback'            => [__CLASS__, 'handle_yoast_sync'],
            'permission_callback' => [__CLASS__, 'check_permission'],
            'args'                => [
                'post_id' => [
                    'required'          => true,
                    'type'              => 'integer',
                    'sanitize_callback' => 'absint',
                ],
                'focuskw' => [
                    'required'          => true,
                    'type'              => 'string',
                    'sanitize_callback' => 'sanitize_text_field',
                ],
                'title' => [
                    'required'          => true,
                    'type'              => 'string',
                    'sanitize_callback' => 'sanitize_text_field',
                ],
                'metadesc' => [
                    'required'          => true,
                    'type'              => 'string',
                    'sanitize_callback' => 'sanitize_text_field',
                ],
                'twitter_title' => [
                    'required'          => false,
                    'type'              => 'string',
                    'sanitize_callback' => 'sanitize_text_field',
                ],
                'twitter_desc' => [
                    'required'          => false,
                    'type'              => 'string',
                    'sanitize_callback' => 'sanitize_text_field',
                ],
                'og_title' => [
                    'required'          => false,
                    'type'              => 'string',
                    'sanitize_callback' => 'sanitize_text_field',
                ],
                'og_desc' => [
                    'required'          => false,
                    'type'              => 'string',
                    'sanitize_callback' => 'sanitize_text_field',
                ],
                'opengraph-image' => [
                    'required'          => false,
                    'type'              => 'string',
                    'sanitize_callback' => 'esc_url_raw',
                ],
                'twitter-image' => [
                    'required'          => false,
                    'type'              => 'string',
                    'sanitize_callback' => 'esc_url_raw',
                ],
                'opengraph-image-id' => [
                    'required'          => false,
                    'type'              => 'integer',
                    'sanitize_callback' => 'absint',
                ],
                'twitter-image-id' => [
                    'required'          => false,
                    'type'              => 'integer',
                    'sanitize_callback' => 'absint',
                ],
            ],
        ]);
        
        // GET /wp-json/barna/v1/yoast-status
        register_rest_route('barna/v1', '/yoast-status', [
            'methods'             => 'GET',
            'callback'            => [__CLASS__, 'handle_yoast_status'],
            'permission_callback' => [__CLASS__, 'check_permission'],
            'args'                => [
                'post_id' => [
                    'required'          => true,
                    'type'              => 'integer',
                    'sanitize_callback' => 'absint',
                ],
            ],
        ]);
    }
    
    /**
     * Check if user has permission to edit the post
     */
    public static function check_permission($request) {
        $post_id = $request->get_param('post_id');
        
        if (!is_user_logged_in()) {
            return new WP_Error('rest_forbidden', 'Authentication required', ['status' => 401]);
        }
        
        if ($post_id && !current_user_can('edit_post', $post_id)) {
            return new WP_Error('rest_forbidden', 'Cannot edit this post', ['status' => 403]);
        }
        
        return true;
    }
    
    /**
     * Handle POST /barna/v1/yoast-sync
     * Sets Yoast meta values and triggers indexable rebuild
     */
    public static function handle_yoast_sync($request) {
        $post_id = $request->get_param('post_id');
        $errors = [];
        $stored_meta = [];
        
        // Verify post exists
        $post = get_post($post_id);
        if (!$post) {
            return new WP_REST_Response([
                'ok'     => false,
                'errors' => ['Post not found'],
            ], 404);
        }
        
        // Step 1: Set Yoast meta values using the most reliable method
        $values_to_set = [
            'focuskw'      => $request->get_param('focuskw'),
            'title'        => $request->get_param('title'),
            'metadesc'     => $request->get_param('metadesc'),
            'twitter_title' => $request->get_param('twitter_title'),
            'twitter_desc'  => $request->get_param('twitter_desc'),
            'og_title'      => $request->get_param('og_title'),
            'og_desc'       => $request->get_param('og_desc'),
        ];
        
        foreach ($values_to_set as $key => $value) {
            if ($value === null || $value === '') {
                continue;
            }
            
            $meta_key = self::$meta_keys[$key] ?? null;
            if (!$meta_key) {
                continue;
            }
            
            // Try Yoast's WPSEO_Meta class first (preferred)
            $yoast_set = false;
            if (class_exists('WPSEO_Meta')) {
                // WPSEO_Meta::set_value expects the key without prefix
                $yoast_key = str_replace('_yoast_wpseo_', '', $meta_key);
                try {
                    WPSEO_Meta::set_value($yoast_key, $value, $post_id);
                    $yoast_set = true;
                } catch (Exception $e) {
                    $errors[] = "WPSEO_Meta error for {$key}: " . $e->getMessage();
                }
            }
            
            // Always also use update_post_meta as backup/confirmation
            $result = update_post_meta($post_id, $meta_key, $value);
            if ($result === false) {
                // Check if it's just unchanged (not an error)
                $existing = get_post_meta($post_id, $meta_key, true);
                if ($existing !== $value) {
                    $errors[] = "Failed to update {$meta_key}";
                }
            }
        }

        // Step 1.5: Handle social media image fields
        // OpenGraph image
        $og_image_url = $request->get_param('opengraph-image');
        $og_image_id = $request->get_param('opengraph-image-id');

        if (!empty($og_image_id)) {
            // Set the image ID (this is what Yoast uses)
            $result = update_post_meta($post_id, '_yoast_wpseo_opengraph-image-id', absint($og_image_id));
            if ($result === false) {
                $existing = get_post_meta($post_id, '_yoast_wpseo_opengraph-image-id', true);
                if ($existing != $og_image_id) {
                    $errors[] = "Failed to update OpenGraph image ID";
                }
            }

            // Also set the URL for backwards compatibility
            if (!empty($og_image_url)) {
                update_post_meta($post_id, '_yoast_wpseo_opengraph-image', esc_url_raw($og_image_url));
            }
        }

        // Twitter card image
        $twitter_image_url = $request->get_param('twitter-image');
        $twitter_image_id = $request->get_param('twitter-image-id');

        if (!empty($twitter_image_id)) {
            // Set the image ID (this is what Yoast uses)
            $result = update_post_meta($post_id, '_yoast_wpseo_twitter-image-id', absint($twitter_image_id));
            if ($result === false) {
                $existing = get_post_meta($post_id, '_yoast_wpseo_twitter-image-id', true);
                if ($existing != $twitter_image_id) {
                    $errors[] = "Failed to update Twitter image ID";
                }
            }

            // Also set the URL for backwards compatibility
            if (!empty($twitter_image_url)) {
                update_post_meta($post_id, '_yoast_wpseo_twitter-image', esc_url_raw($twitter_image_url));
            }
        }

        // Step 2: Trigger Yoast indexable rebuild
        $indexable_rebuilt = false;
        
        // Method A: Use Yoast's indexable repository if available (Yoast 14.0+)
        if (class_exists('Yoast\WP\SEO\Repositories\Indexable_Repository')) {
            try {
                $container = YoastSEO()->classes->get('Yoast\WP\SEO\Repositories\Indexable_Repository');
                if ($container) {
                    // Delete existing indexable to force rebuild
                    $indexable = $container->find_by_id_and_type($post_id, 'post');
                    if ($indexable) {
                        $indexable->delete();
                    }
                    // Rebuild
                    $container->find_by_id_and_type($post_id, 'post', false);
                    $indexable_rebuilt = true;
                }
            } catch (Exception $e) {
                $errors[] = "Indexable rebuild error: " . $e->getMessage();
            }
        }
        
        // Method B: Try Yoast's indexable builder directly
        if (!$indexable_rebuilt && class_exists('Yoast\WP\SEO\Builders\Indexable_Builder')) {
            try {
                $builder = YoastSEO()->classes->get('Yoast\WP\SEO\Builders\Indexable_Builder');
                $repository = YoastSEO()->classes->get('Yoast\WP\SEO\Repositories\Indexable_Repository');
                if ($builder && $repository) {
                    $indexable = $repository->find_by_id_and_type($post_id, 'post', false);
                    if ($indexable) {
                        $builder->build_for_id_and_type($post_id, 'post', $indexable);
                        $indexable->save();
                        $indexable_rebuilt = true;
                    }
                }
            } catch (Exception $e) {
                // Silent fail, try fallback
            }
        }
        
        // Method C: Fallback - clean cache and trigger save hooks
        if (!$indexable_rebuilt) {
            // Clean post cache
            clean_post_cache($post_id);
            
            // Trigger a minimal update to fire save_post hooks that Yoast listens to
            wp_update_post([
                'ID'            => $post_id,
                'post_modified' => current_time('mysql'),
                'post_modified_gmt' => current_time('mysql', true),
            ]);
            
            // Fire Yoast-specific action if available
            if (has_action('wpseo_saved_postdata')) {
                do_action('wpseo_saved_postdata');
            }
            
            $indexable_rebuilt = true; // Best effort
        }
        
        // Step 3: Read back stored values
        foreach (self::$meta_keys as $key => $meta_key) {
            $stored_meta[$key] = get_post_meta($post_id, $meta_key, true);
        }

        // Also read back image meta fields
        $stored_meta['opengraph_image'] = get_post_meta($post_id, '_yoast_wpseo_opengraph-image', true);
        $stored_meta['opengraph_image_id'] = get_post_meta($post_id, '_yoast_wpseo_opengraph-image-id', true);
        $stored_meta['twitter_image'] = get_post_meta($post_id, '_yoast_wpseo_twitter-image', true);
        $stored_meta['twitter_image_id'] = get_post_meta($post_id, '_yoast_wpseo_twitter-image-id', true);
        
        // Step 4: Try to get Yoast indexable values
        $yoast_indexable_values = [];
        $yoast_indexable_seen = false;
        
        if (class_exists('Yoast\WP\SEO\Repositories\Indexable_Repository')) {
            try {
                $repository = YoastSEO()->classes->get('Yoast\WP\SEO\Repositories\Indexable_Repository');
                $indexable = $repository->find_by_id_and_type($post_id, 'post');
                if ($indexable) {
                    $yoast_indexable_seen = true;
                    $yoast_indexable_values = [
                        'title'                  => $indexable->title,
                        'description'            => $indexable->description,
                        'primary_focus_keyword'  => $indexable->primary_focus_keyword,
                        'twitter_title'          => $indexable->twitter_title,
                        'twitter_description'    => $indexable->twitter_description,
                        'open_graph_title'       => $indexable->open_graph_title,
                        'open_graph_description' => $indexable->open_graph_description,
                    ];
                }
            } catch (Exception $e) {
                $errors[] = "Indexable read error: " . $e->getMessage();
            }
        }
        
        // Store sync timestamp
        update_post_meta($post_id, 'barna_yoast_last_sync', current_time('mysql'));
        
        // Determine success
        $ok = !empty($stored_meta['focuskw']) && 
              !empty($stored_meta['metadesc']) && 
              !empty($stored_meta['title']);
        
        return new WP_REST_Response([
            'ok'                   => $ok,
            'post_id'              => $post_id,
            'stored_meta'          => $stored_meta,
            'yoast_indexable_seen' => $yoast_indexable_seen,
            'yoast_values'         => $yoast_indexable_values,
            'errors'               => $errors,
        ], $ok ? 200 : 500);
    }
    
    /**
     * Handle GET /barna/v1/yoast-status
     * Verify Yoast meta values are stored and indexed
     */
    public static function handle_yoast_status($request) {
        $post_id = $request->get_param('post_id');
        
        // Verify post exists
        $post = get_post($post_id);
        if (!$post) {
            return new WP_REST_Response([
                'ok'     => false,
                'errors' => ['Post not found'],
            ], 404);
        }
        
        // Read stored postmeta values
        $stored_meta = [];
        foreach (self::$meta_keys as $key => $meta_key) {
            $stored_meta[$key] = get_post_meta($post_id, $meta_key, true);
        }

        // Also read image meta fields
        $stored_meta['opengraph_image'] = get_post_meta($post_id, '_yoast_wpseo_opengraph-image', true);
        $stored_meta['opengraph_image_id'] = get_post_meta($post_id, '_yoast_wpseo_opengraph-image-id', true);
        $stored_meta['twitter_image'] = get_post_meta($post_id, '_yoast_wpseo_twitter-image', true);
        $stored_meta['twitter_image_id'] = get_post_meta($post_id, '_yoast_wpseo_twitter-image-id', true);

        // Get last sync timestamp
        $last_sync = get_post_meta($post_id, 'barna_yoast_last_sync', true);
        
        // Try to read Yoast indexable
        $yoast_indexable_values = [];
        $yoast_indexable_seen = false;
        
        if (class_exists('Yoast\WP\SEO\Repositories\Indexable_Repository')) {
            try {
                $repository = YoastSEO()->classes->get('Yoast\WP\SEO\Repositories\Indexable_Repository');
                $indexable = $repository->find_by_id_and_type($post_id, 'post');
                if ($indexable) {
                    $yoast_indexable_seen = true;
                    $yoast_indexable_values = [
                        'title'                  => $indexable->title,
                        'description'            => $indexable->description,
                        'primary_focus_keyword'  => $indexable->primary_focus_keyword,
                        'twitter_title'          => $indexable->twitter_title,
                        'twitter_description'    => $indexable->twitter_description,
                        'open_graph_title'       => $indexable->open_graph_title,
                        'open_graph_description' => $indexable->open_graph_description,
                    ];
                }
            } catch (Exception $e) {
                // Yoast classes not available
            }
        }
        
        // Determine if values are properly set
        $focuskw_ok = !empty($stored_meta['focuskw']);
        $metadesc_ok = !empty($stored_meta['metadesc']);
        $title_ok = !empty($stored_meta['title']);
        
        $ok = $focuskw_ok && $metadesc_ok && $title_ok;
        
        return new WP_REST_Response([
            'ok'                   => $ok,
            'post_id'              => $post_id,
            'stored_meta'          => $stored_meta,
            'focuskw_ok'           => $focuskw_ok,
            'metadesc_ok'          => $metadesc_ok,
            'title_ok'             => $title_ok,
            'last_sync'            => $last_sync,
            'yoast_indexable_seen' => $yoast_indexable_seen,
            'yoast_values'         => $yoast_indexable_values,
        ], 200);
    }
}

// Initialize the plugin
Barna_Yoast_Bridge::init();
