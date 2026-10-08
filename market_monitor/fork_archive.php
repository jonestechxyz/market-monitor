<?php
$files = glob(__DIR__ . '/Fork-????-??-??.html');
rsort($files);
$rows = [];
foreach ($files as $f) {
    $name = basename($f);
    if (!preg_match('/(\d{4})-(\d{2})-(\d{2})/', $name, $m)) continue;
    $src = file_get_contents($f);
    preg_match_all('/<h2>(.*?)<\/h2>/s', $src, $t);
    preg_match('/dark fork: (\d+)%/', $src, $o);
    $rows[] = ['file' => $name, 'date' => date('l j F Y', mktime(0, 0, 0, $m[2], $m[3], $m[1])),
               'bright' => $t[1][0] ?? '', 'dark' => $t[1][1] ?? '', 'odds' => $o[1] ?? null];
}
?><!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>THE FORK — Archive</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=Newsreader:ital@0;1&display=swap" rel="stylesheet">
<style>
  :root { --bg:#0b0c0e; --ink:#e6e4df; --dim:#8b8a86; --rule:#26272b; --bright:#f2b544; --dark:#5ad1e6; --danger:#e5484d; }
  body { margin:0; background:var(--bg); color:var(--ink); font:17px/1.55 'Newsreader', Georgia, serif; }
  main { max-width:760px; margin:0 auto; padding:40px 16px 80px; }
  h1 { font:700 64px/0.9 'Space Grotesk', sans-serif; text-align:center; margin:0; letter-spacing:-.04em; }
  h1 span { color:var(--danger); }
  .sub { text-align:center; color:var(--dim); font:13px 'Space Grotesk', sans-serif; letter-spacing:.15em; text-transform:uppercase; margin:12px 0 32px; }
  .sub a { color:var(--ink); }
  a.row { display:block; border-top:1px solid var(--rule); padding:16px 4px; color:var(--ink); text-decoration:none; }
  a.row:hover { background:#141518; }
  .d { font:600 13px 'Space Grotesk', sans-serif; color:var(--dim); display:flex; justify-content:space-between; gap:12px; }
  .b { color:var(--bright); } .k { color:var(--dark); }
</style>
</head>
<body>
<main>
  <h1>THE F<span>O</span>RK</h1>
  <div class="sub"><?= count($rows) ?> forecasts · <a href="/Fork.html">today's</a></div>
  <?php foreach ($rows as $r): ?>
  <a class="row" href="<?= htmlspecialchars($r['file']) ?>">
    <div class="d"><span><?= htmlspecialchars($r['date']) ?></span><?php if ($r['odds'] !== null): ?><span>dark odds <?= (int)$r['odds'] ?>%</span><?php endif; ?></div>
    <div class="b"><?= $r['bright'] ?></div>
    <div class="k"><?= $r['dark'] ?></div>
  </a>
  <?php endforeach; ?>
  <?php if (!$rows): ?><p style="text-align:center;color:var(--dim)">No forecasts yet.</p><?php endif; ?>
</main>
</body>
</html>
