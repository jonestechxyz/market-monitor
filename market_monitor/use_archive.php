<?php
$files = glob(__DIR__ . '/Use-????-??-??.html');
sort($files);
$rows = [];
foreach ($files as $i => $f) {
    $name = basename($f);
    if (!preg_match('/(\d{4})-(\d{2})-(\d{2})/', $name, $m)) continue;
    $src = file_get_contents($f);
    preg_match('/<h1>(.*?)<\/h1>/s', $src, $t);
    preg_match('/class="no">No\. \d+ · (.*?)<\/div>/s', $src, $c);
    $rows[] = ['file' => $name, 'no' => $i + 1, 'title' => $t[1] ?? $name, 'cat' => $c[1] ?? '',
               'date' => date('j M Y', mktime(0, 0, 0, $m[2], $m[3], $m[1]))];
}
$rows = array_reverse($rows);
?><!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A Use a Day — all uses</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Source+Serif+4&display=swap" rel="stylesheet">
<style>
  :root { --bg:#f6f1e4; --ink:#1e2a2a; --dim:#667370; --rule:#d4cbb4; --teal:#12706a; --orange:#d9622b; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#101615; --ink:#e7e3d6; --dim:#93a09c; --rule:#2b3634; --teal:#4cc2b8; --orange:#f08a52; }
  }
  body { margin:0; background:var(--bg); color:var(--ink); font:18px/1.5 'Source Serif 4', Georgia, serif; }
  main { max-width:700px; margin:0 auto; padding:32px 18px 70px; }
  h1 { font:700 40px/1.05 'Space Grotesk', sans-serif; margin:0; letter-spacing:-.02em; }
  .sub { color:var(--dim); margin:6px 0 24px; border-bottom:3px solid var(--teal); padding-bottom:12px; }
  .sub a { color:var(--teal); }
  a.row { display:grid; grid-template-columns:52px 1fr; gap:10px; padding:13px 0; border-bottom:1px solid var(--rule);
          color:var(--ink); text-decoration:none; }
  a.row:hover .t { color:var(--teal); }
  .n { font:700 15px 'Space Grotesk', sans-serif; color:var(--orange); padding-top:3px; }
  .t { font-weight:600; }
  .d { color:var(--dim); font-size:14px; }
</style>
</head>
<body>
<main>
  <h1>A Use a Day</h1>
  <div class="sub"><?= count($rows) ?> repetitive jobs on a building project, and how to make the computer do them · <a href="/Use.html">today's</a></div>
  <?php foreach ($rows as $r): ?>
  <a class="row" href="<?= htmlspecialchars($r['file']) ?>">
    <div class="n">No. <?= $r['no'] ?></div>
    <div><div class="t"><?= $r['title'] ?></div><div class="d"><?= htmlspecialchars($r['date']) ?><?= $r['cat'] ? ' · ' . $r['cat'] : '' ?></div></div>
  </a>
  <?php endforeach; ?>
  <?php if (!$rows): ?><p style="color:var(--dim)">Nothing yet. The first one arrives tomorrow morning.</p><?php endif; ?>
</main>
</body>
</html>
