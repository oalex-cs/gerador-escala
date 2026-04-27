/* ============================================================
   ESCALA DE CULTO — Frontend Logic
   Vanilla JS · Zero dependencies
   ============================================================ */

'use strict';

// ---------------------------------------------------------------
// State
// ---------------------------------------------------------------
let membros = [];        // [{nome, disponibilidades: []}]
let selectedMembro = null; // nome do membro selecionado
let currentSchedule = []; // escala gerada [{data, membro}]
let tempDates = [];      // datas temporárias no painel de disponibilidade

// ---------------------------------------------------------------
// DOM Refs
// ---------------------------------------------------------------
const formMembro       = document.getElementById('form-membro');
const inputNome        = document.getElementById('input-nome');
const memberList       = document.getElementById('member-list');
const badgeCount       = document.getElementById('badge-count');
const emptyState       = document.getElementById('empty-state');

const availPanel       = document.getElementById('avail-panel');
const availMemberName  = document.getElementById('avail-member-name');
const availHintName    = document.getElementById('avail-hint-name');
const datePicker       = document.getElementById('date-picker');
const dateList         = document.getElementById('date-list');
const datesEmptyState  = document.getElementById('dates-empty-state');
const btnAddDate       = document.getElementById('btn-add-date');
const btnSaveAvail     = document.getElementById('btn-save-avail');
const btnCloseAvail    = document.getElementById('btn-close-avail');
const selectPrompt     = document.getElementById('select-prompt');

const schedulePanel    = document.getElementById('schedule-panel');
const scheduleTbody    = document.getElementById('schedule-tbody');
const btnGerar         = document.getElementById('btn-gerar');
const btnExportCsv     = document.getElementById('btn-export-csv');
const btnExportXlsx    = document.getElementById('btn-export-xlsx');
const btnCloseSchedule = document.getElementById('btn-close-schedule');

// ---------------------------------------------------------------
// API Helpers
// ---------------------------------------------------------------
async function api(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== null) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.erro || 'Erro desconhecido');
  return data;
}

// ---------------------------------------------------------------
// Toast
// ---------------------------------------------------------------
function showToast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span class="toast-icon"></span><span>${msg}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('toast-out');
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ---------------------------------------------------------------
// Render Members
// ---------------------------------------------------------------
function renderMembers() {
  memberList.innerHTML = '';
  badgeCount.textContent = membros.length;

  if (membros.length === 0) {
    emptyState.classList.remove('hidden');
    return;
  }
  emptyState.classList.add('hidden');

  membros.forEach(m => {
    const li = document.createElement('li');
    li.className = 'member-item' + (m.nome === selectedMembro ? ' active' : '');
    li.dataset.nome = m.nome;

    const initial = m.nome.charAt(0).toUpperCase();
    const datesCount = m.disponibilidades.length;
    const datesLabel = datesCount === 0
      ? 'Sem datas definidas'
      : `${datesCount} data${datesCount > 1 ? 's' : ''} disponíve${datesCount > 1 ? 'is' : 'l'}`;

    li.innerHTML = `
      <div class="member-item-left">
        <div class="member-avatar">${initial}</div>
        <div class="member-info">
          <div class="member-name">${escapeHtml(m.nome)}</div>
          <div class="member-dates-count">${datesLabel}</div>
        </div>
      </div>
      <div class="member-actions">
        <button class="btn btn-danger btn-sm btn-delete" data-nome="${escapeHtml(m.nome)}" title="Remover membro">✕</button>
      </div>
    `;

    // Click no card → abrir painel de disponibilidade
    li.addEventListener('click', (e) => {
      if (e.target.closest('.btn-delete')) return;
      openAvailPanel(m.nome);
    });

    // Click no botão deletar
    li.querySelector('.btn-delete').addEventListener('click', (e) => {
      e.stopPropagation();
      deleteMembro(m.nome);
    });

    memberList.appendChild(li);
  });
}

// ---------------------------------------------------------------
// Availability Panel
// ---------------------------------------------------------------
function openAvailPanel(nome) {
  selectedMembro = nome;
  const membro = membros.find(m => m.nome === nome);
  if (!membro) return;

  tempDates = [...membro.disponibilidades];
  availMemberName.textContent = nome;
  availHintName.textContent = nome;

  // Esconder o prompt e mostrar o painel
  selectPrompt.classList.add('hidden');
  schedulePanel.classList.add('hidden');
  availPanel.classList.remove('hidden');

  renderDateList();
  renderMembers(); // atualiza active state
}

function closeAvailPanel() {
  selectedMembro = null;
  availPanel.classList.add('hidden');
  selectPrompt.classList.remove('hidden');
  renderMembers();
}

function renderDateList() {
  dateList.innerHTML = '';

  if (tempDates.length === 0) {
    datesEmptyState.classList.remove('hidden');
    return;
  }
  datesEmptyState.classList.add('hidden');

  const sorted = [...tempDates].sort();
  sorted.forEach(d => {
    const li = document.createElement('li');
    li.className = 'date-item';

    const dt = new Date(d + 'T12:00:00'); // evitar timezone offset
    const weekday = dt.toLocaleDateString('pt-BR', { weekday: 'long' });
    const formattedDate = dt.toLocaleDateString('pt-BR', {
      day: '2-digit', month: 'long', year: 'numeric'
    });

    li.innerHTML = `
      <span>
        <span class="date-item-label">${formattedDate}</span>
        <span class="date-item-weekday">(${weekday})</span>
      </span>
      <button class="date-item-remove" data-date="${d}" title="Remover data">✕</button>
    `;

    li.querySelector('.date-item-remove').addEventListener('click', () => {
      tempDates = tempDates.filter(x => x !== d);
      renderDateList();
    });

    dateList.appendChild(li);
  });
}

btnAddDate.addEventListener('click', () => {
  const d = datePicker.value;
  if (!d) { showToast('Selecione uma data.', 'error'); return; }

  const dt = new Date(d + 'T12:00:00');
  if (dt.getDay() !== 6) { // 6 = sábado (JS: 0=dom, 6=sáb)
    showToast('Apenas sábados são permitidos!', 'error');
    return;
  }
  if (tempDates.includes(d)) {
    showToast('Esta data já foi adicionada.', 'info');
    return;
  }
  tempDates.push(d);
  datePicker.value = '';
  renderDateList();
});

btnSaveAvail.addEventListener('click', async () => {
  if (!selectedMembro) return;
  try {
    btnSaveAvail.disabled = true;
    btnSaveAvail.innerHTML = '<span class="loading-spin">⏳</span> Salvando...';

    await api('PUT', `/api/membros/${encodeURIComponent(selectedMembro)}/disponibilidades`, {
      disponibilidades: tempDates,
    });

    // Atualiza localmente
    const m = membros.find(x => x.nome === selectedMembro);
    if (m) m.disponibilidades = [...tempDates];

    showToast('Disponibilidades salvas!', 'success');
    renderMembers();
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btnSaveAvail.disabled = false;
    btnSaveAvail.innerHTML = '💾 Salvar Disponibilidades';
  }
});

btnCloseAvail.addEventListener('click', closeAvailPanel);

// ---------------------------------------------------------------
// Add Member
// ---------------------------------------------------------------
formMembro.addEventListener('submit', async (e) => {
  e.preventDefault();
  const nome = inputNome.value.trim();
  if (!nome) return;

  try {
    inputNome.disabled = true;
    await api('POST', '/api/membros', { nome });
    membros.push({ nome, disponibilidades: [] });
    inputNome.value = '';
    renderMembers();
    showToast(`${nome} adicionado(a)!`, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    inputNome.disabled = false;
    inputNome.focus();
  }
});

// ---------------------------------------------------------------
// Delete Member
// ---------------------------------------------------------------
async function deleteMembro(nome) {
  if (!confirm(`Remover "${nome}" e todas as suas disponibilidades?`)) return;

  try {
    await api('DELETE', `/api/membros/${encodeURIComponent(nome)}`);
    membros = membros.filter(m => m.nome !== nome);

    if (selectedMembro === nome) {
      closeAvailPanel();
    }
    renderMembers();
    showToast(`${nome} removido(a).`, 'info');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ---------------------------------------------------------------
// Generate Schedule
// ---------------------------------------------------------------
btnGerar.addEventListener('click', async () => {
  try {
    btnGerar.disabled = true;
    btnGerar.innerHTML = '<span class="loading-spin">⚡</span> Gerando...';

    const escala = await api('POST', '/api/gerar-escala');
    currentSchedule = escala;

    // Esconder outros painéis direitos
    availPanel.classList.add('hidden');
    selectPrompt.classList.add('hidden');
    selectedMembro = null;
    renderMembers();

    renderSchedule(escala);
    schedulePanel.classList.remove('hidden');
    showToast('Escala gerada com sucesso!', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btnGerar.disabled = false;
    btnGerar.innerHTML = '<span class="btn-icon">⚡</span> Gerar Escala';
  }
});

function renderSchedule(escala) {
  scheduleTbody.innerHTML = '';
  const weekdays = ['Domingo', 'Segunda', 'Ter\u00e7a', 'Quarta', 'Quinta', 'Sexta', 'S\u00e1bado'];

  escala.forEach((row, i) => {
    const tr = document.createElement('tr');
    tr.className = 'schedule-row-anim';
    tr.style.animationDelay = `${i * 40}ms`;

    const dt = new Date(row.data + 'T12:00:00');
    const formattedDate = dt.toLocaleDateString('pt-BR', {
      day: '2-digit', month: '2-digit', year: 'numeric'
    });
    const weekday = weekdays[dt.getDay()];

    const membros = Array.isArray(row.membros) ? row.membros : [];
    const semNinguem = membros.length === 0;

    const membrosHtml = semNinguem
      ? '<span class="no-member">Sem dispon\u00edvel</span>'
      : membros.map(m => `<span class="member-pill">${escapeHtml(m)}</span>`).join('');

    tr.innerHTML = `
      <td>${formattedDate}</td>
      <td>${weekday}</td>
      <td class="members-cell">${membrosHtml}</td>
      <td style="text-align: right;">
        <button class="btn btn-ghost btn-sm" onclick="openEditModal(${i})" title="Editar esta data">
          \u270E
        </button>
      </td>
    `;
    scheduleTbody.appendChild(tr);
  });
}

btnCloseSchedule.addEventListener('click', () => {
  schedulePanel.classList.add('hidden');
  selectPrompt.classList.remove('hidden');
  currentSchedule = [];
});

// ---------------------------------------------------------------
// Export XLSX (pandas)
// ---------------------------------------------------------------
btnExportXlsx.addEventListener('click', async () => {
  if (currentSchedule.length === 0) return;

  try {
    btnExportXlsx.disabled = true;
    btnExportXlsx.innerHTML = '<span class="loading-spin">⏳</span> Gerando...';

    const res = await fetch('/api/exportar-xlsx', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentSchedule),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.erro || 'Erro ao gerar planilha');
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'escala_culto.xlsx';
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    showToast('Planilha Excel exportada! 📊', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btnExportXlsx.disabled = false;
    btnExportXlsx.innerHTML = '📊 Excel';
  }
});

// ---------------------------------------------------------------
// Export CSV
// ---------------------------------------------------------------
btnExportCsv.addEventListener('click', async () => {
  if (currentSchedule.length === 0) return;

  try {
    const res = await fetch('/api/exportar-csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentSchedule),
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'escala_culto.csv';
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    showToast('CSV exportado!', 'success');
  } catch (err) {
    showToast('Erro ao exportar CSV.', 'error');
  }
});

// ---------------------------------------------------------------
// Utils
// ---------------------------------------------------------------
function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------
// Init — carrega membros do backend
// ---------------------------------------------------------------
async function init() {
  try {
    membros = await api('GET', '/api/membros');
    renderMembers();
  } catch (err) {
    showToast('Erro ao carregar dados.', 'error');
  }
}

init();


// ---------------------------------------------------------------
// Modal de Edição da Escala
// ---------------------------------------------------------------
const editModal = document.getElementById('edit-modal');
const btnCloseModal = document.getElementById('btn-close-modal');
const btnSaveEdit = document.getElementById('btn-save-edit');
const editMembersList = document.getElementById('edit-members-list');
const editModalDate = document.getElementById('edit-modal-date');

let editingRowIndex = -1;

window.openEditModal = function(index) {
  editingRowIndex = index;
  const row = currentSchedule[index];
  
  // Format date
  const dt = new Date(row.data + 'T12:00:00');
  editModalDate.textContent = dt.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
  
  // Render members list
  editMembersList.innerHTML = '';
  const assigned = Array.isArray(row.membros) ? row.membros : [];
  
  membros.forEach(m => {
    const isChecked = assigned.includes(m.nome);
    const id = 'chk-' + m.nome.replace(/\s+/g, '-');
    
    const label = document.createElement('label');
    label.className = 'checkbox-item';
    label.innerHTML = `
      <input type="checkbox" id="${id}" value="${escapeHtml(m.nome)}" ${isChecked ? 'checked' : ''} />
      <span>${escapeHtml(m.nome)}</span>
    `;
    editMembersList.appendChild(label);
  });
  
  editModal.classList.remove('hidden');
};

btnCloseModal.addEventListener('click', () => {
  editModal.classList.add('hidden');
  editingRowIndex = -1;
});

btnSaveEdit.addEventListener('click', () => {
  if (editingRowIndex === -1) return;
  
  const checkboxes = editMembersList.querySelectorAll('input[type="checkbox"]');
  const selectedMembers = [];
  checkboxes.forEach(chk => {
    if (chk.checked) selectedMembers.push(chk.value);
  });
  
  currentSchedule[editingRowIndex].membros = selectedMembers;
  renderSchedule(currentSchedule);
  
  editModal.classList.add('hidden');
  editingRowIndex = -1;
  showToast('Escala editada com sucesso! Lembre-se de exportar para salvar.', 'success');
});


// ---------------------------------------------------------------
// Copiar Link
// ---------------------------------------------------------------
const btnCopyLink = document.getElementById('btn-copy-link');
if (btnCopyLink) {
  btnCopyLink.addEventListener('click', () => {
    const url = window.location.origin + '/membro';
    navigator.clipboard.writeText(url).then(() => {
      showToast('Link do formulário copiado! Pode colar no WhatsApp.', 'success');
    }).catch(() => {
      showToast('Erro ao copiar o link. Seu navegador pode não suportar isso.', 'error');
    });
  });
}
