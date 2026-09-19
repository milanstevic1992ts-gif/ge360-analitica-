<?php
/**
 * Plugin Name: GE360 Tracker
 * Description: Raccoglie in modo privacy-first page view e conversioni (WhatsApp, telefono, moduli) per GE360 Analitica.
 * Version: 0.2.0
 * Author: GE360
 */

if (!defined('ABSPATH')) {
    exit;
}

define('GE360_TRACKER_VERSION', '0.2.0');
define('GE360_TRACKER_DB_VERSION', '2');
define('GE360_TRACKER_MAX_BATCH', 25);
define('GE360_TRACKER_TABLE_SUFFIX', 'ge360_events');

function ge360_tracker_table_name() {
    global $wpdb;
    return $wpdb->prefix . GE360_TRACKER_TABLE_SUFFIX;
}

function ge360_tracker_activate() {
    global $wpdb;
    $table = ge360_tracker_table_name();
    $charset = $wpdb->get_charset_collate();

    $sql = "CREATE TABLE {$table} (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        event_type VARCHAR(64) NOT NULL,
        source VARCHAR(190) NULL,
        campaign VARCHAR(190) NULL,
        content_id VARCHAR(190) NULL,
        url TEXT NULL,
        referrer TEXT NULL,
        occurred_at DATETIME NOT NULL,
        event_id VARCHAR(64) NULL,
        session_id VARCHAR(64) NULL,
        visitor_id VARCHAR(64) NULL,
        device VARCHAR(16) NULL,
        value DOUBLE NULL,
        payload LONGTEXT NULL,
        PRIMARY KEY  (id),
        UNIQUE KEY event_id (event_id),
        KEY event_type (event_type),
        KEY occurred_at (occurred_at),
        KEY session_id (session_id)
    ) {$charset};";

    require_once ABSPATH . 'wp-admin/includes/upgrade.php';
    dbDelta($sql);

    if (!get_option('ge360_tracker_sync_key')) {
        update_option('ge360_tracker_sync_key', wp_generate_password(48, false, false), false);
    }

    if (!get_option('ge360_tracker_retention_days')) {
        update_option('ge360_tracker_retention_days', 365, false);
    }

    update_option('ge360_tracker_db_version', GE360_TRACKER_DB_VERSION, false);
}
register_activation_hook(__FILE__, 'ge360_tracker_activate');

// Gli aggiornamenti del plugin non richiamano l'hook di attivazione:
// la tabella viene aggiornata al primo caricamento dopo l'update.
function ge360_tracker_maybe_upgrade() {
    if (get_option('ge360_tracker_db_version') !== GE360_TRACKER_DB_VERSION) {
        ge360_tracker_activate();
    }
}
add_action('plugins_loaded', 'ge360_tracker_maybe_upgrade');

function ge360_tracker_allowed_event_types() {
    return array(
        'page_view',
        'whatsapp_click',
        'phone_click',
        'form_submit',
        'email_click',
        'cta_click',
        'page_404',
        'scroll_depth',
        'page_engagement',
        'form_start',
        'outbound_click',
        'file_download',
        'rage_click',
        'web_vital',
    );
}

// Solo queste chiavi descrittive possono finire nel campo payload.
function ge360_tracker_allowed_meta_keys() {
    return array(
        'medium', 'term', 'content', 'click_id', 'landing', 'page_index', 'lang',
        'viewport', 'title', 'path', 'max_scroll', 'target', 'text', 'target_host',
        'file_ext', 'form_id', 'metric_name', 'metric_rating', 'vital_target',
    );
}

function ge360_tracker_clean_id($value) {
    $value = is_string($value) ? $value : '';
    return preg_match('/^[A-Za-z0-9\-]{8,64}$/', $value) ? $value : null;
}

function ge360_tracker_clean_meta($meta) {
    if (!is_array($meta)) {
        return null;
    }
    $clean = array();
    foreach (ge360_tracker_allowed_meta_keys() as $key) {
        if (!array_key_exists($key, $meta)) {
            continue;
        }
        $value = $meta[$key];
        if (is_int($value) || is_float($value)) {
            $clean[$key] = $value;
        } elseif (is_string($value)) {
            $clean[$key] = mb_substr(sanitize_text_field($value), 0, 300);
        }
    }
    return empty($clean) ? null : wp_json_encode($clean);
}

function ge360_tracker_clean_url($value) {
    if (!$value) {
        return null;
    }

    $url = esc_url_raw(wp_unslash($value));
    if (!$url) {
        return null;
    }

    // Rimuove fragment e parametri potenzialmente sensibili; conserva UTM solo separatamente.
    $parts = wp_parse_url($url);
    if (!$parts || empty($parts['host'])) {
        return null;
    }

    $scheme = isset($parts['scheme']) ? $parts['scheme'] : 'https';
    $path = isset($parts['path']) ? $parts['path'] : '/';
    return esc_url_raw($scheme . '://' . $parts['host'] . $path);
}

function ge360_tracker_same_origin_request(WP_REST_Request $request) {
    $origin = $request->get_header('origin');
    $referer = $request->get_header('referer');
    $home_host = wp_parse_url(home_url('/'), PHP_URL_HOST);

    foreach (array($origin, $referer) as $candidate) {
        if (!$candidate) {
            continue;
        }
        $host = wp_parse_url($candidate, PHP_URL_HOST);
        if ($host && strtolower($host) === strtolower($home_host)) {
            return true;
        }
    }

    return false;
}

function ge360_tracker_rate_limit_ok() {
    $remote = isset($_SERVER['REMOTE_ADDR']) ? sanitize_text_field(wp_unslash($_SERVER['REMOTE_ADDR'])) : 'unknown';
    $bucket = gmdate('YmdHi');
    $key = 'ge360_rl_' . substr(hash_hmac('sha256', $remote . '|' . $bucket, wp_salt('nonce')), 0, 24);
    $count = (int) get_transient($key);

    if ($count >= 90) {
        return false;
    }

    set_transient($key, $count + 1, 2 * MINUTE_IN_SECONDS);
    return true;
}

function ge360_tracker_track_permission(WP_REST_Request $request) {
    return ge360_tracker_same_origin_request($request) && ge360_tracker_rate_limit_ok();
}

function ge360_tracker_sync_permission(WP_REST_Request $request) {
    $configured = (string) get_option('ge360_tracker_sync_key', '');
    $provided = (string) $request->get_header('x-ge360-key');

    if (!$configured || !$provided) {
        return false;
    }

    return hash_equals($configured, $provided);
}

function ge360_tracker_insert_one($event) {
    global $wpdb;

    if (!is_array($event)) {
        return false;
    }

    $event_type = isset($event['event_type']) ? sanitize_key($event['event_type']) : '';
    if (!in_array($event_type, ge360_tracker_allowed_event_types(), true)) {
        return false;
    }

    $device = isset($event['device']) ? sanitize_key($event['device']) : '';
    if (!in_array($device, array('mobile', 'tablet', 'desktop'), true)) {
        $device = null;
    }

    $value = (isset($event['value']) && is_numeric($event['value'])) ? (float) $event['value'] : null;

    $row = array(
        'event_type' => $event_type,
        'source' => isset($event['source']) ? mb_substr(sanitize_text_field($event['source']), 0, 190) : null,
        'campaign' => isset($event['campaign']) ? mb_substr(sanitize_text_field($event['campaign']), 0, 190) : null,
        'content_id' => isset($event['content_id']) ? mb_substr(sanitize_text_field($event['content_id']), 0, 190) : null,
        'url' => isset($event['url']) ? ge360_tracker_clean_url($event['url']) : null,
        'referrer' => isset($event['referrer']) ? ge360_tracker_clean_url($event['referrer']) : null,
        'occurred_at' => current_time('mysql', true),
        'event_id' => ge360_tracker_clean_id(isset($event['event_id']) ? $event['event_id'] : ''),
        'session_id' => ge360_tracker_clean_id(isset($event['session_id']) ? $event['session_id'] : ''),
        'visitor_id' => ge360_tracker_clean_id(isset($event['visitor_id']) ? $event['visitor_id'] : ''),
        'device' => $device,
        'value' => $value,
        'payload' => ge360_tracker_clean_meta(isset($event['meta']) ? $event['meta'] : null),
    );

    // Valori vuoti -> NULL scritto esplicitamente; il resto passa da prepare().
    $columns = array();
    $placeholders = array();
    $args = array();
    foreach ($row as $column => $cell) {
        $columns[] = $column;
        if ($cell === null || $cell === '') {
            $placeholders[] = 'NULL';
        } elseif ($column === 'value') {
            $placeholders[] = '%f';
            $args[] = $cell;
        } else {
            $placeholders[] = '%s';
            $args[] = $cell;
        }
    }

    $table = ge360_tracker_table_name();
    // INSERT IGNORE: lo stesso event_id inviato due volte viene scartato.
    $sql = $wpdb->prepare(
        "INSERT IGNORE INTO {$table} (" . implode(', ', $columns) . ') VALUES (' . implode(', ', $placeholders) . ')',
        $args
    );

    return $wpdb->query($sql) !== false;
}

function ge360_tracker_store_event(WP_REST_Request $request) {
    $payload = $request->get_json_params();
    if (!is_array($payload)) {
        return new WP_Error('invalid_payload', 'Payload non valido', array('status' => 400));
    }

    // Compatibile con il tracker 0.1 (evento singolo) e 0.2 (blocco di eventi).
    $events = isset($payload['events']) && is_array($payload['events'])
        ? array_slice($payload['events'], 0, GE360_TRACKER_MAX_BATCH)
        : array($payload);

    $stored = 0;
    foreach ($events as $event) {
        if (ge360_tracker_insert_one($event)) {
            $stored++;
        }
    }

    if (!$stored) {
        return new WP_Error('invalid_event', 'Nessun evento valido', array('status' => 400));
    }

    return rest_ensure_response(array('ok' => true, 'stored' => $stored));
}

function ge360_tracker_export_events(WP_REST_Request $request) {
    global $wpdb;

    $after_id = max(0, (int) $request->get_param('after_id'));
    $limit = min(500, max(1, (int) $request->get_param('limit')));
    if (!$limit) {
        $limit = 250;
    }

    $table = ge360_tracker_table_name();
    $rows = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT id, event_type, source, campaign, content_id, url, occurred_at,
                    event_id, session_id, visitor_id, device, value, payload
             FROM {$table}
             WHERE id > %d
             ORDER BY id ASC
             LIMIT %d",
            $after_id,
            $limit
        ),
        ARRAY_A
    );

    $last_id = $after_id;
    if (!empty($rows)) {
        $last = end($rows);
        $last_id = (int) $last['id'];
    }

    return rest_ensure_response(array(
        'events' => $rows,
        'last_id' => $last_id,
        'has_more' => count($rows) === $limit,
    ));
}

function ge360_tracker_status(WP_REST_Request $request) {
    global $wpdb;
    $table = ge360_tracker_table_name();

    return rest_ensure_response(array(
        'version' => GE360_TRACKER_VERSION,
        'events' => (int) $wpdb->get_var("SELECT COUNT(*) FROM {$table}"),
        'latest_id' => (int) $wpdb->get_var("SELECT COALESCE(MAX(id), 0) FROM {$table}"),
        'retention_days' => (int) get_option('ge360_tracker_retention_days', 365),
        'persistent_visitor' => (bool) get_option('ge360_tracker_persistent_visitor', false),
    ));
}

function ge360_tracker_register_routes() {
    register_rest_route('ge360/v1', '/track', array(
        'methods' => WP_REST_Server::CREATABLE,
        'callback' => 'ge360_tracker_store_event',
        'permission_callback' => 'ge360_tracker_track_permission',
    ));

    register_rest_route('ge360/v1', '/events', array(
        'methods' => WP_REST_Server::READABLE,
        'callback' => 'ge360_tracker_export_events',
        'permission_callback' => 'ge360_tracker_sync_permission',
        'args' => array(
            'after_id' => array('default' => 0, 'sanitize_callback' => 'absint'),
            'limit' => array('default' => 250, 'sanitize_callback' => 'absint'),
        ),
    ));

    register_rest_route('ge360/v1', '/status', array(
        'methods' => WP_REST_Server::READABLE,
        'callback' => 'ge360_tracker_status',
        'permission_callback' => 'ge360_tracker_sync_permission',
    ));
}
add_action('rest_api_init', 'ge360_tracker_register_routes');

function ge360_tracker_frontend_script() {
    if (is_admin()) {
        return;
    }

    // Libreria ufficiale Google web-vitals 4.2.4 (Apache-2.0), servita dal sito stesso.
    wp_register_script(
        'ge360-web-vitals',
        plugins_url('web-vitals.attribution.iife.js', __FILE__),
        array(),
        '4.2.4',
        true
    );

    wp_register_script(
        'ge360-tracker',
        plugins_url('tracker.js', __FILE__),
        array('ge360-web-vitals'),
        GE360_TRACKER_VERSION,
        true
    );

    wp_localize_script('ge360-tracker', 'GE360TrackerConfig', array(
        'endpoint' => esc_url_raw(rest_url('ge360/v1/track')),
        'contentId' => is_singular() ? (string) get_queried_object_id() : '',
        'is404' => is_404(),
        'persistentVisitor' => (bool) get_option('ge360_tracker_persistent_visitor', false),
    ));

    wp_enqueue_script('ge360-tracker');
}
add_action('wp_enqueue_scripts', 'ge360_tracker_frontend_script');

function ge360_tracker_cleanup() {
    global $wpdb;
    $days = max(30, (int) get_option('ge360_tracker_retention_days', 365));
    $table = ge360_tracker_table_name();
    $wpdb->query(
        $wpdb->prepare(
            "DELETE FROM {$table} WHERE occurred_at < UTC_TIMESTAMP() - INTERVAL %d DAY",
            $days
        )
    );
}
add_action('ge360_tracker_daily_cleanup', 'ge360_tracker_cleanup');

function ge360_tracker_schedule_cleanup() {
    if (!wp_next_scheduled('ge360_tracker_daily_cleanup')) {
        wp_schedule_event(time() + HOUR_IN_SECONDS, 'daily', 'ge360_tracker_daily_cleanup');
    }
}
add_action('init', 'ge360_tracker_schedule_cleanup');

function ge360_tracker_admin_menu() {
    add_options_page(
        'GE360 Tracker',
        'GE360 Tracker',
        'manage_options',
        'ge360-tracker',
        'ge360_tracker_settings_page'
    );
}
add_action('admin_menu', 'ge360_tracker_admin_menu');

function ge360_tracker_register_settings() {
    register_setting('ge360_tracker_settings', 'ge360_tracker_sync_key', array(
        'type' => 'string',
        'sanitize_callback' => 'sanitize_text_field',
    ));
    register_setting('ge360_tracker_settings', 'ge360_tracker_retention_days', array(
        'type' => 'integer',
        'sanitize_callback' => 'absint',
    ));
    register_setting('ge360_tracker_settings', 'ge360_tracker_persistent_visitor', array(
        'type' => 'boolean',
        'sanitize_callback' => 'rest_sanitize_boolean',
    ));
}
add_action('admin_init', 'ge360_tracker_register_settings');

function ge360_tracker_settings_page() {
    if (!current_user_can('manage_options')) {
        return;
    }

    $key = (string) get_option('ge360_tracker_sync_key', '');
    $days = (int) get_option('ge360_tracker_retention_days', 365);
    $persistent = (bool) get_option('ge360_tracker_persistent_visitor', false);
    ?>
    <div class="wrap">
        <h1>GE360 Tracker</h1>
        <p>Raccoglie solo eventi analitici. Non registra nome, telefono, email, IP o testo dei moduli.</p>
        <form method="post" action="options.php">
            <?php settings_fields('ge360_tracker_settings'); ?>
            <table class="form-table">
                <tr>
                    <th scope="row">Chiave sincronizzazione</th>
                    <td>
                        <input type="text" class="regular-text code" name="ge360_tracker_sync_key"
                               value="<?php echo esc_attr($key); ?>" autocomplete="off" />
                        <p class="description">Inserisci questa chiave nel file .env del server GE360 come WORDPRESS_GE360_KEY.</p>
                    </td>
                </tr>
                <tr>
                    <th scope="row">Conservazione eventi</th>
                    <td>
                        <input type="number" min="30" max="730" name="ge360_tracker_retention_days"
                               value="<?php echo esc_attr($days); ?>" /> giorni
                    </td>
                </tr>
                <tr>
                    <th scope="row">Riconosci i visitatori di ritorno</th>
                    <td>
                        <label>
                            <input type="checkbox" name="ge360_tracker_persistent_visitor" value="1"
                                   <?php checked($persistent); ?> />
                            Salva un ID anonimo nel browser per collegare più visite della stessa persona
                        </label>
                        <p class="description">Spento: ogni sessione resta separata. Acceso: vedi il percorso su più giorni.
                            Prima di accenderlo verifica che l'informativa cookie e il banner consenso lo coprano.</p>
                    </td>
                </tr>
            </table>
            <?php submit_button(); ?>
        </form>
    </div>
    <?php
}
