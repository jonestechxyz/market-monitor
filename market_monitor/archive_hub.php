<?php
// One page listing every daily series, with how many editions each has and the latest one.
$SERIES = [
  ['madworld', 'MAD! World', 'MadWorld.html', 'MadWorld', 'The day\'s news as a satirical magazine'],
  ['use', 'A Use a Day', 'Use.html', 'Use', 'One repetitive building-site job, and how to automate it'],
  ['aiworld', 'AI World', 'AIWorld.html', 'AIWorld', 'What the world is doing with AI: the marvel and the panic'],
  ['signal', 'Signal', 'Signal.html', 'Signal', 'Daily futurology'],
  ['fork', 'The Fork', 'Fork.html', 'Fork', 'Two dispatches from five years ahead: bright and dark'],
  ['nabokov', 'The Daily Nabokov', 'Nabokov.html', 'Nabokov', 'One headline, written in the manner of Nabokov'],
  ['aiart', 'Life in 2050', 'AiArt.html', 'AiArt', 'A daily gallery of AI pictures of the future'],
  ['brief', 'Daily Brief', 'daily.html', 'Brief', 'Markets and news before the European open'],
];
require_once __DIR__ . '/headlines.php';
$rows = [];
foreach ($SERIES as [$key, $name, $live, $prefix, $blurb]) {
  $files = glob(__DIR__ . "/$key/$prefix-????-??-??.html") ?: [];
  rsort($files);
  $latest = $files ? preg_replace('/^.*-(\d{4})-(\d{2})-(\d{2})\.html$/', '$3-$2-$1', $files[0]) : '';
  $head = $files ? (edition_headlines(dirname($files[0]), $prefix, [$files[0]])[basename($files[0])] ?? '') : '';
  $rows[] = compact('key', 'name', 'live', 'blurb', 'latest', 'head') + ['count' => count($files)];
}
?><!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Archives — jonestech.xyz</title>
<style>
  :root { --bg:#f5f3ee; --ink:#1d2326; --dim:#6b7378; --rule:#d9d4c7; --accent:#12706a; --box:#fffdf8; }
  @media (prefers-color-scheme: dark) { :root { --bg:#111416; --ink:#e6e3dc; --dim:#8e979c; --rule:#2a3033; --accent:#4cc2b8; --box:#181c1e; } }
  body { margin:0; background:var(--bg); color:var(--ink); font:17px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  main { max-width:760px; margin:0 auto; padding:34px 18px 70px; }
  h1 { font-size:36px; line-height:1.1; margin:0; }
  .sub { color:var(--dim); margin:8px 0 24px; padding-bottom:14px; border-bottom:3px solid var(--accent); }
  .card { background:var(--box); border:1px solid var(--rule); border-radius:10px; padding:14px 16px; margin:0 0 12px; }
  .card h2 { margin:0; font-size:20px; }
  .card p { margin:4px 0 8px; color:var(--dim); }
  .card .links a { color:var(--accent); font-weight:600; margin-right:16px; text-decoration:none; }
  .meta { font-size:14px; color:var(--dim); }
  .card p.latest { color:var(--ink); font-weight:600; margin:8px 0 4px; }
</style>
</head>
<body>
<main>
  <h1>Archives</h1>
  <div class="sub">Every daily page on jonestech.xyz, and every edition it has published.</div>
  <?php foreach ($rows as $r): ?>
  <div class="card">
    <h2><?= htmlspecialchars($r['name']) ?></h2>
    <p><?= htmlspecialchars($r['blurb']) ?></p>
    <div class="links"><a href="/<?= htmlspecialchars($r['live']) ?>">Today's</a><a href="/archive/<?= $r['key'] ?>/index.php">Past editions</a></div>
    <?php if ($r['head']): ?><p class="latest">Latest: <?= htmlspecialchars($r['head']) ?></p><?php endif; ?>
    <div class="meta"><?= $r['count'] ?> archived<?= $r['latest'] ? ' · latest ' . $r['latest'] : '' ?></div>
  </div>
  <?php endforeach; ?>
</main>
</body>
</html>
