const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = d => new Date(d + 'T00:00').toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric'});
let me = null;

async function api(url, opt = {}) {
  const r = await fetch(url, {headers: {'Content-Type': 'application/json'}, ...opt});
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(d.error || 'Request failed'), {problems: d.problems});
  return d;
}

// ---------- login / logout ----------
async function init() {
  try { me = (await api('/api/me')).user; showApp(); } catch { showLogin(); }
}
function showLogin() { $('#app').hidden = true; $('#login').hidden = false; }
$('#loginForm').onsubmit = async e => {
  e.preventDefault();
  $('#loginError').textContent = '';
  try {
    me = (await api('/api/login', {method: 'POST', body: JSON.stringify({email: $('#email').value, password: $('#password').value})})).user;
    $('#password').value = '';
    showApp();
  } catch (err) { $('#loginError').textContent = err.message; }
};
$('#logout').onclick = async () => { await api('/api/logout', {method: 'POST'}); me = null; showLogin(); };

function showApp() {
  $('#login').hidden = true; $('#app').hidden = false;
  $('#who').textContent = `${me.name} (${me.role.toLowerCase()})`;
  go(me.role === 'AGENT' ? 'tasks' : 'projects');
}

// ---------- navigation ----------
function go(k) {
  const tabs = [['projects', me.role === 'AGENT' ? 'Related projects' : 'Projects'], ['team', 'Team']];
  if (me.role === 'AGENT') tabs.unshift(['tasks', 'My tasks']);
  $('#nav').innerHTML = tabs.map(([key, label]) => `<button data-k="${key}" class="${key === k ? 'on' : ''}">${label}</button>`).join('');
  $('#nav').querySelectorAll('button').forEach(b => b.onclick = () => go(b.dataset.k));
  ({projects: viewProjects, tasks: viewTasks, team: viewTeam})[k]();
}

// ---------- projects ----------
function cards(list) {
  if (!list.length) return `<p class="muted">${me.role === 'ADMIN' ? 'No projects yet. Paste a meeting transcript above to create them.' : 'Nothing has been assigned to you yet.'}</p>`;
  return list.map(p => `<button class="card" data-id="${p.id}">
    <h3>${esc(p.name)}</h3>
    <dl><dt>Client</dt><dd>${esc(p.client_name)}</dd><dt>Manager</dt><dd>${esc(p.manager_name)}</dd>
    <dt>Deadline</dt><dd>${fmt(p.deadline)}</dd><dt>Tasks</dt><dd>${p.task_count}</dd></dl></button>`).join('');
}
async function loadCards() {
  const {projects} = await api('/api/projects');
  $('#cards').innerHTML = cards(projects);
  $('#cards').querySelectorAll('.card').forEach(c => c.onclick = () => openProject(c.dataset.id));
}
async function viewProjects() {
  $('#view').innerHTML = (me.role === 'ADMIN' ? `
    <section class="panel">
      <h2>Create from transcript</h2>
      <p class="muted">Paste the meeting transcript. Projects and tasks are created from the final decisions in it.</p>
      <textarea id="transcript" placeholder="Paste the meeting transcript here"></textarea>
      <div class="row">
        <button id="create" class="primary">Create from Transcript</button>
        <button id="reset">Clear all projects</button>
        <span id="msg" role="status"></span>
      </div>
      <ul id="problems" class="problems"></ul>
    </section>` : '') + `<h2>${me.role === 'MANAGER' ? 'Your projects' : 'Projects'}</h2><div class="cards" id="cards"></div>`;
  if (me.role === 'ADMIN') bindAdmin();
  loadCards();
}
function bindAdmin() {
  const msg = $('#msg'), probs = $('#problems');
  $('#create').onclick = async function () {
    const btn = this;
    btn.disabled = true; btn.textContent = 'Creating…';
    msg.className = 'muted'; msg.textContent = 'The AI is reading the transcript…'; probs.innerHTML = '';
    try {
      const r = await api('/api/create-from-transcript', {method: 'POST', body: JSON.stringify({transcript: $('#transcript').value})});
      msg.className = 'ok'; msg.textContent = `Created ${r.projects} projects with ${r.tasks} tasks.`;
      loadCards();
    } catch (e) {
      msg.className = 'error'; msg.textContent = e.message;
      probs.innerHTML = (e.problems || []).map(p => `<li>${esc(p)}</li>`).join('');
    } finally { btn.disabled = false; btn.textContent = 'Create from Transcript'; }
  };
  $('#reset').onclick = async () => {
    if (!confirm('Delete all projects and tasks?')) return;
    await api('/api/reset', {method: 'POST'});
    msg.className = 'muted'; msg.textContent = 'All projects cleared.'; loadCards();
  };
}

async function openProject(id) {
  try {
    const {project: p, tasks} = await api('/api/projects/' + id);
    $('#view').innerHTML = `<button class="back" id="back">Back to projects</button>
      <h2>${esc(p.name)}</h2><p>${esc(p.description)}</p>
      <div class="meta"><div><span>Client</span>${esc(p.client_name)}</div><div><span>Manager</span>${esc(p.manager_name)}</div>
      <div><span>Deadline</span>${fmt(p.deadline)}</div></div>
      <h3>Tasks</h3>${taskTable(tasks, false)}`;
    $('#back').onclick = () => go('projects');
  } catch (e) { $('#view').innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

// ---------- tasks ----------
function taskTable(tasks, showProject) {
  if (!tasks.length) return '<p class="muted">No tasks to show.</p>';
  return `<div class="tablewrap"><table><thead><tr><th>Task</th>${showProject ? '<th>Project</th>' : ''}<th>Description</th>
    <th>Assigned to</th><th>Deadline</th><th class="num">Hours</th></tr></thead><tbody>` +
    tasks.map(t => `<tr><td><strong>${esc(t.title)}</strong></td>${showProject ? `<td>${esc(t.project_name)}</td>` : ''}
    <td>${esc(t.description)}</td><td>${esc(t.assignee_name)}</td><td>${fmt(t.deadline)}</td><td class="num">${t.estimated_hours}</td></tr>`).join('') +
    '</tbody></table></div>';
}
async function viewTasks() {
  const {tasks} = await api('/api/my-tasks');
  $('#view').innerHTML = `<h2>My tasks</h2>${taskTable(tasks, true)}`;
}

// ---------- team ----------
async function viewTeam() {
  const {team} = await api('/api/team');
  $('#view').innerHTML = `<h2>Team directory</h2><div class="tablewrap"><table><thead><tr><th>Name</th><th>Role</th><th>Specialization</th></tr></thead><tbody>` +
    team.map(t => `<tr><td>${esc(t.name)}</td><td>${esc(t.role.toLowerCase())}</td><td>${esc(t.specialization)}</td></tr>`).join('') + '</tbody></table></div>';
}

init();
