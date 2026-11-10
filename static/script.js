// Логіка сторінки: надсилання тексту на сервер Flask і показ результату
const $ = (id) => document.getElementById(id);
const form = $('form'), textEl = $('text'), btn = $('submit'), errorEl = $('error');
const history = [];

textEl.addEventListener('input', () => { $('count').textContent = textEl.value.length; });

// Кнопки-приклади підставляють текст у поле
document.querySelectorAll('.chip').forEach((chip) => {
  chip.addEventListener('click', () => {
    textEl.value = chip.textContent;
    $('count').textContent = textEl.value.length;
    textEl.focus();
  });
});

function showError(message) {
  errorEl.textContent = '⚠️ ' + message;
  errorEl.hidden = false;
}

function setLoading(on) {
  btn.disabled = on;
  btn.classList.toggle('loading', on);
  btn.querySelector('.btn-text').textContent = on ? 'ШІ аналізує текст...' : 'Визначити емоцію';
}

function render(r) {
  $('r-emoji').textContent = r.emoji;
  $('r-emotion').textContent = r.emotion;
  $('r-secondary').innerHTML = '';
  r.secondary.forEach((s) => {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = `${s.emoji} ${s.emotion}`;
    $('r-secondary').appendChild(tag);
  });
  $('r-conf').textContent = r.confidence + ' %';
  $('r-bar').style.width = '0';
  requestAnimationFrame(() => { $('r-bar').style.width = r.confidence + '%'; });
  $('r-explanation').textContent = r.explanation;
  $('r-advice').textContent = r.advice;
  $('r-quote').textContent = '“' + r.quote + '”';
  $('r-meta').textContent = `Модель: ${r.model} · ${(r.time_ms / 1000).toFixed(1)} с`;
  $('result').hidden = false;
  $('result').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function addToHistory(text, r) {
  history.unshift({ text, r });
  if (history.length > 5) history.pop();
  const list = $('history');
  list.innerHTML = '';
  history.forEach((item) => {
    const li = document.createElement('li');
    li.innerHTML = '<span class="h-emoji"></span><span class="h-text"></span>';
    li.querySelector('.h-emoji').textContent = item.r.emoji;
    li.querySelector('.h-text').textContent = item.text;
    li.title = 'Показати цей результат';
    li.addEventListener('click', () => render(item.r));
    list.appendChild(li);
  });
  $('history-wrap').hidden = false;
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  errorEl.hidden = true;
  const text = textEl.value.trim();
  if (!text) { showError('Введіть текст для аналізу.'); return; }

  setLoading(true);
  try {
    const res = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const data = await res.json().catch(() => ({ error: 'Сервер повернув неочікувану відповідь.' }));
    if (!res.ok) { showError(data.error || 'Сталася помилка.'); return; }
    render(data);
    addToHistory(text, data);
  } catch (err) {
    showError("Немає з'єднання з сервером. Перевірте інтернет і спробуйте ще раз.");
  } finally {
    setLoading(false);
  }
});

// Ctrl+Enter – швидке надсилання
textEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) form.requestSubmit();
});
