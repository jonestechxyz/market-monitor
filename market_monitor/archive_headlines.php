<?php
// Headline of each archived edition, for the archive pages. Editions can be several MB (pictures are built in),
// so each headline is read once and remembered in headlines-cache.json next to the editions.

const HEADLINE_PATTERNS = [
  'MadWorld' => '#<div class="hero-headline">(.*?)</div>#s',
  'Signal'   => '#<h1 class="headline">(.*?)</h1>#s',
  'AiArt'    => '#<h1 class="header-title">(.*?)</h1>#s',
  'AIWorld'  => '#<h2 class="lead-title">(.*?)</h2>#s',
  'Brief'    => '#<h2 class="big-read-title">(.*?)</h2>#s',
  'Nabokov'  => '#<h2>(.*?)</h2>#s',
  'Fork'     => '#<h2>(.*?)</h2>#s',
  'Use'      => '#<h1>(.*?)</h1>#s',
];

function edition_headlines(string $dir, string $prefix, array $files): array {
  $cacheFile = $dir . '/headlines-cache.json';
  $cache = is_file($cacheFile) ? (json_decode(file_get_contents($cacheFile), true) ?: []) : [];
  $pattern = HEADLINE_PATTERNS[$prefix] ?? null;
  $out = []; $changed = false; $fresh = 0;
  @set_time_limit(120);
  foreach ($files as $f) {
    $name = basename($f); $mtime = filemtime($f);
    if (!isset($cache[$name]) || $cache[$name]['m'] !== $mtime) {
      $h = '';
      if ($pattern && preg_match($pattern, file_get_contents($f), $m)) {
        $h = trim(preg_replace('/\s+/', ' ', html_entity_decode(strip_tags($m[1]), ENT_QUOTES | ENT_HTML5, 'UTF-8')));
      }
      $cache[$name] = ['m' => $mtime, 'h' => $h]; $changed = true;
      // Save as it goes, so a first visit that runs out of time still keeps what it has read.
      if (++$fresh % 10 === 0) @file_put_contents($cacheFile, json_encode($cache), LOCK_EX);
    }
    $out[$name] = $cache[$name]['h'];
  }
  if ($changed) @file_put_contents($cacheFile, json_encode($cache), LOCK_EX);
  return $out;
}
