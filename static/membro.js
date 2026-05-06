document.addEventListener('DOMContentLoaded', () => {
  const saturdaysList = document.getElementById('saturdays-list');
  const btnSubmit = document.getElementById('btn-submit');
  const inputNome = document.getElementById('nome-membro');
  const inputWhatsapp = document.getElementById('whatsapp-membro');
  const formView = document.getElementById('form-view');
  const successView = document.getElementById('success-view');
  const subtitle = document.querySelector('.hero-subtitle');

  function getNext5Saturdays() {
    const dates = [];
    const d = new Date();
    d.setDate(d.getDate() + (6 - d.getDay() + 7) % 7);

    for (let i = 0; i < 5; i++) {
      dates.push(new Date(d));
      d.setDate(d.getDate() + 7);
    }
    return dates;
  }

  async function getCampaignSaturdays() {
    try {
      const res = await fetch('/api/campanha-publica');
      if (!res.ok) throw new Error('Campanha indisponivel.');
      const payload = await res.json();
      const campaign = payload.campanha;
      if (!campaign || !Array.isArray(campaign.sabados) || campaign.sabados.length === 0) {
        throw new Error('Campanha sem sabados.');
      }
      if (subtitle) {
        subtitle.textContent = `Informe quais sabados voce pode servir em ${campaign.nome}.`;
      }
      return campaign.sabados.map(d => new Date(d + 'T12:00:00'));
    } catch (err) {
      if (subtitle) {
        subtitle.textContent = 'Informe quais sabados voce pode servir nas proximas semanas.';
      }
      return getNext5Saturdays();
    }
  }

  function renderSaturdays(saturdays) {
    const months = [
      'Janeiro', 'Fevereiro', 'Marco', 'Abril', 'Maio', 'Junho',
      'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
    ];

    saturdaysList.innerHTML = '';
    saturdays.forEach((date, i) => {
      const isoDate = date.toISOString().split('T')[0];
      const day = String(date.getDate()).padStart(2, '0');
      const month = months[date.getMonth()];
      const year = date.getFullYear();

      const label = document.createElement('label');
      label.className = 'checkbox-item-large';
      label.innerHTML = `
        <div class="date-info">
          <span class="date-day">Sabado, ${day}</span>
          <span class="date-month">de ${month} de ${year}</span>
        </div>
        <input type="checkbox" value="${isoDate}" id="chk-${i}" />
      `;
      saturdaysList.appendChild(label);
    });
  }

  function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span class="toast-icon"></span> <span>${message}</span>`;

    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('toast-out');
      setTimeout(() => toast.remove(), 300);
    }, 3000);
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

  btnSubmit.addEventListener('click', async () => {
    const nome = inputNome.value.trim();
    const whatsapp = inputWhatsapp.value.trim();
    if (!nome) {
      showToast('Por favor, digite seu nome.', 'error');
      inputNome.focus();
      return;
    }
    if (!isValidWhatsapp(whatsapp)) {
      showToast('Informe seu WhatsApp com DDD.', 'error');
      inputWhatsapp.focus();
      return;
    }

    const checkboxes = saturdaysList.querySelectorAll('input[type="checkbox"]:checked');
    const disponibilidades = Array.from(checkboxes).map(chk => chk.value);

    try {
      btnSubmit.disabled = true;
      btnSubmit.innerHTML = 'Enviando...';

      const res = await fetch('/api/membro/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nome, whatsapp, disponibilidades })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.erro || 'Erro ao salvar disponibilidade.');
      }

      formView.classList.add('hidden');
      successView.classList.remove('hidden');
    } catch (error) {
      showToast(error.message, 'error');
      btnSubmit.disabled = false;
      btnSubmit.innerHTML = 'Enviar Disponibilidade';
    }
  });

  getCampaignSaturdays().then(renderSaturdays);
});
