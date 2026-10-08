<?php
$files = glob(__DIR__ . '/Nabokov-????-??-??.html');
rsort($files);
$rows = [];
foreach ($files as $f) {
    $name = basename($f);
    if (!preg_match('/(\d{4})-(\d{2})-(\d{2})/', $name, $m)) continue;
    $title = '';
    if (preg_match('/<h2>(.*?)<\/h2>/s', file_get_contents($f), $t)) $title = $t[1];
    $rows[] = ['file' => $name, 'date' => date('l j F Y', mktime(0, 0, 0, $m[2], $m[3], $m[1])),
               'title' => $title, 'audio' => file_exists(__DIR__ . '/' . str_replace('.html', '.mp3', $name))];
}
?><!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Daily Nabokov — Archive</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&family=IM+Fell+English+SC&display=swap" rel="stylesheet">
<style>
  :root { --bg:#f4ecdc; --ink:#2b2118; --dim:#7a6a55; --rule:#c9b48f; --accent:#6b2d2d; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#16120d; --ink:#e8dcc4; --dim:#9c8b70; --rule:#4a3d2a; --accent:#c98f6a; }
  }
  body { margin:0; background:var(--bg); color:var(--ink); font:20px/1.6 'Cormorant Garamond', Georgia, serif; }
  main { max-width:680px; margin:0 auto; padding:48px 20px 80px; }
  h1 { font:400 40px/1.1 'IM Fell English SC', serif; text-align:center; margin:0; }
  .sub { text-align:center; color:var(--dim); font-style:italic; margin:6px 0 36px; }
  .sub a { color:var(--accent); }
  ul { list-style:none; padding:0; margin:0; border-top:1px solid var(--rule); }
  li { border-bottom:1px solid var(--rule); }
  li a { display:block; padding:14px 4px; color:var(--ink); text-decoration:none; }
  li a:hover { color:var(--accent); }
  .t { font-weight:600; font-size:22px; }
  .d { color:var(--dim); font-size:15px; font-style:italic; }
  .empty { text-align:center; color:var(--dim); font-style:italic; }
</style>
</head>
<body>
<main>
  <h1>The Daily Nabokov</h1>
  <div class="sub"><?= count($rows) ?> specimens pinned · <a href="/Nabokov.html">today's</a></div>
  <?php if ($rows): ?>
  <ul>
    <?php foreach ($rows as $r): ?>
    <li><a href="<?= htmlspecialchars($r['file']) ?>">
      <div class="t"><?= $r['title'] ?: htmlspecialchars($r['date']) ?></div>
      <div class="d"><?= htmlspecialchars($r['date']) ?><?= $r['audio'] ? ' · with audio' : '' ?></div>
    </a></li>
    <?php endforeach; ?>
  </ul>
  <?php else: ?>
  <p class="empty">The cabinet is empty. Check back tomorrow.</p>
  <?php endif; ?>
</main>
</body>
</html>
