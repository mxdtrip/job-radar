const feed = document.querySelector('#feed');
const statusEl = document.querySelector('#status');
const scoreEl = document.querySelector('#score');
const systemEl = document.querySelector('#system');
const onboarding = document.querySelector('#onboarding');
const onboardingForm = document.querySelector('#onboarding-form');
const onboardingError = document.querySelector('#onboarding-error');

function money(v) {
  if (!v.salary_from && !v.salary_to) return 'зарплата не указана';
  const fmt = n => n ? new Intl.NumberFormat('ru-RU').format(n) : '';
  if (v.salary_from && v.salary_to) return `${fmt(v.salary_from)}–${fmt(v.salary_to)} ${v.currency || ''}`;
  if (v.salary_from) return `от ${fmt(v.salary_from)} ${v.currency || ''}`;
  return `до ${fmt(v.salary_to)} ${v.currency || ''}`;
}

function parseList(value) {
  return [...new Set(value.split(/[\n,;]+/).map(x => x.trim()).filter(Boolean))];
}

function showOnboarding() {
  onboarding.classList.remove('hidden');
  onboarding.setAttribute('aria-hidden', 'false');
  document.body.classList.add('modal-open');
}

function hideOnboarding() {
  onboarding.classList.add('hidden');
  onboarding.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('modal-open');
}

async function fillOnboarding() {
  const pref = await fetch('/api/preferences').then(r => r.json());
  document.querySelector('#desired-terms').value = (pref.desired_terms || []).join(', ');
  document.querySelector('#locations').value = (pref.locations || []).join(', ');
  document.querySelector('#min-salary').value = pref.min_salary || '';
  document.querySelector('#remote-ok').checked = pref.remote_ok !== false;
  document.querySelector('#target-companies').value = (pref.target_companies || []).join(', ');
  document.querySelector('#excluded-terms').value = (pref.excluded_terms || []).join(', ');
  document.querySelector('#notes').value = pref.notes || '';
}

async function loadSystem() {
  const [health, sources] = await Promise.all([
    fetch('/api/health').then(r => r.json()),
    fetch('/api/sources').then(r => r.json())
  ]);
  const ready = sources.filter(s => s.status === 'ready' && s.name !== 'mock').map(s => s.name).join(', ');
  const needs = sources.filter(s => s.status === 'needs_config').map(s => s.name).join(', ');
  const errors = sources.filter(s => s.last_error).map(s => `${s.name}: ${s.last_error}`);
  systemEl.innerHTML = `
    <span>Scheduler: <b>${health.scheduler.running ? 'ON' : 'OFF'}</b> · ${health.scheduler.interval_minutes} мин</span>
    <span>LLM: <b>${health.llm_configured ? 'ON' : 'OFF'}</b></span>
    <span>Источники: ${ready || '—'}</span>
    ${needs ? `<span>Нужна настройка: ${needs}</span>` : ''}
    ${errors.length ? `<span class="source-error" title="${errors.join('\n').replaceAll('"', '&quot;')}">Есть ошибки источников: ${errors.length}</span>` : ''}
  `;
}

async function load() {
  const min = Number(scoreEl.value || 0);
  const [rows, stats] = await Promise.all([
    fetch(`/api/vacancies?min_score=${min}`).then(r => r.json()),
    fetch(`/api/stats?min_score=${min}`).then(r => r.json())
  ]);

  if (!rows.length) {
    let explanation = 'В базе пока нет вакансий. Настрой поиск и запусти полную синхронизацию.';
    if (stats.total > 0 && stats.unreviewed === 0) {
      explanation = `В базе ${stats.total} вакансий, но все уже оценены. Новые появятся после следующей синхронизации.`;
    } else if (stats.unreviewed > 0) {
      explanation = `В базе ${stats.unreviewed} непросмотренных вакансий, но ни одна не набрала score ≥ ${min}. Попробуй снизить порог.`;
    }
    feed.innerHTML = `<div class="empty-state"><h2>Лента пока пустая</h2><p>${explanation}</p><button onclick="openSettings()">Настроить поиск</button></div>`;
  } else {
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
    `).join('');
  }
  statusEl.textContent = `В ленте: ${rows.length} · в базе: ${stats.total}`;
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
  setTimeout(async () => {
    card.remove();
    await load();
  }, 180);
}

async function sync(source, full = false) {
  statusEl.textContent = `Синхронизация ${source}…`;
  const res = await fetch(`/api/sync/${source}?full=${full}`, {method: 'POST'});
  const data = await res.json();
  statusEl.textContent = data.error
    ? `Ошибка ${source}: ${data.error}`
    : `${source}: найдено ${data.fetched}, новых ${data.inserted}, дублей ${data.duplicates}, обновлено ${data.updated}`;
  await Promise.all([load(), loadSystem()]);
}

async function syncAll(full = false) {
  statusEl.textContent = full ? 'Собираю первую ленту…' : 'Синхронизация всех источников…';
  const res = await fetch(`/api/sync-all?full=${full}`, {method: 'POST'});
  const data = await res.json();
  const results = data.results || [];
  const ok = results.filter(x => !x.error).length;
  const errors = results.filter(x => x.error).length;
  const fetched = results.reduce((sum, x) => sum + (x.fetched || 0), 0);
  const inserted = results.reduce((sum, x) => sum + (x.inserted || 0), 0);
  statusEl.textContent = `Готово: найдено ${fetched}, новых ${inserted}, источников ${ok}, ошибок ${errors}`;
  await Promise.all([load(), loadSystem()]);
}

async function openSettings() {
  await fillOnboarding();
  showOnboarding();
}
window.openSettings = openSettings;

onboardingForm.addEventListener('submit', async event => {
  event.preventDefault();
  onboardingError.textContent = '';
  const desiredTerms = parseList(document.querySelector('#desired-terms').value);
  if (!desiredTerms.length) {
    onboardingError.textContent = 'Укажи хотя бы одну профессию или вариант названия вакансии.';
    return;
  }

  const salaryRaw = document.querySelector('#min-salary').value.trim();
  const payload = {
    desired_terms: desiredTerms,
    excluded_terms: parseList(document.querySelector('#excluded-terms').value),
    locations: parseList(document.querySelector('#locations').value),
    target_companies: parseList(document.querySelector('#target-companies').value),
    excluded_companies: [],
    min_salary: salaryRaw ? Number(salaryRaw) : null,
    remote_ok: document.querySelector('#remote-ok').checked,
    notes: document.querySelector('#notes').value.trim()
  };

  const response = await fetch('/api/preferences', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const error = await response.json();
    onboardingError.textContent = error.detail || 'Не удалось сохранить настройки.';
    return;
  }

  localStorage.setItem('jobRadarOnboardingV1', 'done');
  hideOnboarding();
  await syncAll(true);
});

document.querySelector('#reload').onclick = load;
document.querySelector('#settings').onclick = openSettings;
document.querySelector('#sync-hh').onclick = () => sync('hh', false);
document.querySelector('#sync-all').onclick = () => syncAll(false);
document.querySelector('#close-onboarding').onclick = hideOnboarding;
scoreEl.onchange = load;

Promise.all([load(), loadSystem(), fillOnboarding()]).then(() => {
  if (localStorage.getItem('jobRadarOnboardingV1') !== 'done') showOnboarding();
});
