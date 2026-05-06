/* ============================================================
   ESCALA DE CULTO - Frontend Logic
   Vanilla JS - Zero dependencies
   ============================================================ */

'use strict';

// ---------------------------------------------------------------
// State
// ---------------------------------------------------------------
let membros = [];
let campanhas = [];
let activeCampaign = null;
let selectedMembro = null;
let currentSchedule = [];
let currentScheduleCampaignId = null;
let currentScheduleUpdatedAt = null;
let tempDates = [];

// ---------------------------------------------------------------
// DOM Refs
// ---------------------------------------------------------------
const formMembro       = document.getElementById('form-membro');
const inputNome        = document.getElementById('input-nome');
const inputWhatsapp    = document.getElementById('input-whatsapp');
const memberList       = document.getElementById('member-list');
const badgeCount       = document.getElementById('badge-count');
const emptyState       = document.getElementById('empty-state');

const activeCampaignBadge = document.getElementById('active-campaign-badge');
const activeCampaignTitle = document.getElementById('active-campaign-title');
const activeCampaignMeta  = document.getElementById('active-campaign-meta');
const campaignMonth       = document.getElementById('campaign-month');
const btnSaveCampaign     = document.getElementById('btn-save-campaign');
const btnResetResponses   = document.getElementById('btn-reset-responses');
const campaignList        = document.getElementById('campaign-list');

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
const scheduleTitle    = document.getElementById('schedule-title');
const scheduleMeta     = document.getElementById('schedule-meta');
const scheduleTbody    = document.getElementById('schedule-tbody');
const btnGerar         = document.getElementById('btn-gerar');
const btnSaveSchedule  = document.getElementById('btn-save-schedule');
const btnExportCsv     = document.getElementById('btn-export-csv');
const btnExportXlsx    = document.getElementById('btn-export-xlsx');
const btnCloseSchedule = document.getElementById('btn-close-schedule');

const editModal       = document.getElementById('edit-modal');
const btnCloseModal   = document.getElementById('btn-close-modal');
const btnSaveEdit     = document.getElementById('btn-save-edit');
const editMembersList = document.getElementById('edit-members-list');
const editModalDate   = document.getElementById('edit-modal-date');

let editingRowIndex = -1;

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
  const data = await res.json().catch(() => ({}));

  if (res.status === 401) {
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
    throw new Error('Autenticacao necessaria.');
  }

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
  toast.innerHTML = `<span class="toast-icon"></span><span>${escapeHtml(msg)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('toast-out');
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ---------------------------------------------------------------
// Campaigns
// ---------------------------------------------------------------
async function loadCampaigns() {
  const payload = await api('GET', '/api/campanhas');
  campanhas = payload.campanhas || [];
  activeCampaign = payload.ativa || null;
  renderCampaigns();
}

function renderCampaigns() {
  if (!activeCampaign) {
    activeCampaignBadge.textContent = '--';
    activeCampaignTitle.textContent = 'Nenhuma campanha ativa';
    activeCampaignMeta.textContent = 'Selecione um mes para comecar.';
    return;
  }

  const sabados = activeCampaign.sabados || [];
  const respostas = activeCampaign.respostas_count || 0;
  activeCampaignBadge.textContent = activeCampaign.id;
  activeCampaignTitle.textContent = activeCampaign.nome;
  activeCampaignMeta.textContent =
    `${sabados.length} sabado${sabados.length === 1 ? '' : 's'} no periodo - ` +
    `${respostas} resposta${respostas === 1 ? '' : 's'}` +
    (activeCampaign.tem_escala ? ' - escala salva' : ' - sem escala salva');
  campaignMonth.value = activeCampaign.id;

  if (datePicker && sabados.length > 0) {
    datePicker.min = sabados[0];
    datePicker.max = sabados[sabados.length - 1];
  }

  campaignList.innerHTML = '';
  campanhas.forEach(campaign => {
    const li = document.createElement('li');
    li.className = 'campaign-item' + (campaign.id === activeCampaign.id ? ' active' : '');

    const count = campaign.respostas_count || 0;
    const status = `${count} resposta${count === 1 ? '' : 's'} - ${campaign.tem_escala ? 'Escala salva' : 'Sem escala'}`;
    const buttonLabel = campaign.id === activeCampaign.id ? 'Abrir' : 'Ativar';

    li.innerHTML = `
      <div class="campaign-item-info">
        <div class="campaign-item-title">${escapeHtml(campaign.nome)}</div>
        <div class="campaign-item-meta">${escapeHtml(status)}</div>
      </div>
      <button type="button" class="btn btn-ghost btn-sm btn-open-campaign" data-campaign-id="${escapeHtml(campaign.id)}">
        ${buttonLabel}
      </button>
    `;

    li.querySelector('.btn-open-campaign').addEventListener('click', () => {
      activateCampaign(campaign.id);
    });

    campaignList.appendChild(li);
  });
}

async function activateCampaign(campaignId) {
  try {
    await api('POST', `/api/campanhas/${encodeURIComponent(campaignId)}/ativar`);
    await loadCampaigns();
    await loadScheduleForCampaign(campaignId, { showWhenFound: true });
    showToast('Campanha ativa atualizada.', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

btnSaveCampaign.addEventListener('click', async () => {
  const mes = campaignMonth.value;
  if (!mes) {
    showToast('Selecione um mes.', 'error');
    return;
  }

  const message = 'Ativar esta campanha vai limpar disponibilidades de outros meses para evitar duplicidade. Continuar?';
  if (!confirm(message)) return;

  try {
    btnSaveCampaign.disabled = true;
    const payload = await api('POST', '/api/campanhas', { mes });
    await loadCampaigns();
    membros = await api('GET', '/api/membros');
    renderMembers();
    await loadScheduleForCampaign(mes, { showWhenFound: true });
    const removed = payload.limpeza ? payload.limpeza.datas_removidas : 0;
    showToast(removed > 0 ? `Campanha ativada. ${removed} data(s) antiga(s) removida(s).` : 'Campanha ativada.', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btnSaveCampaign.disabled = false;
  }
});

btnResetResponses.addEventListener('click', async () => {
  if (!activeCampaign) {
    showToast('Ative uma campanha primeiro.', 'error');
    return;
  }

  const message = `Zerar todas as respostas de disponibilidade de ${activeCampaign.nome}? Membros e escalas salvas serao mantidos.`;
  if (!confirm(message)) return;

  try {
    btnResetResponses.disabled = true;
    const payload = await api('POST', `/api/campanhas/${encodeURIComponent(activeCampaign.id)}/zerar-respostas`);
    await loadCampaigns();
    membros = await api('GET', '/api/membros');
    renderMembers();
    const removed = payload.limpeza ? payload.limpeza.datas_removidas : 0;
    showToast(removed > 0 ? `${removed} data(s) de disponibilidade removida(s).` : 'Nao havia respostas para zerar.', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btnResetResponses.disabled = false;
  }
});

// ---------------------------------------------------------------
// Members
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
    const memberId = memberIdentifier(m);
    const li = document.createElement('li');
    li.className = 'member-item' + (memberId === selectedMembro ? ' active' : '');
    li.dataset.memberId = memberId;

    const initial = m.nome.charAt(0).toUpperCase();
    const phoneLabel = formatWhatsapp(m.whatsapp || m.whatsapp_key);
    const datesCount = Array.isArray(m.disponibilidades) ? m.disponibilidades.length : 0;
    const datesLabel = datesCount === 0
      ? 'Sem datas definidas'
      : `${datesCount} data${datesCount > 1 ? 's' : ''} disponivel${datesCount > 1 ? 's' : ''}`;
    const metaLabel = datesLabel;

    li.innerHTML = `
      <div class="member-item-left">
        <div class="member-avatar">${escapeHtml(initial)}</div>
        <div class="member-info">
          <div class="member-name">${escapeHtml(m.nome)}</div>
          <div class="member-dates-count">
            ${phoneLabel ? `<span class="member-phone">${escapeHtml(phoneLabel)}</span>` : ''}
            <span>${escapeHtml(metaLabel)}</span>
          </div>
        </div>
      </div>
      <div class="member-actions">
        <button class="btn btn-danger btn-sm btn-delete" data-member-id="${escapeHtml(memberId)}" title="Remover membro">x</button>
      </div>
    `;

    li.addEventListener('click', (e) => {
      if (e.target.closest('.btn-delete')) return;
      openAvailPanel(memberId);
    });

    li.querySelector('.btn-delete').addEventListener('click', (e) => {
      e.stopPropagation();
      deleteMembro(memberId);
    });

    memberList.appendChild(li);
  });
}

// ---------------------------------------------------------------
// Availability Panel
// ---------------------------------------------------------------
function openAvailPanel(memberId) {
  selectedMembro = memberId;
  const membro = membros.find(m => memberIdentifier(m) === memberId);
  if (!membro) return;

  tempDates = [...(membro.disponibilidades || [])];
  availMemberName.textContent = formatMemberNameWithPhone(membro);
  availHintName.textContent = membro.nome;

  selectPrompt.classList.add('hidden');
  schedulePanel.classList.add('hidden');
  availPanel.classList.remove('hidden');

  renderDateList();
  renderMembers();
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

  [...tempDates].sort().forEach(d => {
    const li = document.createElement('li');
    li.className = 'date-item';

    const dt = new Date(d + 'T12:00:00');
    const weekday = dt.toLocaleDateString('pt-BR', { weekday: 'long' });
    const formattedDate = dt.toLocaleDateString('pt-BR', {
      day: '2-digit', month: 'long', year: 'numeric'
    });

    li.innerHTML = `
      <span>
        <span class="date-item-label">${escapeHtml(formattedDate)}</span>
        <span class="date-item-weekday">(${escapeHtml(weekday)})</span>
      </span>
      <button class="date-item-remove" data-date="${escapeHtml(d)}" title="Remover data">x</button>
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
  if (dt.getDay() !== 6) {
    showToast('Apenas sabados sao permitidos.', 'error');
    return;
  }
  if (tempDates.includes(d)) {
    showToast('Esta data ja foi adicionada.', 'info');
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
    btnSaveAvail.innerHTML = '<span class="loading-spin">...</span> Salvando...';

    await api('PUT', `/api/membros/${encodeURIComponent(selectedMembro)}/disponibilidades`, {
      disponibilidades: tempDates,
    });

    const m = membros.find(x => memberIdentifier(x) === selectedMembro);
    if (m) m.disponibilidades = [...tempDates];

    showToast('Disponibilidades salvas.', 'success');
    renderMembers();
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btnSaveAvail.disabled = false;
    btnSaveAvail.innerHTML = 'Salvar Disponibilidades';
  }
});

btnCloseAvail.addEventListener('click', closeAvailPanel);

formMembro.addEventListener('submit', async (e) => {
  e.preventDefault();
  const nome = inputNome.value.trim();
  const whatsapp = inputWhatsapp.value.trim();
  if (!nome) {
    showToast('Informe o nome completo.', 'error');
    inputNome.focus();
    return;
  }
  if (!isValidWhatsapp(whatsapp)) {
    showToast('Informe o WhatsApp com DDD.', 'error');
    inputWhatsapp.focus();
    return;
  }

  try {
    inputNome.disabled = true;
    inputWhatsapp.disabled = true;
    const payload = await api('POST', '/api/membros', { nome, whatsapp });
    const savedMember = payload.membro || { nome, whatsapp, disponibilidades: [] };
    const savedId = memberIdentifier(savedMember);
    const existingIndex = membros.findIndex(m => memberIdentifier(m) === savedId);
    if (existingIndex >= 0) {
      membros[existingIndex] = savedMember;
    } else {
      membros.push(savedMember);
    }
    inputNome.value = '';
    inputWhatsapp.value = '';
    renderMembers();
    showToast(`${nome} adicionado(a).`, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    inputNome.disabled = false;
    inputWhatsapp.disabled = false;
    inputNome.focus();
  }
});

async function deleteMembro(memberId) {
  const member = membros.find(m => memberIdentifier(m) === memberId);
  if (!member) return;
  if (!confirm(`Remover "${member.nome}" e todas as suas disponibilidades?`)) return;

  try {
    await api('DELETE', `/api/membros/${encodeURIComponent(memberId)}`);
    membros = membros.filter(m => memberIdentifier(m) !== memberId);

    if (selectedMembro === memberId) closeAvailPanel();
    renderMembers();
    showToast(`${member.nome} removido(a).`, 'info');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ---------------------------------------------------------------
// Schedules
// ---------------------------------------------------------------
async function loadScheduleForCampaign(campaignId, options = {}) {
  const { showWhenFound = false } = options;
  try {
    const payload = await api('GET', `/api/campanhas/${encodeURIComponent(campaignId)}/escala`);
    activeCampaign = payload.campanha || activeCampaign;

    if (payload.escala) {
      currentSchedule = payload.escala.itens || [];
      currentScheduleCampaignId = payload.escala.campanha_id;
      currentScheduleUpdatedAt = payload.escala.updated_at;
      renderSchedule(currentSchedule);
      if (showWhenFound) showSchedulePanel();
    } else if (showWhenFound) {
      clearScheduleView();
      showToast('Esta campanha ainda nao tem escala salva.', 'info');
    }

    renderCampaigns();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function applySchedulePayload(payload) {
  activeCampaign = payload.campanha || activeCampaign;
  const escala = payload.escala;
  currentSchedule = escala ? (escala.itens || []) : [];
  currentScheduleCampaignId = escala ? escala.campanha_id : (activeCampaign && activeCampaign.id);
  currentScheduleUpdatedAt = escala ? escala.updated_at : null;
  renderSchedule(currentSchedule);
  showSchedulePanel();
}

btnGerar.addEventListener('click', async () => {
  if (!activeCampaign) {
    showToast('Ative uma campanha antes de gerar a escala.', 'error');
    return;
  }

  try {
    btnGerar.disabled = true;
    btnGerar.innerHTML = '<span class="loading-spin">...</span> Gerando...';

    const payload = await api('POST', `/api/campanhas/${encodeURIComponent(activeCampaign.id)}/gerar-escala`);
    applySchedulePayload(payload);
    await loadCampaigns();
    showToast('Escala gerada e salva.', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btnGerar.disabled = false;
    btnGerar.innerHTML = 'Gerar Escala';
  }
});

function renderSchedule(escala) {
  scheduleTbody.innerHTML = '';
  const weekdays = ['Domingo', 'Segunda', 'Terca', 'Quarta', 'Quinta', 'Sexta', 'Sabado'];

  scheduleTitle.textContent = activeCampaign ? `Escala - ${activeCampaign.nome}` : 'Escala Gerada';
  scheduleMeta.textContent = currentScheduleUpdatedAt
    ? `Salva em ${formatDateTime(currentScheduleUpdatedAt)}`
    : 'Ainda nao salva.';

  escala.forEach((row, i) => {
    const tr = document.createElement('tr');
    tr.className = 'schedule-row-anim';
    tr.style.animationDelay = `${i * 40}ms`;

    const dt = new Date(row.data + 'T12:00:00');
    const formattedDate = dt.toLocaleDateString('pt-BR', {
      day: '2-digit', month: '2-digit', year: 'numeric'
    });
    const weekday = weekdays[dt.getDay()];

    const membrosRow = Array.isArray(row.membros) ? row.membros : [];
    const semNinguem = membrosRow.length === 0;

    const membrosHtml = semNinguem
      ? '<span class="no-member">Sem disponivel</span>'
      : membrosRow.map(m => `<span class="member-pill">${escapeHtml(m)}</span>`).join('');

    tr.innerHTML = `
      <td>${escapeHtml(formattedDate)}</td>
      <td>${escapeHtml(weekday)}</td>
      <td class="members-cell">${membrosHtml}</td>
      <td style="text-align: right;">
        <button class="btn btn-ghost btn-sm" onclick="openEditModal(${i})" title="Editar esta data">
          Editar
        </button>
      </td>
    `;
    scheduleTbody.appendChild(tr);
  });
}

function showSchedulePanel() {
  availPanel.classList.add('hidden');
  selectPrompt.classList.add('hidden');
  schedulePanel.classList.remove('hidden');
  selectedMembro = null;
  renderMembers();
}

function clearScheduleView() {
  currentSchedule = [];
  currentScheduleCampaignId = null;
  currentScheduleUpdatedAt = null;
  schedulePanel.classList.add('hidden');
  selectPrompt.classList.remove('hidden');
}

async function saveCurrentSchedule(options = {}) {
  const { silent = false } = options;
  if (!currentScheduleCampaignId || currentSchedule.length === 0) {
    if (!silent) showToast('Nao ha escala para salvar.', 'error');
    return false;
  }

  try {
    btnSaveSchedule.disabled = true;
    const payload = await api('PUT', `/api/campanhas/${encodeURIComponent(currentScheduleCampaignId)}/escala`, {
      itens: currentSchedule,
    });
    applySchedulePayload(payload);
    await loadCampaigns();
    if (!silent) showToast('Escala salva.', 'success');
    return true;
  } catch (err) {
    showToast(err.message, 'error');
    return false;
  } finally {
    btnSaveSchedule.disabled = false;
  }
}

btnSaveSchedule.addEventListener('click', () => {
  saveCurrentSchedule();
});

btnCloseSchedule.addEventListener('click', () => {
  clearScheduleView();
});

// ---------------------------------------------------------------
// Export
// ---------------------------------------------------------------
btnExportXlsx.addEventListener('click', async () => {
  if (currentSchedule.length === 0) return;

  try {
    btnExportXlsx.disabled = true;
    btnExportXlsx.innerHTML = '<span class="loading-spin">...</span> Gerando...';

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
    downloadBlob(blob, `escala_${currentScheduleCampaignId || 'culto'}.xlsx`);
    showToast('Planilha Excel exportada.', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btnExportXlsx.disabled = false;
    btnExportXlsx.innerHTML = 'Excel';
  }
});

btnExportCsv.addEventListener('click', async () => {
  if (currentSchedule.length === 0) return;

  try {
    const res = await fetch('/api/exportar-csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentSchedule),
    });
    const blob = await res.blob();
    downloadBlob(blob, `escala_${currentScheduleCampaignId || 'culto'}.csv`);
    showToast('CSV exportado.', 'success');
  } catch (err) {
    showToast('Erro ao exportar CSV.', 'error');
  }
});

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---------------------------------------------------------------
// Edit Schedule Modal
// ---------------------------------------------------------------
window.openEditModal = function(index) {
  editingRowIndex = index;
  const row = currentSchedule[index];
  if (!row) return;

  const dt = new Date(row.data + 'T12:00:00');
  editModalDate.textContent = dt.toLocaleDateString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric'
  });

  editMembersList.innerHTML = '';
  const assigned = Array.isArray(row.membros) ? row.membros : [];

  membros.forEach((m, memberIndex) => {
    const labelValue = memberScheduleLabel(m);
    const isChecked = assigned.includes(labelValue) || assigned.includes(m.nome);
    const id = `chk-${index}-${memberIndex}`;

    const label = document.createElement('label');
    label.className = 'checkbox-item';
    label.innerHTML = `
      <input type="checkbox" id="${id}" value="${escapeHtml(labelValue)}" ${isChecked ? 'checked' : ''} />
      <span>${escapeHtml(formatMemberNameWithPhone(m))}</span>
    `;
    editMembersList.appendChild(label);
  });

  editModal.classList.remove('hidden');
};

btnCloseModal.addEventListener('click', () => {
  editModal.classList.add('hidden');
  editingRowIndex = -1;
});

btnSaveEdit.addEventListener('click', async () => {
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
  const saved = await saveCurrentSchedule({ silent: true });
  if (saved) showToast('Escala editada e salva.', 'success');
});

// ---------------------------------------------------------------
// Copy Link
// ---------------------------------------------------------------
const btnCopyLink = document.getElementById('btn-copy-link');
if (btnCopyLink) {
  btnCopyLink.addEventListener('click', () => {
    const url = window.location.origin + '/membro';
    navigator.clipboard.writeText(url).then(() => {
      showToast('Link do formulario copiado.', 'success');
    }).catch(() => {
      showToast('Erro ao copiar o link.', 'error');
    });
  });
}

// ---------------------------------------------------------------
// Utils
// ---------------------------------------------------------------
function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function normalizeWhatsapp(value) {
  let digits = String(value || '').replace(/\D/g, '');
  if (digits.startsWith('55') && (digits.length === 12 || digits.length === 13)) {
    digits = digits.slice(2);
  }
  if (digits.startsWith('0') && (digits.length === 11 || digits.length === 12)) {
    digits = digits.slice(1);
  }
  return digits;
}

function isValidWhatsapp(value) {
  const digits = normalizeWhatsapp(value);
  return digits.length === 10 || digits.length === 11;
}

function formatWhatsapp(value) {
  const digits = normalizeWhatsapp(value);
  if (digits.length === 11) {
    return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`;
  }
  if (digits.length === 10) {
    return `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`;
  }
  return digits;
}

function memberIdentifier(member) {
  return member.id || member.whatsapp_key || member.whatsapp || member.nome;
}

function normalizeNameKey(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ');
}

function memberScheduleLabel(member) {
  const nameKey = normalizeNameKey(member.nome);
  const duplicates = membros.filter(m => normalizeNameKey(m.nome) === nameKey);
  if (duplicates.length <= 1) return member.nome;
  const suffix = normalizeWhatsapp(member.whatsapp || member.whatsapp_key).slice(-4);
  return suffix ? `${member.nome} (${suffix})` : member.nome;
}

function formatMemberNameWithPhone(member) {
  const phone = formatWhatsapp(member.whatsapp || member.whatsapp_key);
  return phone ? `${member.nome} - ${phone}` : member.nome;
}

function formatDateTime(isoString) {
  if (!isoString) return '';
  const dt = new Date(isoString);
  if (Number.isNaN(dt.getTime())) return isoString;
  return dt.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ---------------------------------------------------------------
// Init
// ---------------------------------------------------------------
async function init() {
  try {
    const [membersData] = await Promise.all([
      api('GET', '/api/membros'),
      loadCampaigns(),
    ]);

    membros = membersData;
    renderMembers();

    if (activeCampaign && activeCampaign.tem_escala) {
      await loadScheduleForCampaign(activeCampaign.id, { showWhenFound: true });
    }
  } catch (err) {
    showToast('Erro ao carregar dados.', 'error');
  }
}

init();
