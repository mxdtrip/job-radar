const feed = document.querySelector('#feed');
const statusEl = document.querySelector('#status');
const scoreEl = document.querySelector('#score');
const systemEl = document.querySelector('#system');

function money(v) {
  if (!v.salary_from && !v.salary_to) return 'зарплата не указана';
  const fmt = n => n ? new Intl.NumberFormat('ru-RU').format(n) : '';
  if (v.salary_from && v.salary_to) return `${fmt(v.salary_from)}–${fmt(v.salary_to)} ${v.currency || ''}`;
  if (v.salary_from) return `от ${fmt(v.salary_from)} ${v.currency || ''}`;
  return `до ${fmt(v.salary_to)} ${v.currency || ''}`;
}

async function loadSystem() {
  const [health, sources] = await Promise.all([
    fetch('/api/health').then(r => r.json()),
    fetch('/api/sources').then(r => r.json())
  ]);
  const ready = sources.filter(s => s.status === 'ready' && s.name !== 'mock').map(s => s.name).join(', ');
  const needs = sources.filter(s => s.status === 'needs_config').map(s => s.name).join(', ');
  systemEl.innerHTML = `
    <span>Scheduler: <b>${health.scheduler.running ? 'ON' : 'OFF'}</b> · ${health.scheduler.interval_minutes} мин</span>
    <span>LLM: <b>${health.llm_configured ? 'ON' : 'OFF'}</b></span>
    <span>Источники: ${ready || '—'}</span>
    ${needs ? `<span>Нужна настройка: ${needs}</span>` : ''}
  `;
}

async function load() {
  const min = Number(scoreEl.value || 0);
  const res = await fetch(`/api/vacancies?min_score=${min}`);
  const rows = await res.json();
  feed.innerHTML = rows.map(v => `
    <article class="card" data-id="${v.id}">
      <div>
        <div class="company">${v.company || 'Компания не указана'} · ${(v.sources || [v.source]).map(x => x.toUpperCase()).join(' + ')}</div>
        <h2 class="title">${v.title}</h2>
        <div class="meta">${v.location || 'локация не указана'} · ${money(v)}</div>
        <ul class="reasons">${(v.score_reasons || []).map(r => `<li>${r}</li>`).join('')}</ul>
      </div>
      <div class="score">${Math.round(v.score)}</div>
      <div class="card-actions">
        <a href="${v.url}" target="_blank" rel="noreferrer">Открыть вакансию ↗</a>
        <button class="dislike" onclick="feedback(${v.id}, 'dislike', this)">Не подходит</button>
        <button class="like" onclick="feedback(${v.id}, 'like', this)">Нравится</button>
      </div>
    </article>
  `).join('') || '<p>Нет вакансий по текущему фильтру.</p>';
  statusEl.textContent = `Найдено: ${rows.length}`;
}

async function feedback(id, action, btn) {
  const reason = action === 'dislike' ? (prompt('Почему не подходит? Можно оставить пустым.') || null) : null;
  await fetch(`/api/vacancies/${id}/feedback`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({action, reason})
  });
  const card = btn.closest('.card');
  card.style.opacity = '.35';
  setTimeout(() => card.remove(), 180);
}

async function sync(source) {
  statusEl.textContent = `Синхронизация ${source}…`;
  const res = await fetch(`/api/sync/${source}`, {method: 'POST'});
  const data = await res.json();
  statusEl.textContent = data.error ? `Ошибка ${source}: ${data.error}` : `${source}: +${data.inserted}, дублей ${data.duplicates}, обновлено ${data.updated}`;
  await Promise.all([load(), loadSystem()]);
}

async function syncAll() {
  statusEl.textContent = 'Синхронизация всех источников…';
  const res = await fetch('/api/sync-all', {method: 'POST'});
  const data = await res.json();
  const ok = (data.results || []).filter(x => !x.error).length;
  const errors = (data.results || []).filter(x => x.error).length;
  statusEl.textContent = `Готово: ${ok} источн., ошибок ${errors}`;
  await Promise.all([load(), loadSystem()]);
}

document.querySelector('#reload').onclick = load;
document.querySelector('#sync-mock').onclick = () => sync('mock');
document.querySelector('#sync-hh').onclick = () => sync('hh');
document.querySelector('#sync-all').onclick = syncAll;
scoreEl.onchange = load;
Promise.all([load(), loadSystem()]);
