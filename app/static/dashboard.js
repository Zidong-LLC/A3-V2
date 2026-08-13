(() => {
  if (window.lucide) lucide.createIcons({ attrs: { 'aria-hidden': 'true', focusable: 'false' } });
  const sidebarToggle = document.querySelector('#sidebar-toggle');
  const _sidebarApply = (state) => {
    document.body.setAttribute('data-sidebar', state);
    try { localStorage.setItem('sidebar_state', state); } catch {}
    if (sidebarToggle) sidebarToggle.setAttribute('aria-label', state === 'collapsed' ? 'Expandir menu' : 'Colapsar menu');
  };
  try { const saved = localStorage.getItem('sidebar_state'); if (saved) _sidebarApply(saved); } catch {}
  if (sidebarToggle) sidebarToggle.addEventListener('click', () => _sidebarApply(document.body.getAttribute('data-sidebar') === 'collapsed' ? 'expanded' : 'collapsed'));
  const builderItemsSafe = window.__BUILDER_ITEMS__ || [];
  const customProfilesSafe = window.__CUSTOM_PROFILES__ || [];
  const postJsonSafe = async (url, payload) => {
    const res = await fetch(url, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Error');
    return data;
  };
  const esc = (value) => String(value || '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = (value) => `$ ${Number(value || 0).toLocaleString('es-CO')}`;

  document.querySelectorAll('.client-edit-input,.client-edit-select').forEach((control) => {
    if (control.dataset.safeBound) return;
    control.dataset.safeBound = '1';
    control.addEventListener('change', async () => {
      const row = control.closest('.client-table-row');
      const flag = control.parentElement.querySelector('.save-flag') || (row && row.querySelector('.save-flag'));
      if (!row) return;
      try {
        if (control.dataset.kind === 'assignment') {
          await postJsonSafe('/api/dashboard/client-assignment', {client_id: row.dataset.clientId, courier_id: control.value});
        } else if (control.dataset.kind === 'client') {
          await postJsonSafe('/api/dashboard/client-profile', {client_id: row.dataset.clientId, clinic_key: row.dataset.clinicKey, clinic_name: control.value, field: control.dataset.field, value: control.value});
        } else {
          await postJsonSafe('/api/dashboard/client-profile', {client_id: row.dataset.clientId, clinic_key: row.dataset.clinicKey, clinic_name: row.dataset.clinicName, field: control.dataset.field, value: control.value});
        }
        if (flag) flag.textContent = 'Guardado';
      } catch (err) {
        if (flag) flag.textContent = err.message;
      }
    });
  });

  function moveSampleCard(select) {
    const card = select.closest('.sample-process-card');
    if (!card) return;
    let status = select.value;
    if (status === 'on_route') status = 'picked_up';
    if (status === 'ready_results') status = 'processed';
    const targetLane = document.querySelector(`[data-sample-status="${status}"]`);
    if (!targetLane) return;
    const sourceLane = card.closest('[data-sample-status]');
    if (sourceLane && sourceLane !== targetLane) {
      const sourceCount = sourceLane.querySelector('header strong');
      if (sourceCount) sourceCount.textContent = Math.max(0, Number(sourceCount.textContent || 0) - 1);
      const targetCount = targetLane.querySelector('header strong');
      if (targetCount) targetCount.textContent = Number(targetCount.textContent || 0) + 1;
    }
    targetLane.appendChild(card);
    const badge = card.querySelector('.sample-card-top .status-badge');
    const selected = select.options[select.selectedIndex];
    if (badge && selected) badge.textContent = selected.textContent;
  }

  document.querySelectorAll('.sample-status-select').forEach((select) => {
    if (select.dataset.safeBound) return;
    select.dataset.safeBound = '1';
    select.dataset.originalValue = select.value;
    select.addEventListener('change', async () => {
      const flag = select.parentElement.querySelector('.save-flag');
      const label = select.options[select.selectedIndex]?.textContent || select.value;
      if (!window.confirm(`Cambiar estado a "${label}"?`)) {
        select.value = select.dataset.originalValue;
        return;
      }
      try {
        await postJsonSafe('/api/dashboard/sample-status', { sample_id: select.dataset.sampleId, status: select.value });
        select.dataset.originalValue = select.value;
        if (flag) flag.textContent = 'Guardado';
        moveSampleCard(select);
      } catch (err) {
        select.value = select.dataset.originalValue;
        if (flag) flag.textContent = err.message;
      }
    });
  });

  document.querySelectorAll('.request-priority-select').forEach((select) => {
    select.addEventListener('change', async () => {
      const flag = select.parentElement.querySelector('.save-flag');
      try { await postJsonSafe('/api/dashboard/request-operation', {request_id: select.dataset.requestId, priority: select.value}); if (flag) flag.textContent = 'Guardado'; }
      catch (err) { if (flag) flag.textContent = err.message; }
    });
  });
  document.querySelectorAll('.request-sample-count-input').forEach((input) => {
    input.addEventListener('change', async () => { try { await postJsonSafe('/api/dashboard/request-operation', {request_id: input.dataset.requestId, sample_count: input.value}); } catch (err) {} });
  });
  document.querySelectorAll('.request-sample-types-input').forEach((input) => {
    input.addEventListener('change', async () => { try { await postJsonSafe('/api/dashboard/request-operation', {request_id: input.dataset.requestId, sample_types: input.value}); } catch (err) {} });
  });
  document.querySelectorAll('.request-address-input').forEach((input) => {
    input.addEventListener('change', async () => { const flag = input.parentElement.querySelector('.save-flag'); try { await postJsonSafe('/api/dashboard/request-operation', {request_id: input.dataset.requestId, pickup_address: input.value}); if (flag) flag.textContent = 'Guardado'; } catch (err) { if (flag) flag.textContent = err.message; } });
  });
  document.querySelectorAll('.request-courier-select').forEach((select) => {
    select.addEventListener('change', async () => { const flag = select.parentElement.querySelector('.save-flag'); try { await postJsonSafe('/api/dashboard/request-operation', {request_id: select.dataset.requestId, assigned_courier_id: select.value}); if (flag) flag.textContent = 'Guardado'; } catch (err) { if (flag) flag.textContent = err.message; } });
  });
  document.querySelectorAll('.request-date-input').forEach((input) => {
    input.addEventListener('change', async () => { const flag = input.parentElement.querySelector('.save-flag'); try { await postJsonSafe('/api/dashboard/request-operation', {request_id: input.dataset.requestId, scheduled_pickup_date: input.value}); if (flag) flag.textContent = 'Guardado'; } catch (err) { if (flag) flag.textContent = err.message; } });
  });
  document.querySelectorAll('.request-status-select').forEach((select) => {
    select.addEventListener('change', async () => { const flag = select.parentElement.querySelector('.save-flag'); try { await postJsonSafe('/api/dashboard/request-status', {request_id: select.dataset.requestId, status: select.value}); if (flag) flag.textContent = 'Guardado'; } catch (err) { if (flag) flag.textContent = err.message; } });
  });

  document.querySelectorAll('.courier-phone-input').forEach((input) => {
    input.addEventListener('change', async () => { const flag = input.parentElement.querySelector('.save-flag'); try { await postJsonSafe('/api/dashboard/courier-phone', {courier_id: input.dataset.courierId, phone: input.value}); if (flag) flag.textContent = 'Guardado'; } catch (err) { if (flag) flag.textContent = err.message; } });
  });
  document.querySelectorAll('.courier-color-picker').forEach((picker) => { const dot = picker.parentElement.querySelector('.courier-color-dot'); picker.addEventListener('input', () => { if (dot) dot.style.background = picker.value; }); });
  document.querySelectorAll('.courier-availability-select').forEach((select) => {
    select.addEventListener('change', async () => { const flag = select.parentElement.querySelector('.save-flag'); try { await postJsonSafe('/api/dashboard/courier-availability', {courier_id: select.dataset.courierId, availability: select.value}); if (flag) flag.textContent = 'Guardado'; } catch (err) { if (flag) flag.textContent = err.message; } });
  });
  document.querySelectorAll('.locality-assignment-select').forEach((select) => {
    select.addEventListener('change', async () => { const flag = select.parentElement.querySelector('.save-flag'); try { await postJsonSafe('/api/dashboard/courier-locality-assignment', {locality_code: select.dataset.localityCode, courier_id: select.value}); if (flag) flag.textContent = 'Guardado'; } catch (err) { if (flag) flag.textContent = err.message; } });
  });

  function mountClientDeleteActions() {
    const table = document.querySelector('.table-clients');
    if (!table) return;
    const header = table.querySelector('thead tr');
    if (header && !header.querySelector('[data-client-delete-head]')) header.insertAdjacentHTML('beforeend', '<th data-client-delete-head>Acciones</th>');
    table.querySelectorAll('.client-table-row').forEach((row) => {
      if (row.querySelector('[data-client-delete-btn]')) return;
      const cell = document.createElement('td');
      cell.innerHTML = '<button type="button" class="reject-btn" data-client-delete-btn>Eliminar</button><small class="save-flag"></small>';
      row.appendChild(cell);
    });
    table.querySelectorAll('[data-client-delete-btn]').forEach((button) => {
      if (button.dataset.bound) return;
      button.dataset.bound = '1';
      button.addEventListener('click', async () => {
        const row = button.closest('.client-table-row');
        const flag = button.parentElement.querySelector('.save-flag');
        if (!row || !row.dataset.clientId) return;
        const name = row.dataset.clinicName || 'este cliente';
        if (!window.confirm(`Eliminar definitivamente ${name}? Esta accion no se puede deshacer.`)) return;
        button.disabled = true;
        try { await postJsonSafe('/api/dashboard/client-delete', {client_id: row.dataset.clientId, clinic_key: row.dataset.clinicKey}); row.remove(); }
        catch (err) { button.disabled = false; if (flag) flag.textContent = err.message; }
      });
    });
  }

  function mountClientFilters() {
    const rows = Array.from(document.querySelectorAll('.client-table-row'));
    if (!rows.length) return;
    const search = document.querySelector('[data-clients-search-input]');
    const type = document.querySelector('[data-clients-type-filter]');
    const status = document.querySelector('[data-clients-status-filter]');
    const assignment = document.querySelector('[data-clients-assignment-filter]');
    const fe = document.querySelector('[data-clients-fe-filter]');
    const count = document.querySelector('[data-clients-count-pill]');
    function apply() {
      const q = String(search && search.value || '').toLowerCase().trim();
      const t = String(type && type.value || 'all');
      const s = String(status && status.value || 'all');
      const a = String(assignment && assignment.value || 'all');
      const f = String(fe && fe.value || 'all');
      let visible = 0;
      rows.forEach((row) => {
        const ok = (!q || String(row.dataset.search || '').includes(q)) && (t === 'all' || String(row.dataset.clientType || '') === t) && (s === 'all' || String(row.dataset.clientStatus || '') === s) && (a === 'all' || String(row.dataset.clientHasCourier || '') === a) && (f === 'all' || String(row.dataset.clientFe || 'sin_dato') === f);
        row.style.display = ok ? '' : 'none';
        if (ok) visible++;
      });
      if (count) count.textContent = `${visible} visibles`;
    }
    [search, type, status, assignment, fe].forEach((el) => { if (el) el.addEventListener('input', apply), el.addEventListener('change', apply); });
    apply();
  }

  mountClientDeleteActions();
  mountClientFilters();

  (function() {
    const suggestBtn = document.getElementById('suggest-btn');
    const confirmBtn = document.getElementById('confirm-suggestions-btn');
    const flag = document.getElementById('suggest-flag');
    if (!suggestBtn) return;
    let pendingSuggestions = [];
    const METHOD_LABELS = {zona:'Zona', knowledge:'Knowledge', localidad:'Localidad', knowledge_fuzzy:'Knowledge (aprox)', geocode:'Geocodificacion'};
    suggestBtn.addEventListener('click', async () => {
      if (!window.confirm('Calcular sugerencias de motorizados por zona, knowledge y geocodificacion? Esto puede tardar varios minutos.')) return;
      suggestBtn.disabled = true;
      confirmBtn.style.display = 'none';
      if (flag) flag.textContent = 'Calculando sugerencias (puede tardar varios minutos)...';
      try {
        const res = await fetch('/api/dashboard/suggest-couriers', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({})});
        if (!res.ok) throw new Error((await res.json()).error || 'Error');
        const data = await res.json();
        pendingSuggestions = data.suggestions || [];
        let applied = 0;
        const rows = document.querySelectorAll('.client-table-row');
        const index = {};
        rows.forEach(r => { index[r.dataset.clientId] = r; });
        pendingSuggestions.forEach(s => {
          const row = index[s.client_id];
          if (!row) return;
          const select = row.querySelector('select[data-kind="assignment"]');
          if (select) {
            select.value = s.courier_id;
            row.classList.add('suggested-row');
            const badge = document.createElement('span');
            badge.className = 'suggest-badge';
            badge.textContent = METHOD_LABELS[s.method] || s.method;
            badge.title = 'Metodo: ' + s.method;
            select.parentElement.appendChild(badge);
            applied++;
          }
        });
        if (flag) flag.textContent = applied + ' sugerencias aplicadas de ' + pendingSuggestions.length + ' (' + data.no_match + ' sin coincidencia, ' + data.skipped + ' ya asignados)';
        if (applied > 0) confirmBtn.style.display = '';
      } catch (err) {
        if (flag) flag.textContent = 'Error: ' + err.message;
      } finally {
        suggestBtn.disabled = false;
      }
    });
    if (confirmBtn) confirmBtn.addEventListener('click', async () => {
      if (!window.confirm('Confirmar las sugerencias seleccionadas? Se guardaran en la base de datos.')) return;
      confirmBtn.disabled = true;
      if (flag) flag.textContent = 'Guardando...';
      try {
        const rows = document.querySelectorAll('.client-table-row.suggested-row');
        const updates = [];
        rows.forEach(row => {
          const select = row.querySelector('select[data-kind="assignment"]');
          if (select && select.value) updates.push({client_id: row.dataset.clientId, courier_id: select.value});
        });
        const res = await fetch('/api/dashboard/confirm-suggestions', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({updates})});
        if (!res.ok) throw new Error((await res.json()).error || 'Error');
        if (flag) flag.textContent = 'Sugerencias guardadas';
        setTimeout(() => location.reload(), 1000);
      } catch (err) {
        if (flag) flag.textContent = 'Error: ' + err.message;
        confirmBtn.disabled = false;
      }
    });
  })();

  const catalog = document.querySelector('[data-builder-catalog]');
  const selection = document.querySelector('[data-builder-selection]');
  const samples = document.querySelector('[data-builder-samples]');
  const total = document.querySelector('[data-builder-total]');
  const summary = document.querySelector('[data-builder-summary]');
  const client = document.querySelector('[data-builder-client]');
  const panel = document.querySelector('.builder-sticky');
  if (!catalog || !selection || !panel) return;
  catalog.querySelectorAll('[data-builder-add]').forEach((button) => { button.textContent = button.dataset.type === 'profile' ? 'Usar perfil' : 'Agregar analisis'; });

  const selectedItems = [];
  function applyBuilderCatalogFilters() {
    const search = document.querySelector('[data-builder-search]');
    const typeFilter = document.querySelector('[data-builder-type-filter]');
    const speciesFilter = document.querySelector('[data-builder-species-filter]');
    const categoryFilter = document.querySelector('[data-builder-category-filter]');
    const query = String(search?.value || '').toLowerCase().trim();
    const type = String(typeFilter?.value || 'all');
    const species = String(speciesFilter?.value || 'all');
    const category = String(categoryFilter?.value || 'all');
    catalog.querySelectorAll('[data-builder-card]').forEach((card) => {
      const text = `${card.dataset.name || ''} ${card.dataset.code || ''}`.toLowerCase();
      const matches = (!query || text.includes(query)) && (type === 'all' || card.dataset.type === type) && (species === 'all' || card.dataset.species === species) && (category === 'all' || card.dataset.category === category);
      card.style.display = matches ? '' : 'none';
    });
  }
  document.querySelectorAll('[data-builder-search],[data-builder-type-filter],[data-builder-species-filter],[data-builder-category-filter]').forEach((control) => {
    control.addEventListener('input', applyBuilderCatalogFilters);
    control.addEventListener('change', applyBuilderCatalogFilters);
  });
  function addItem(item, source = 'manual_extra', baseProfileCode = '') {
    if (!item || selectedItems.some((s) => s.code === item.code && s.item_type === item.item_type)) return;
    selectedItems.push({...item, selection_source: item.item_type === 'profile' ? 'base_profile' : source, included_from_profile_code: baseProfileCode});
    if (item.item_type === 'profile' && Array.isArray(item.composed_tests)) {
      item.composed_tests.forEach((test) => addItem(builderItemsSafe.find((candidate) => candidate.item_type === 'analysis' && candidate.code === test.code), 'profile_included', item.code));
    }
  }
  function renderBuilder() {
    const sampleSet = [...new Set(selectedItems.map((item) => item.sample).filter(Boolean))];
    const totalValue = selectedItems.reduce((sum, item) => sum + (item.selection_source === 'profile_included' ? 0 : Number(item.price || 0)), 0);
    selection.innerHTML = selectedItems.length ? selectedItems.map((item, index) => { const label = item.selection_source === 'base_profile' ? 'Perfil base · precio bonificado' : item.selection_source === 'profile_included' ? `Incluido en perfil ${esc(item.included_from_profile_code)} · sin costo extra` : 'Analisis adicional · suma al total'; return `<div class="builder-selected-item" data-code="${esc(item.code)}" data-type="${esc(item.item_type)}" data-source="${esc(item.selection_source)}" data-included-from="${esc(item.included_from_profile_code)}"><span><strong>${esc(item.name)}</strong><small>${esc(item.code)} · ${label}</small></span><button type="button" data-builder-remove="${index}">Quitar</button></div>`; }).join('') : '<div class="flow-empty">Agrega perfiles o analisis del catalogo.</div>';
    if (samples) samples.innerHTML = sampleSet.length ? sampleSet.map((sample) => `<span class="status-badge">${esc(sample)}</span>`).join(' ') : '<span class="muted-text">Sin items seleccionados</span>';
    if (total) total.textContent = money(totalValue);
    if (summary) {
      const clientName = client && client.value ? client.options[client.selectedIndex].textContent : 'Cliente por definir';
      summary.value = `Cliente: ${clientName}\nItems:\n${selectedItems.map((item) => `- ${item.code} ${item.name} (${item.selection_source === 'base_profile' ? 'Perfil base bonificado' : item.selection_source === 'profile_included' ? 'Incluido sin costo extra' : 'Analisis adicional'})`).join('\n') || '- Sin items'}\nMuestras requeridas: ${sampleSet.join(', ') || 'Sin definir'}\nTotal estimado: ${money(totalValue)}`;
    }
  }
  catalog.addEventListener('click', (event) => {
    const button = event.target.closest('[data-builder-add]');
    if (!button) return;
    addItem(builderItemsSafe.find((item) => item.code === button.dataset.code && item.item_type === button.dataset.type));
    renderBuilder();
  });
  selection.addEventListener('click', (event) => {
    const button = event.target.closest('[data-builder-remove]');
    if (!button) return;
    const removed = selectedItems.splice(Number(button.dataset.builderRemove), 1)[0];
    if (removed && removed.selection_source === 'base_profile') {
      for (let i = selectedItems.length - 1; i >= 0; i--) {
        if (selectedItems[i].selection_source === 'profile_included' && selectedItems[i].included_from_profile_code === removed.code) selectedItems.splice(i, 1);
      }
    }
    renderBuilder();
  });

  if (!panel.querySelector('[data-builder-profile-name]')) {
    panel.insertAdjacentHTML('afterbegin', '<label>Nombre del perfil personalizado<input class="cell-input" data-builder-profile-name placeholder="Ej. Perfil renal Max"></label>');
  }
  if (!panel.querySelector('[data-builder-add-analysis]')) panel.insertAdjacentHTML('beforeend', '<button type="button" class="ghost-btn" data-builder-add-analysis>Agregar analisis extra</button>');
  if (!panel.querySelector('[data-builder-clear]')) panel.insertAdjacentHTML('beforeend', '<button type="button" class="ghost-btn" data-builder-clear>Limpiar seleccion</button>');
  if (!panel.querySelector('[data-builder-save-profile]')) panel.insertAdjacentHTML('beforeend', '<button type="button" class="ghost-btn" data-builder-save-profile>Guardar perfil personalizado</button>');
  if (!panel.querySelector('[data-builder-accept]')) panel.insertAdjacentHTML('beforeend', '<button type="button" class="primary-btn" data-builder-accept>Aceptar y registrar muestras</button><small class="save-flag" data-builder-save-flag></small>');

  panel.querySelector('[data-builder-clear]')?.addEventListener('click', () => { selectedItems.splice(0); renderBuilder(); });
  panel.querySelector('[data-builder-add-analysis]')?.addEventListener('click', () => { const typeFilter = document.querySelector('[data-builder-type-filter]'); const search = document.querySelector('[data-builder-search]'); if (typeFilter) typeFilter.value = 'analysis'; applyBuilderCatalogFilters(); catalog.scrollIntoView({behavior:'smooth', block:'start'}); if (search) search.focus(); });
  panel.querySelector('[data-builder-save-profile]')?.addEventListener('click', async () => {
    const flag = panel.querySelector('[data-builder-save-flag]');
    const name = panel.querySelector('[data-builder-profile-name]')?.value || 'Perfil personalizado';
    if (!client?.value) { if (flag) flag.textContent = 'Selecciona un cliente'; return; }
    if (!selectedItems.length) { if (flag) flag.textContent = 'Agrega analisis al perfil'; return; }
    try {
      await postJsonSafe('/api/dashboard/save-custom-profile', { client_id: client.value, name, items: selectedItems.map((item) => ({ code: item.code, item_type: item.item_type, name: item.name, source: item.selection_source, included_from_profile_code: item.included_from_profile_code, price: item.selection_source === 'profile_included' ? 0 : Number(item.price || 0) })) });
      if (flag) flag.textContent = 'Perfil guardado';
      setTimeout(() => location.reload(), 1000);
    } catch (err) { if (flag) flag.textContent = err.message; }
  });
  panel.querySelector('[data-builder-accept]')?.addEventListener('click', async () => {
    const flag = panel.querySelector('[data-builder-save-flag]');
    if (!client?.value) { if (flag) flag.textContent = 'Selecciona un cliente'; return; }
    if (!selectedItems.length) { if (flag) flag.textContent = 'Agrega al menos un analisis'; return; }
    try {
      const result = await postJsonSafe('/api/dashboard/profile-assignment', { client_id: client.value, items: selectedItems.map((item) => ({ code: item.code, item_type: item.item_type, source: item.selection_source, included_from_profile_code: item.included_from_profile_code })), notes: summary?.value || '' });
      if (flag) flag.textContent = `Registradas ${result.created_count} muestra(s)`;
      setTimeout(() => location.reload(), 1200);
    } catch (err) { if (flag) flag.textContent = err.message; }
  });
  document.querySelectorAll('[data-load-profile]').forEach((button) => button.addEventListener('click', () => {
    const profile = customProfilesSafe.find((item) => item.id === button.dataset.loadProfile);
    if (!profile) return;
    selectedItems.splice(0);
    (profile.items_json || []).forEach((saved) => addItem(builderItemsSafe.find((item) => item.code === saved.code && item.item_type === saved.item_type)));
    if (client && profile.client_id) client.value = profile.client_id;
    const nameInput = panel.querySelector('[data-builder-profile-name]');
    if (nameInput) nameInput.value = profile.name || '';
    renderBuilder();
  }));
  document.querySelectorAll('[data-delete-profile]').forEach((button) => button.addEventListener('click', async () => {
    if (!window.confirm('Eliminar este perfil personalizado?')) return;
    await postJsonSafe('/api/dashboard/delete-custom-profile', { profile_id: button.dataset.deleteProfile });
    button.closest('.custom-profile-card')?.remove();
  }));
  client?.addEventListener('change', renderBuilder);
  renderBuilder();
  applyBuilderCatalogFilters();
})();

// ── Panel Ejecutivo — sistema de widgets ─────────────────────────────────────
(() => {
  if (!document.querySelector('[data-widget]')) return;

  const STORAGE_KEY = 'exec_widgets_v1';
  const TABLE_ID = 'exec_widgets';
  const SERVER_ENDPOINT = '/api/dashboard/column-prefs';
  const ALL_WIDS = ['kpi_ops', 'kpi_biz', 'alerts', 'pipeline', 'requests_recent', 'samples_state', 'courier_load', 'billing_mini', 'top_clients', 'activity'];
  let saveTimer = null;

  const loadPrefs = () => {
    try { const s = localStorage.getItem(STORAGE_KEY); if (s) return JSON.parse(s); } catch {}
    return { visible: [...ALL_WIDS] };
  };

  const savePrefs = (prefs) => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs)); } catch {}
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      fetch(SERVER_ENDPOINT, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ table_id: TABLE_ID, prefs }),
      }).catch(() => {});
    }, 600);
  };

  const applyPrefs = (prefs) => {
    document.querySelectorAll('[data-widget]').forEach(w => {
      w.classList.toggle('exec-hidden', !prefs.visible.includes(w.dataset.widget));
    });
    document.querySelectorAll('#exec-widget-list [data-wid]').forEach(li => {
      const cb = li.querySelector('input[type="checkbox"]');
      if (cb) cb.checked = prefs.visible.includes(li.dataset.wid);
    });
  };

  // Inicializar
  applyPrefs(loadPrefs());

  // Panel open/close
  const panel = document.getElementById('exec-widget-panel');
  const openBtn = document.getElementById('exec-customize-btn');
  const closeBtn = document.getElementById('exec-widget-close');
  openBtn?.addEventListener('click', (e) => { e.stopPropagation(); panel?.classList.add('open'); });
  closeBtn?.addEventListener('click', () => panel?.classList.remove('open'));
  document.addEventListener('click', (e) => {
    if (panel?.classList.contains('open') && !panel.contains(e.target) && !openBtn?.contains(e.target)) {
      panel.classList.remove('open');
    }
  });

  // Toggles de checkboxes
  document.querySelectorAll('#exec-widget-list [data-wid]').forEach(li => {
    const cb = li.querySelector('input[type="checkbox"]');
    if (!cb) return;
    cb.addEventListener('change', () => {
      const prefs = loadPrefs();
      const wid = li.dataset.wid;
      prefs.visible = cb.checked
        ? [...new Set([...prefs.visible, wid])]
        : prefs.visible.filter(v => v !== wid);
      savePrefs(prefs);
      applyPrefs(prefs);
    });
  });

  // Mostrar todo
  document.getElementById('exec-widgets-show-all')?.addEventListener('click', () => {
    const prefs = { visible: [...ALL_WIDS] };
    savePrefs(prefs); applyPrefs(prefs);
  });

  // Restablecer (mismo que mostrar todo por ahora)
  document.getElementById('exec-widgets-reset')?.addEventListener('click', () => {
    try { localStorage.removeItem(STORAGE_KEY); } catch {}
    const prefs = { visible: [...ALL_WIDS] };
    savePrefs(prefs); applyPrefs(prefs);
  });

  // Cargar preferencias del servidor
  fetch(SERVER_ENDPOINT)
    .then(r => r.json())
    .then(data => {
      const sp = (data.prefs || {})[TABLE_ID];
      if (sp?.visible?.length) {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(sp)); } catch {}
        applyPrefs(sp);
      }
    })
    .catch(() => {});
})();

// ── Centro Operativo — panel lateral de orden + buscador ─────────────────────
(() => {
  const panel = document.getElementById('op-detail-panel');
  if (!panel) return;
  const overlay = document.getElementById('op-detail-overlay');
  const title = document.getElementById('op-detail-title');
  const statusEl = document.getElementById('op-detail-status');
  const body = document.getElementById('op-detail-body');
  const foot = document.getElementById('op-detail-foot');
  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const val = (v) => (v == null || v === '' || v === '-') ? '—' : esc(v);

  const close = () => { panel.classList.remove('open'); overlay?.classList.remove('open'); };
  document.getElementById('op-detail-close')?.addEventListener('click', close);
  overlay?.addEventListener('click', close);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });

  const field = (label, value, full) => `<div class="op-detail-field${full ? ' full' : ''}"><span>${label}</span><strong>${val(value)}</strong></div>`;

  const open = (o) => {
    if (title) title.textContent = 'Orden ' + (o.order_number || '—');
    if (statusEl) statusEl.textContent = o.status_label || '';
    if (body) body.innerHTML = `
      <div class="op-detail-section">
        <h4>Veterinaria</h4>
        <div class="op-detail-fields">
          ${field('Cliente', o.clinic_name, true)}
          ${field('Medico solicitante', o.requesting_doctor)}
          ${field('Telefono', o.clinic_phone)}
          ${field('Direccion de recogida', o.pickup_address, true)}
        </div>
      </div>
      <div class="op-detail-section">
        <h4>Paciente</h4>
        <div class="op-detail-fields">
          ${field('Nombre', o.patient_name)}
          ${field('Propietario', o.owner_name)}
          ${field('Especie', o.species)}
          ${field('Raza', o.breed)}
          ${field('Sexo', o.sex)}
          ${field('Edad', o.patient_age)}
        </div>
      </div>
      <div class="op-detail-section">
        <h4>Orden de servicio</h4>
        <div class="op-detail-fields">
          ${field('Estudio principal', o.exam_type, true)}
          ${field('Forma de pago', o.payment_method)}
          ${field('Prioridad', o.priority)}
          ${field('Motorizado', o.courier_name)}
          ${field('Fecha de orden', (o.service_order_date || '').slice(0, 10))}
          ${field('Fecha programada', (o.scheduled_pickup_date || '').slice(0, 10))}
        </div>
      </div>
      <div class="op-detail-section">
        <h4>Observaciones</h4>
        <div class="op-detail-fields">${field('', o.observations, true)}</div>
      </div>`;
    if (foot) {
      foot.innerHTML = o.request_id
        ? `<a class="primary-btn" href="/ordenes-servicio/${encodeURIComponent(o.request_id)}/imprimir" target="_blank" rel="noopener">Imprimir PDF</a>`
        : '<button class="ghost-btn" disabled>PDF no disponible</button>';
    }
    panel.classList.add('open');
    overlay?.classList.add('open');
    if (window.lucide) lucide.createIcons({ attrs: { 'aria-hidden': 'true', focusable: 'false' } });
  };

  document.querySelectorAll('[data-op-order]').forEach((row) => {
    const trigger = row.querySelector('.op-view-order') || row;
    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      try { open(JSON.parse(row.dataset.opOrder)); } catch {}
    });
  });

  // Buscador de órdenes (filtra filas en cliente).
  const search = document.getElementById('op-orders-search');
  search?.addEventListener('input', () => {
    const q = search.value.trim().toLowerCase();
    document.querySelectorAll('.op-order-row').forEach((row) => {
      row.classList.toggle('op-hidden', q && !(row.dataset.search || '').includes(q));
    });
  });

  // ── Edición del catálogo (precio y etiqueta de especie) ─────────────────────
  // El catálogo era de solo lectura: cambiar un precio exigía SQL a mano (pedido de A3 del
  // 07/04). La etiqueta de especie marca los ítems EXCLUSIVOS de una especie; el resto
  // queda disponible para todas (decisión 012).
  document.querySelectorAll('[data-catalog-edit]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const row = btn.closest('[data-builder-card]')?.querySelector('[data-catalog-edit-row]');
      if (row) row.hidden = !row.hidden;
    });
  });

  document.querySelectorAll('[data-catalog-save]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const card = btn.closest('[data-builder-card]');
      const row = btn.closest('[data-catalog-edit-row]');
      const flag = row?.querySelector('[data-catalog-flag]');
      const precio = row?.querySelector('[data-catalog-price-input]');
      const especie = row?.querySelector('[data-catalog-species-input]');
      if (!card || !precio || !especie) return;
      const payload = {
        kind: btn.dataset.kind,
        code: btn.dataset.code,
        price: precio.value.trim(),
        species: especie.value,
      };
      if (flag) flag.textContent = 'Guardando…';
      btn.disabled = true;
      try {
        const data = await postJsonSafe('/api/dashboard/catalog-item', payload);
        const nuevo = Number(data.item?.price || 0);
        const label = card.querySelector('[data-catalog-price]');
        if (label) label.textContent = nuevo ? money(nuevo) : 'Sin precio';
        // La card se filtra por especie desde la barra de arriba: hay que actualizar el
        // dataset o el filtro seguiría usando el valor viejo hasta recargar.
        card.dataset.species = especie.value;
        const meta = card.querySelector('.lab-card-meta span');
        if (meta) meta.textContent = especie.value;
        if (flag) flag.textContent = 'Guardado';
        setTimeout(() => { if (flag) flag.textContent = ''; if (row) row.hidden = true; }, 1200);
      } catch (err) {
        if (flag) flag.textContent = err.message || 'No se pudo guardar';
      } finally {
        btn.disabled = false;
      }
    });
  });


  // ── Cierre manual de un pedido ──────────────────────────────────────────────
  // Respaldo humano del barrido automático: ese barrido corre de forma oportunista (sin
  // scheduler), así que un pedido abandonado sin tráfico posterior necesita que alguien
  // pueda cerrarlo desde acá.
  document.querySelectorAll('[data-pedido-close]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const pedidoId = btn.dataset.pedidoClose;
      const flag = document.querySelector(`[data-pedido-flag="${pedidoId}"]`);
      if (!window.confirm('Se cerrará el pedido y se intentará emitir su factura. ¿Continuar?')) return;
      btn.disabled = true;
      if (flag) flag.textContent = 'Procesando…';
      try {
        const data = await postJsonSafe('/api/dashboard/pedido-close', { pedido_id: pedidoId, invoice: true });
        if (flag) flag.textContent = data.warning || (data.invoice ? `Facturado ${data.invoice}` : 'Cerrado');
        if (!data.warning) setTimeout(() => window.location.reload(), 1200);
      } catch (err) {
        if (flag) flag.textContent = err.message || 'No se pudo cerrar';
      } finally {
        btn.disabled = false;
      }
    });
  });

})();
