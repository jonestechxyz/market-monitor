// Adds "Ask about this idea" to an A Use a Day page. The server supplies the page text to the AI.
(() => {
  const m = location.pathname.match(/\/(Use\.html|archive\/use\/Use-\d{4}-\d{2}-\d{2}\.html)$/);
  const main = document.querySelector('main');
  if (!m || !main) return;
  const page = m[1];

  const css = document.createElement('style');
  css.textContent = `
    #ask { margin-top:40px; border:2px solid var(--teal); background:var(--box); padding:16px; }
    #ask h3 { margin-top:0; }
    #ask .note { color:var(--dim); font-size:14px; margin:0 0 12px; }
    #ask .chips { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:12px; }
    #ask .chip { font:500 14px 'Space Grotesk', sans-serif; border:1px solid var(--teal); color:var(--teal); background:transparent;
                 border-radius:16px; padding:6px 12px; cursor:pointer; }
    #ask .log { display:flex; flex-direction:column; gap:10px; }
    #ask .msg { padding:10px 12px; border-radius:8px; font-size:16px; line-height:1.55; overflow-wrap:anywhere; }
    #ask .me { align-self:flex-end; max-width:85%; background:var(--teal); color:var(--bg); white-space:pre-wrap; }
    #ask .ai { background:var(--bg); border:1px solid var(--rule); }
    #ask .ai p { margin:0 0 8px; } #ask .ai p:last-child { margin:0; }
    #ask .ai ol, #ask .ai ul { margin:0 0 8px; padding-left:22px; }
    #ask .ai pre { overflow-x:auto; background:var(--box); border:1px solid var(--rule); padding:8px; margin:0 0 8px; }
    #ask .ai pre code { background:none; padding:0; white-space:pre; }
    #ask .ai code { font:14px 'JetBrains Mono', ui-monospace, monospace; background:var(--box); padding:0 4px; }
    #ask .err { color:var(--orange); font-size:15px; }
    #ask form { display:flex; gap:8px; margin-top:12px; }
    #ask textarea { flex:1; min-width:0; min-height:46px; max-height:160px; resize:vertical; padding:10px; font:16px/1.4 inherit;
                    border:1px solid var(--rule); border-radius:6px; background:var(--bg); color:var(--ink); }
    #ask button.send { background:var(--teal); color:var(--bg); border:0; border-radius:6px; padding:0 18px;
                       font:700 14px 'Space Grotesk', sans-serif; cursor:pointer; }
    #ask button:disabled { opacity:.5; cursor:default; }`;
  document.head.append(css);

  const box = document.createElement('section');
  box.id = 'ask';
  box.innerHTML = `
    <h3>Ask about this idea</h3>
    <p class="note">Ask how to set it up, how it would fit your own job, or what could go wrong. This uses an online AI,
      so do not paste in real project documents: describe them, or use made-up examples.</p>
    <div class="chips">
      <button class="chip">Walk me through setting it up</button>
      <button class="chip">How would this work on a small project?</button>
      <button class="chip">What could go wrong?</button>
      <button class="chip">Help me explain it to my manager</button>
    </div>
    <div class="log"></div>
    <form><textarea placeholder="Your question" rows="2"></textarea><button class="send">Ask</button></form>`;
  main.insertBefore(box, main.querySelector('footer'));

  const log = box.querySelector('.log'), input = box.querySelector('textarea'), send = box.querySelector('.send');
  const history = [];
  const esc = s => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  // Just enough formatting for answers: paragraphs, lists, bold, inline code.
  function render(md) {
    const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|[^*\w])\*([^*\n]+?)\*(?!\*)/g, '$1<i>$2</i>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');
    let html = '', list = null, code = null;
    for (const line of md.split('\n')) {
      if (/^\s*```/.test(line)) {                     // fenced code: show as-is
        if (code === null) { if (list) { html += `</${list}>`; list = null; } code = []; }
        else { html += `<pre><code>${esc(code.join('\n'))}</code></pre>`; code = null; }
        continue;
      }
      if (code !== null) { code.push(line); continue; }
      const ol = line.match(/^\s*\d+[.)]\s+(.*)/), ul = line.match(/^\s*[-*•]\s+(.*)/);
      const kind = ol ? 'ol' : ul ? 'ul' : null;
      if (list && kind !== list) { html += `</${list}>`; list = null; }
      // Keep the writer's own numbering, so a list broken up by notes does not restart at 1.
      if (kind) { if (!list) { html += kind === 'ol' ? `<ol start="${parseInt(line, 10) || 1}">` : '<ul>'; list = kind; } html += `<li>${inline((ol || ul)[1])}</li>`; }
      else if (line.trim()) html += `<p>${inline(line.replace(/^#+\s*/, ''))}</p>`;
    }
    if (code !== null) html += `<pre><code>${esc(code.join('\n'))}</code></pre>`;
    return html + (list ? `</${list}>` : '');
  }
  function add(cls, html) { const d = document.createElement('div'); d.className = 'msg ' + cls; d.innerHTML = html; log.append(d); return d; }

  async function ask(q) {
    q = q.trim();
    if (!q || send.disabled) return;
    input.value = ''; send.disabled = true;
    add('me', esc(q));
    history.push({ role: 'user', content: q });
    const wait = add('ai', '<p class="note" style="margin:0">Thinking…</p>');
    try {
      const r = await fetch('/use-chat.php', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page, messages: history.slice(-12) }) });
      const data = await r.json().catch(() => ({}));
      if (!r.ok || !data.reply) throw new Error(data.error || `The chat is not available right now (${r.status}).`);
      wait.innerHTML = render(data.reply);
      history.push({ role: 'assistant', content: data.reply });
    } catch (e) {
      history.pop();
      wait.className = 'msg err'; wait.textContent = e.message;
    }
    send.disabled = false;
  }

  box.querySelectorAll('.chip').forEach(c => c.onclick = () => ask(c.textContent));
  box.querySelector('form').onsubmit = e => { e.preventDefault(); ask(input.value); };
  input.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(input.value); } };
})();
