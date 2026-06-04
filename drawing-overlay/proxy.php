<?php
// Simple proxy for MangaDex API + images
// Only allows requests to mangadex.org and its CDN

$allowed = ['api.mangadex.org', 'uploads.mangadex.org'];

$url = isset($_GET['url']) ? $_GET['url'] : '';
if (!$url) { http_response_code(400); echo 'Missing url'; exit; }

$parsed = parse_url($url);
$host   = isset($parsed['host']) ? $parsed['host'] : '';

if (!in_array($host, $allowed)) {
    http_response_code(403);
    echo 'Forbidden host';
    exit;
}

// Fetch the remote URL
$ch = curl_init($url);
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_FOLLOWLOCATION => true,
    CURLOPT_TIMEOUT        => 15,
    CURLOPT_USERAGENT      => 'TraceHelper/1.0',
    CURLOPT_SSL_VERIFYPEER => true,
    CURLOPT_HEADER         => true,
]);
$response = curl_exec($ch);
$httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
$contentType = curl_getinfo($ch, CURLINFO_CONTENT_TYPE);
curl_close($ch);

$body = substr($response, $headerSize);

http_response_code($httpCode);
header('Access-Control-Allow-Origin: *');
header('Content-Type: ' . ($contentType ?: 'application/octet-stream'));
echo $body;
