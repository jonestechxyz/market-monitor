<?php
// Chat about one "A Use a Day" page. The page text is read here on the server, never sent by
// the browser, so this endpoint can only be used to discuss a published page.
$KEY_FILE   = dirname(__DIR__) . '/groq_key.php';
$RATE_DIR   = dirname(__DIR__) . '/groq_rate/use_chat';
// A different model from the daily page builders, so chat traffic cannot use up their allowance.
$MODEL      = 'openai/gpt-oss-20b';
$PER_HOUR   = 30;    // per visitor
$PER_DAY    = 300;   // for everyone together
$MAX_MSGS   = 12;
$MAX_CHARS  = 2000;  // per message
$ALLOWED    = ['https://jonestech.xyz', 'https://www.jonestech.xyz'];

header('Content-Type: application/json');
function fail($code, $msg) { http_response_code($code); echo json_encode(['error' => $msg]); exit; }

if ($_SERVER['REQUEST_METHOD'] !== 'POST') fail(405, 'POST only');
$origin = $_SERVER['HTTP_ORIGIN'] ?? ''; $referer = $_SERVER['HTTP_REFERER'] ?? '';
$ok = false;
foreach ($ALLOWED as $a) if ($origin === $a || strpos($referer, $a . '/') === 0) { $ok = true; break; }
if (!$ok) fail(403, 'Forbidden');

$in = json_decode(file_get_contents('php://input'), true);
if (!is_array($in) || !is_string($in['page'] ?? null) || !is_array($in['messages'] ?? null)) fail(400, 'Bad request');

// Only the live page or a dated archive copy, and nothing else on the server.
$page = $in['page'];
if (!preg_match('#^(Use\.html|archive/use/Use-\d{4}-\d{2}-\d{2}\.html)$#', $page)) fail(400, 'Unknown page');
$path = __DIR__ . '/' . $page;
if (!is_file($path)) fail(404, 'Page not found');

$messages = [];
foreach (array_slice($in['messages'], -$MAX_MSGS) as $m) {
    if (!is_array($m) || !in_array($m['role'] ?? '', ['user', 'assistant'], true) || !is_string($m['content'] ?? null)) fail(400, 'Bad message');
    if (strlen($m['content']) > $MAX_CHARS) fail(413, 'That message is too long. Keep it under 2,000 characters.');
    $messages[] = ['role' => $m['role'], 'content' => $m['content']];
}
if (!$messages || end($messages)['role'] !== 'user') fail(400, 'Nothing to answer');

// Rate limits: per visitor per hour, and for the whole site per day.
if (!is_dir($RATE_DIR)) @mkdir($RATE_DIR, 0700, true);
$now = time();
$rf = $RATE_DIR . '/' . hash('sha256', $_SERVER['REMOTE_ADDR'] ?? 'unknown');
$hits = is_file($rf) ? array_filter(explode("\n", file_get_contents($rf)), fn($t) => $t !== '' && $now - (int)$t < 3600) : [];
if (count($hits) >= $PER_HOUR) fail(429, 'You have reached the hourly limit for questions. Try again in a while.');
$df = $RATE_DIR . '/day-' . gmdate('Ymd');
$day = is_file($df) ? (int)file_get_contents($df) : 0;
if ($day >= $PER_DAY) fail(429, 'The chat has reached its limit for today. Try again tomorrow.');
$hits[] = $now;
file_put_contents($rf, implode("\n", $hits), LOCK_EX);
file_put_contents($df, (string)($day + 1), LOCK_EX);

// The page as plain text.
$html = file_get_contents($path);
$html = preg_replace('#<(style|script|head)\b.*?</\1>#si', ' ', $html);
$html = preg_replace('#<(li|p|h1|h3|div|br)\b#i', "\n<$1", $html);
$text = trim(preg_replace("/[ \t]+/", ' ', preg_replace("/\n\s*\n+/", "\n", html_entity_decode(strip_tags($html), ENT_QUOTES | ENT_HTML5, 'UTF-8'))));
$text = mb_substr($text, 0, 9000);

$system = "You are a practical colleague helping someone who works in construction in Europe. They are reading the page below, "
  . "which suggests one way to make the computer do a repetitive paperwork job. Help them understand it, adapt it to their "
  . "own situation, and actually set it up.\n\n"
  . "How to answer:\n"
  . "- Plain words. They know building thoroughly but are not comfortable with technology. Explain any technical step as "
  . "concrete actions: which menu, which button, what to type.\n"
  . "- When they ask how to set it up, give numbered steps using tools they already have (Excel, Word, their folders) "
  . "before suggesting anything to install. Give real Excel formulas or exact settings when they help.\n"
  . "- Keep answers under about 250 words unless they ask for more detail.\n"
  . "- Format for a phone screen: short paragraphs, numbered steps or bullet points, bold for key words. Never use tables.\n"
  . "- Only describe menus, options and commands you are sure exist in that program. If you are not sure, say so plainly and tell them what to look for instead of guessing. Prefer built-in features over anything that needs installing; if something must be installed (an add-in, a module), say so first.\n"
  . "- Be honest about limits and about what a person must still check. Do not name or quote any law, regulation or "
  . "contract clause number. Use euros, metric units and day-month-year dates.\n"
  . "- This chat runs on an online AI service. If they start pasting what looks like real, confidential project documents "
  . "(names of real clients, prices, contract text), remind them not to, and suggest they use made-up examples.\n"
  . "- Stay on this page's topic and closely related paperwork automation. Politely decline anything unrelated.\n\n"
  . "THE PAGE:\n" . $text;

$payload = json_encode([
    'model'            => $MODEL,
    'messages'         => array_merge([['role' => 'system', 'content' => $system]], $messages),
    'max_tokens'       => 1400,
    'temperature'      => 0.4,
    'reasoning_effort' => 'low',
]);

$key = require $KEY_FILE;
$ch = curl_init('https://api.groq.com/openai/v1/chat/completions');
curl_setopt_array($ch, [
    CURLOPT_POST => true, CURLOPT_POSTFIELDS => $payload, CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 60,
    CURLOPT_HTTPHEADER => ['Content-Type: application/json', 'Authorization: Bearer ' . $key],
]);
$res = curl_exec($ch);
$code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);
if ($res === false) fail(502, 'The AI service could not be reached. Try again in a minute.');
$data = json_decode($res, true);
$reply = trim($data['choices'][0]['message']['content'] ?? '');
if ($code !== 200 || $reply === '') fail(502, 'The AI service did not answer (' . $code . '). Try again in a minute.');
echo json_encode(['reply' => $reply]);
