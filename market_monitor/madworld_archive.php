<?php
$files = glob(__DIR__ . '/MadWorld-????-??-??.html');
rsort($files); // newest first

$editions = [];
foreach ($files as $f) {
    $name = basename($f);
    if (preg_match('/MadWorld-(\d{4})-(\d{2})-(\d{2})\.html$/', $name, $m)) {
        $ts = mktime(0, 0, 0, (int)$m[2], (int)$m[3], (int)$m[1]);
        $editions[] = [
            'file'  => $name,
            'label' => date('l j F Y', $ts),
            'ts'    => $ts,
        ];
    }
}
?><!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MAD! World — Archive</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@700;900&family=Special+Elite&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #1a0a00;
    --surface: #2a1200;
    --border: #5a2a00;
    --text: #f5e6c8;
    --text-dim: #c4a882;
    --red: #cc0000;
    --yellow: #ffd700;
    --yellow2: #ffb300;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Special Elite', cursive;
    max-width: 780px;
    margin: 0 auto;
    padding: 0 24px 60px;
  }

  .masthead {
    text-align: center;
    padding: 36px 0 24px;
    border-bottom: 6px double var(--yellow);
    margin-bottom: 40px;
  }
  .masthead::before {
    content: "EVERY ABSURD DAY, PRESERVED FOR POSTERITY";
    display: block;
    font-family: 'Oswald', sans-serif;
    font-size: 11px;
    letter-spacing: 0.2em;
    color: var(--yellow2);
    text-transform: uppercase;
    margin-bottom: 12px;
  }
  .masthead-title {
    font-family: 'Oswald', sans-serif;
    font-size: 72px;
    font-weight: 900;
    line-height: 0.9;
    color: var(--yellow);
    text-shadow: 4px 4px 0 var(--red), 8px 8px 0 #660000;
    letter-spacing: -2px;
  }
  .masthead-title span { color: var(--red); text-shadow: 4px 4px 0 var(--yellow), 8px 8px 0 #884400; }
  .masthead-sub {
    font-family: 'Oswald', sans-serif;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.3em;
    text-transform: uppercase;
    color: var(--red);
    margin-top: 8px;
  }

  .count {
    font-family: 'Oswald', sans-serif;
    font-size: 12px;
    color: var(--text-dim);
    letter-spacing: 0.1em;
    text-align: center;
    margin-bottom: 32px;
  }
  .count strong { color: var(--yellow); }

  .today-link {
    display: block;
    text-align: center;
    font-family: 'Oswald', sans-serif;
    font-weight: 700;
    font-size: 15px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--bg);
    background: var(--yellow);
    padding: 14px 28px;
    border-radius: 3px;
    text-decoration: none;
    margin: 0 auto 40px;
    max-width: 320px;
    border: 3px solid var(--red);
    transition: background 0.15s;
  }
  .today-link:hover { background: var(--yellow2); }

  .year-group { margin-bottom: 36px; }
  .year-label {
    font-family: 'Oswald', sans-serif;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.25em;
    text-transform: uppercase;
    color: var(--red);
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
  }
  .year-label::before, .year-label::after {
    content: "";
    flex: 1;
    height: 2px;
    background: repeating-linear-gradient(90deg, var(--red) 0, var(--red) 6px, transparent 6px, transparent 10px);
  }

  .edition-list { list-style: none; }
  .edition-list li {
    border-bottom: 1px solid var(--border);
  }
  .edition-list li:first-child { border-top: 1px solid var(--border); }
  .edition-list a {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 13px 6px;
    text-decoration: none;
    color: var(--text);
    transition: background 0.1s, padding-left 0.1s;
    gap: 12px;
  }
  .edition-list a:hover {
    background: var(--surface);
    padding-left: 14px;
    color: var(--yellow);
  }
  .edition-date { font-size: 15px; }
  .edition-arrow {
    font-family: 'Oswald', sans-serif;
    font-size: 11px;
    letter-spacing: 0.1em;
    color: var(--red);
    flex-shrink: 0;
  }

  .empty {
    text-align: center;
    color: var(--text-dim);
    font-style: italic;
    padding: 40px 0;
  }

  .footer {
    border-top: 4px double var(--yellow);
    padding-top: 20px;
    margin-top: 40px;
    text-align: center;
    font-family: 'Oswald', sans-serif;
    font-size: 11px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--text-dim);
  }
  .footer strong { color: var(--yellow); }

  @media (max-width: 480px) {
    .masthead-title { font-size: 52px; }
  }
</style>
</head>
<body>

<div class="masthead">
  <div class="masthead-title">MAD<span>!</span></div>
  <div class="masthead-sub">World Archive</div>
</div>

<?php if ($editions): ?>
<p class="count"><strong><?= count($editions) ?></strong> edition<?= count($editions) !== 1 ? 's' : '' ?> in the vault</p>

<a class="today-link" href="../MadWorld.html">→ Read Today's Edition</a>

<?php
// Group by year
$by_year = [];
foreach ($editions as $e) {
    $y = date('Y', $e['ts']);
    $by_year[$y][] = $e;
}
foreach ($by_year as $year => $items):
?>
<div class="year-group">
  <div class="year-label"><?= $year ?></div>
  <ul class="edition-list">
    <?php foreach ($items as $e): ?>
    <li>
      <a href="<?= htmlspecialchars($e['file']) ?>">
        <span class="edition-date"><?= $e['label'] ?></span>
        <span class="edition-arrow">READ →</span>
      </a>
    </li>
    <?php endforeach; ?>
  </ul>
</div>
<?php endforeach; ?>

<?php else: ?>
<p class="empty">No archived editions yet — check back after the first run.</p>
<?php endif; ?>

<div class="footer">
  <strong>MAD! World</strong> &nbsp;·&nbsp; Generated daily at 09:00 UTC &nbsp;·&nbsp; jonestech.xyz
</div>

</body>
</html>
