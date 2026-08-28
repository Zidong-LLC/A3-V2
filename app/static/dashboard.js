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

  // El filtrado ya NO se hace acá: lo hace el servidor sobre los 992 clientes y después
  // pagina (app/client_filters.py). Filtrar en el navegador solo miraba las 15 filas de la
  // página visible, así que buscar un cliente cargado en la página 40 daba cero resultados.
  // Lo único que queda es enviar el formulario al elegir un desplegable.
  function mountClientFilters() {
    const selects = document.querySelectorAll('[data-clients-submit]');
    if (!selects.length) return;
    const form = selects[0].form;
    selects.forEach((select) => {
      select.addEventListener('change', () => form && form.requestSubmit());
    });
    // Los campos vacíos o en "todos" no viajan: sin esto la URL queda
    // ?q=&tipo=all&estado=all&motorizado=all&fe=all y no se puede compartir.
    if (form) {
      form.addEventListener('submit', () => {
        [...form.elements].forEach((campo) => {
          if (!campo.name) return;
          if (campo.value === '' || campo.value === 'all') campo.disabled = true;
        });
        setTimeout(() => [...form.elements].forEach((c) => { c.disabled = false; }), 0);
      });
    }
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
        const res = await fetch('/api/dashboard/confirm-suggested-assignments', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({assignments: updates})});
        if (!res.ok) throw new Error((await res.json()).error || 'Error');
        if (flag) flag.textContent = 'Sugerencias guardadas';
        setTimeout(() => location.reload(), 1000);
      } catch (err) {
        if (flag) flag.textContent = 'Error: ' + err.message;
        confirmBtn.disabled = false;
      }
    });
  })();

  // ── Buscador y filtros del catalogo ─────────────────────────────────────────
  // Vivia dentro del constructor de perfil a medida; al retirarlo habria quedado sin
  // ejecutarse (`if (!panel) return;`) y el catalogo se habria quedado sin busqueda.
  (() => {
    const catalog = document.querySelector('[data-builder-catalog]');
    if (!catalog) return;
    const plano = (v) => String(v || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

    function aplicar() {
      const search = document.querySelector('[data-builder-search]');
      const typeFilter = document.querySelector('[data-builder-type-filter]');
      const speciesFilter = document.querySelector('[data-builder-species-filter]');
      const categoryFilter = document.querySelector('[data-builder-category-filter]');
      // Sin tildes y por palabras: «hepatico» tiene que encontrar «Perfil Hepático».
      const palabras = plano(search?.value).trim().split(/\s+/).filter(Boolean);
      const type = String(typeFilter?.value || 'all');
      const species = String(speciesFilter?.value || 'all');
      const category = String(categoryFilter?.value || 'all');
      let visibles = 0;
      catalog.querySelectorAll('[data-builder-card]').forEach((card) => {
        const text = plano(`${card.dataset.name || ''} ${card.dataset.code || ''}`);
        const matches = palabras.every((p) => text.includes(p))
          && (type === 'all' || card.dataset.type === type)
          && (species === 'all' || card.dataset.species === species)
          && (category === 'all' || card.dataset.category === category);
        card.style.display = matches ? '' : 'none';
        if (matches) visibles++;
      });
      const contador = document.querySelector('[data-builder-count]');
      if (contador) contador.textContent = `${visibles} de ${catalog.querySelectorAll('[data-builder-card]').length}`;
      const vacio = document.querySelector('[data-builder-empty]');
      if (vacio) vacio.hidden = visibles > 0;
    }

    document.querySelectorAll('[data-builder-search],[data-builder-type-filter],[data-builder-species-filter],[data-builder-category-filter]')
      .forEach((control) => {
        control.addEventListener('input', aplicar);
        control.addEventListener('change', aplicar);
      });
    aplicar();
  })();


})();

// ── Panel Ejecutivo — sistema de widgets ─────────────────────────────────────
(() => {
  if (!document.querySelector('[data-widget]')) return;

  const STORAGE_KEY = 'exec_widgets_v1';
  const TABLE_ID = 'exec_widgets';
  const SERVER_ENDPOINT = '/api/dashboard/column-prefs';
  const ALL_WIDS = ['kpi_ops', 'kpi_biz', 'alerts', 'pipeline', 'requests_recent', 'samples_state', 'courier_load', 'billing_mini', 'top_clients', 'activity', 'tat', 'trends'];
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
        // El server exige visible Y order (400 si falta): sin order la
        // persistencia server-side fallaba en silencio por el catch.
        body: JSON.stringify({ table_id: TABLE_ID, prefs: { visible: prefs.visible, order: prefs.order || prefs.visible } }),
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


})();

// El editor de descuentos vivia dentro del IIFE del Centro Operativo, que arranca
// con `if (!panel) return;`: en Muestras, que es donde se muestra, los botones no
// hacian nada. Va en su propio bloque.
// ── Descuentos por volumen editables ────────────────────────────────────────
// Los tramos viven en discount_tiers (migración 021); el % se muestra como
// porcentaje (12) y viaja como fracción (0.12). El server valida en serio.
(() => {
  const card = document.querySelector('[data-discount-card]');
  if (!card) return;
  // Envío propio: `postJsonSafe` vive dentro del IIFE grande y este bloque quedó afuera.
  const enviar = async (url, payload) => {
    const res = await fetch(url, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Error');
    return data;
  };
  const rowsBox = card.querySelector('[data-discount-rows]');
  const flag = card.querySelector('[data-discount-flag]');
  const saveBtn = card.querySelector('[data-discount-save]');

  card.querySelector('[data-tier-add]').addEventListener('click', () => {
    const tr = document.createElement('tr');
    tr.setAttribute('data-discount-row', '');
    tr.innerHTML = '<td><input class="cell-input" data-tier-min type="number" min="2" max="99"></td>'
      + '<td><input class="cell-input" data-tier-pct type="number" step="0.5" min="0" max="90"></td>'
      + '<td><button type="button" class="ghost-btn" data-tier-remove title="Quitar tramo">✕</button></td>';
    rowsBox.appendChild(tr);
  });

  rowsBox.addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-tier-remove]');
    if (btn) btn.closest('tr').remove();
  });

  saveBtn.addEventListener('click', async () => {
    const tiers = [];
    rowsBox.querySelectorAll('[data-discount-row]').forEach((tr) => {
      const min = parseInt(tr.querySelector('[data-tier-min]').value, 10);
      const pct = parseFloat(tr.querySelector('[data-tier-pct]').value);
      if (!Number.isNaN(min) && !Number.isNaN(pct)) tiers.push({ min_tests: min, pct: pct / 100 });
    });
    flag.textContent = 'Guardando…';
    saveBtn.disabled = true;
    try {
      await enviar('/api/dashboard/discount-tiers', { tiers });
      flag.textContent = 'Guardado';
      setTimeout(() => { flag.textContent = ''; }, 1500);
    } catch (err) {
      flag.textContent = err.message || 'No se pudo guardar';
    } finally {
      saveBtn.disabled = false;
    }
  });
})();

// Estos tres bloques vivian DENTRO del IIFE del Centro Operativo, que arranca con
// `if (!panel) return;`: el lapiz del catalogo, el cierre de pedidos y el grafico de
// tendencias nunca corrian en las pantallas donde se muestran.
(() => {
  const enviar = async (url, payload) => {
    const res = await fetch(url, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Error');
    return data;
  };
  // `money` tambien vive en el IIFE grande: al mover el bloque, guardar un precio
  // terminaba con "money is not defined" aunque el precio SI se hubiera guardado.
  const money = (value) => `$ ${Number(value || 0).toLocaleString('es-CO')}`;
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
        const data = await enviar('/api/dashboard/catalog-item', payload);
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
        const data = await enviar('/api/dashboard/pedido-close', { pedido_id: pedidoId, invoice: true });
        if (flag) flag.textContent = data.warning || (data.invoice ? `Facturado ${data.invoice}` : 'Cerrado');
        if (!data.warning) setTimeout(() => window.location.reload(), 1200);
      } catch (err) {
        if (flag) flag.textContent = err.message || 'No se pudo cerrar';
      } finally {
        btn.disabled = false;
      }
    });
  });




  // ── Tendencias del Panel Ejecutivo (ApexCharts, ya cargado por CDN) ─────────
  (() => {
    const dataNode = document.getElementById('exec-metrics-data');
    if (!dataNode || !window.ApexCharts) return;
    let metrics;
    try { metrics = JSON.parse(dataNode.textContent); } catch { return; }

    // Estilo compartido de la piel ZIDONG OS: fondo transparente, texto
    // atenuado, serie monocroma blanca y grid sutil sobre el canvas oscuro.
    const osChartBase = {
      chart: { background: 'transparent', foreColor: 'rgba(230,230,238,.62)', fontFamily: '"Public Sans",Inter,sans-serif', toolbar: { show: false } },
      colors: ['#f5f5f7'],
      grid: { borderColor: 'rgba(255,255,255,.08)' },
      tooltip: { theme: 'dark' },
    };

    const dailyNode = document.getElementById('chart-requests-daily');
    if (dailyNode && (metrics.daily || []).length) {
      new ApexCharts(dailyNode, {
        ...osChartBase,
        chart: { ...osChartBase.chart, type: 'bar', height: 200 },
        plotOptions: { bar: { borderRadius: 3, columnWidth: '60%' } },
        series: [{ name: 'Solicitudes', data: metrics.daily.map(d => d.count) }],
        xaxis: { categories: metrics.daily.map(d => d.date.slice(5)), labels: { rotate: -45, style: { fontSize: '10px' } } },
        dataLabels: { enabled: false },
        title: { text: 'Solicitudes por día (30 días)', style: { fontSize: '12px', color: 'rgba(230,230,238,.72)' } },
      }).render();
    }

    const weeklyNode = document.getElementById('chart-tat-weekly');
    if (weeklyNode && (metrics.weekly || []).length) {
      new ApexCharts(weeklyNode, {
        ...osChartBase,
        chart: { ...osChartBase.chart, type: 'line', height: 180 },
        series: [{ name: 'TAT promedio (h)', data: metrics.weekly.map(w => w.avg_hours) }],
        xaxis: { categories: metrics.weekly.map(w => w.week) },
        stroke: { curve: 'smooth', width: 3 },
        markers: { size: 4 },
        title: { text: 'TAT promedio por semana', style: { fontSize: '12px', color: 'rgba(230,230,238,.72)' } },
      }).render();
    }
  })();
})();
