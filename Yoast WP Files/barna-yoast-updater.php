<?php
/**
 * Plugin Name: Barna Yoast Updater
 * Description: REST API endpoint to update Yoast SEO fields
 * Version: 1.0
 * Author: Barna News
 */

// Prevent direct access
if (!defined('ABSPATH')) {
    exit;
}

// Register REST API endpoint
add_action('rest_api_init', function () {
    register_rest_route('barna/v1', '/update-yoast/(?P<id>\d+)', array(
        'methods' => 'POST',
        'callback' => 'barna_update_yoast_fields',
        'permission_callback' => function() {
            return current_user_can('edit_posts');
        },
        'args' => array(
            'id' => array(
                'validate_callback' => function($param) {
                    return is_numeric($param);
                }
            ),
        ),
    ));
});

function barna_update_yoast_fields($request) {
    $post_id = $request['id'];
    $params = $request->get_json_params();

    // Check if post exists
    if (!get_post($post_id)) {
        return new WP_Error('post_not_found', 'Post not found', array('status' => 404));
    }

    $updated = array();

    // Update Yoast SEO Title
    if (isset($params['seo_title'])) {
        update_post_meta($post_id, '_yoast_wpseo_title', sanitize_text_field($params['seo_title']));
        $updated['seo_title'] = $params['seo_title'];
    }

    // Update Yoast Meta Description
    if (isset($params['meta_description'])) {
        update_post_meta($post_id, '_yoast_wpseo_metadesc', sanitize_textarea_field($params['meta_description']));
        $updated['meta_description'] = $params['meta_description'];
    }

    // Update Yoast Focus Keyword
    if (isset($params['focus_keyword'])) {
        update_post_meta($post_id, '_yoast_wpseo_focuskw', sanitize_text_field($params['focus_keyword']));
        $updated['focus_keyword'] = $params['focus_keyword'];
    }

    // Set robots meta to index/follow
    update_post_meta($post_id, '_yoast_wpseo_meta-robots-noindex', '0');
    update_post_meta($post_id, '_yoast_wpseo_meta-robots-nofollow', '0');

    // Return success response
    return array(
        'success' => true,
        'post_id' => $post_id,
        'updated' => $updated,
        'message' => 'Yoast meta fields updated successfully'
    );
}
?>
