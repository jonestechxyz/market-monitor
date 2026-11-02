<?php
// Shared archive page for one daily series. It works out which series it belongs to from its folder.
$SERIES = [
  'signal'  => ['Signal', 'Signal.html', 'Signal'],
  'aiart'   => ['Life in 2050', 'AiArt.html', 'AiArt'],
  'aiworld' => ['AI World', 'AIWorld.html', 'AIWorld'],
  'brief'   => ['Daily Brief', 'daily.html', 'Brief'],
];
$key = basename(__DIR__);
[$name, $live, $prefix] = $SERIES[$key] ?? [ucfirst($key), '', ucfirst($key)];

$rows = [];
foreach (glob(__DIR__ . '/' . $prefix . '-????-??-??.html') as $f) {
  if (!preg_match('/(\d{4})-(\d{2})-(\d{2})\.html$/', $f, $m)) continue;
  $head = file_get_contents($f, false, null, 0, 6000);
  $title = preg_match('/<title>(.*?)<\/title>/s', $head, $t) ? html_entity_decode(trim($t[1]), ENT_QUOTES, 'UTF-8') : '';
  // Drop the series name and the date from the title, leaving what that day was about.
  $about = trim(preg_replace('/^' . preg_quote($name, '/') . '\s*[—–:-]?\s*/iu', '', $title));
  $about = trim(preg_replace('/\s*[—–-]?\s*\w+day,?\s+\d{1,2}\s+\w+\s+\d{4}\s*$|\s*[—–-]?\s*\d{1,2}\s+\w+\s+\d{4}\s*$/u', '', $about), " —–-");
  $ts = mktime(0, 0, 0, (int)$m[2], (int)$m[3], (int)$m[1]);
  $rows[] = ['file' => basename($f), 'ts' => $ts, 'about' => $about];
}
usort($rows, fn($a, $b) => $b['ts'] <=> $a['ts']);
require_once dirname(__DIR__) . '/headlines.php';
$heads = edition_headlines(__DIR__, $prefix, array_map(fn($r) => __DIR__ . '/' . $r['file'], $rows));
foreach ($rows as &$r) { if (!empty($heads[$r['file']])) $r['about'] = $heads[$r['file']]; }
unset($r);
?><!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title><?= htmlspecialchars($name) ?> — Past editions</title>
<style>
  :root { --bg:#f5f3ee; --ink:#1d2326; --dim:#6b7378; --rule:#d9d4c7; --accent:#12706a; }
  @media (prefers-color-scheme: dark) { :root { --bg:#111416; --ink:#e6e3dc; --dim:#8e979c; --rule:#2a3033; --accent:#4cc2b8; } }
  body { margin:0; background:var(--bg); color:var(--ink); font:17px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  main { max-width:720px; margin:0 auto; padding:34px 18px 70px; }
  h1 { font-size:34px; line-height:1.1; margin:0; letter-spacing:-.01em; }
  .sub { color:var(--dim); margin:8px 0 26px; padding-bottom:14px; border-bottom:3px solid var(--accent); }
  .sub a { color:var(--accent); }
  h2 { font-size:12px; letter-spacing:.16em; text-transform:uppercase; color:var(--accent); margin:26px 0 6px; }
  a.row { display:grid; grid-template-columns:96px 1fr; gap:12px; padding:10px 0; border-bottom:1px solid var(--rule); color:var(--ink); text-decoration:none; }
  a.row:hover .a { color:var(--accent); }
  .d { color:var(--dim); font-variant-numeric:tabular-nums; }
  .empty { color:var(--dim); font-style:italic; }
</style>
</head>
<body>
<main>
  <h1><?= htmlspecialchars($name) ?></h1>
  <div class="sub"><?= count($rows) ?> past edition<?= count($rows) === 1 ? '' : 's' ?>
    <?php if ($live): ?> · <a href="/<?= htmlspecialchars($live) ?>">today's</a><?php endif; ?>
    · <a href="/archive/index.php">all archives</a></div>
  <?php $month = ''; foreach ($rows as $r): $mm = date('F Y', $r['ts']); if ($mm !== $month): $month = $mm; ?>
  <h2><?= $mm ?></h2>
  <?php endif; ?>
  <a class="row" href="<?= htmlspecialchars($r['file']) ?>"><span class="d"><?= date('D j M', $r['ts']) ?></span>
    <span class="a"><?= htmlspecialchars($r['about'] !== '' ? $r['about'] : 'Read this edition') ?></span></a>
  <?php endforeach; ?>
  <?php if (!$rows): ?><p class="empty">No past editions yet. They start collecting from the next one.</p><?php endif; ?>
</main>
</body>
</html>
