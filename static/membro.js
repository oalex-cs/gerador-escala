document.addEventListener('DOMContentLoaded', () => {
  const saturdaysList = document.getElementById('saturdays-list');
  const btnSubmit = document.getElementById('btn-submit');
  const inputNome = document.getElementById('nome-membro');
  const formView = document.getElementById('form-view');
  const successView = document.getElementById('success-view');

  // Gerar os próximos 5 sábados
  function getNext5Saturdays() {
    const dates = [];
    let d = new Date();
    // Encontrar o próximo sábado (ou hoje se for sábado)
    d.setDate(d.getDate() + (6 - d.getDay() + 7) % 7);
    
    for (let i = 0; i < 5; i++) {
      dates.push(new Date(d));
      d.setDate(d.getDate() + 7);
    }
    return dates;
  }

  const saturdays = getNext5Saturdays();
  
  const months = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];

  saturdays.forEach((date, i) => {
    const isoDate = date.toISOString().split('T')[0];
    const day = String(date.getDate()).padStart(2, '0');
    const month = months[date.getMonth()];
    const year = date.getFullYear();
    
    const label = document.createElement('label');
    label.className = 'checkbox-item-large';
    label.innerHTML = `
      <div class="date-info">
        <span class="date-day">Sábado, ${day}</span>
        <span class="date-month">de ${month} de ${year}</span>
      </div>
      <input type="checkbox" value="${isoDate}" id="chk-${i}" />
    `;
    saturdaysList.appendChild(label);
  });

  // Função helper para Toast (copiada do app principal)
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

  // Enviar formulário
  btnSubmit.addEventListener('click', async () => {
    const nome = inputNome.value.trim();
    if (!nome) {
      showToast('Por favor, digite seu nome.', 'error');
      inputNome.focus();
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
        body: JSON.stringify({ nome, disponibilidades })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.erro || 'Erro ao salvar disponibilidade.');
      }

      // Sucesso
      formView.classList.add('hidden');
      successView.classList.remove('hidden');

    } catch (error) {
      showToast(error.message, 'error');
      btnSubmit.disabled = false;
      btnSubmit.innerHTML = 'Enviar Disponibilidade';
    }
  });
});
