/**
 * invoices.js — interactividad del módulo "Facturación".
 * Filtros/orden/paginación van por querystring (filtrado del lado servidor, conserva
 * compatibilidad con el selector de columnas). Sync, detalle y copiar usan los endpoints
 * /api/dashboard/invoices*. Read-only: nada emite ni envía.
 */
(() => {
  const root = document.querySelector('[data-columns-table="facturacion"]');
  if (!root) return;
  const locked = window.__INVOICES_LOCKED__ === true;
  const money = (v) => `$ ${Number(v || 0).toLocaleString('es-CO')}`;
  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const baseParams = () => new URLSearchParams(window.location.search);
  const go = (params) => { window.location.search = params.toString(); };

  // Orden por columna: click en <th data-sort>.
  root.querySelectorAll('thead th[data-sort]').forEach((th) => {
    th.classList.add('sortable');
    th.addEventListener('click', () => {
      const field = th.dataset.sort;
      const params = baseParams();
      const current = params.get('order_field') || 'invoice_date';
      const dir = params.get('order_dir') || 'desc';
      params.set('order_field', field);
      params.set('order_dir', current === field && dir === 'desc' ? 'asc' : 'desc');
      params.delete('page');
      go(params);
    });
  });

  // Paginación conservando filtros.
  document.querySelectorAll('[data-invoices-page]').forEach((link) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const params = baseParams();
      params.set('page', link.dataset.invoicesPage);
      go(params);
    });
  });

  // Exportar (CSV / Excel) con los filtros aplicados.
  document.querySelectorAll('[data-invoices-export]').forEach((link) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const params = baseParams();
      params.set('format', link.dataset.invoicesExport);
      params.delete('page');
      window.location.href = '/api/dashboard/invoices/export?' + params.toString();
    });
  });

  // Copiar número de factura.
  document.querySelectorAll('[data-invoice-copy]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const value = btn.dataset.invoiceCopy || '';
      navigator.clipboard?.writeText(value).then(() => {
        const old = btn.textContent; btn.textContent = 'Copiado'; setTimeout(() => { btn.textContent = old; }, 1200);
      }).catch(() => {});
    });
  });

  // Sincronizar con Alegra.
  const syncBtn = document.querySelector('[data-invoices-sync]');
  const syncFlag = document.querySelector('[data-invoices-sync-flag]');
  if (syncBtn && !syncBtn.disabled) {
    syncBtn.addEventListener('click', async () => {
      if (!window.confirm('Traer/actualizar las facturas desde Alegra? (solo lectura)')) return;
      syncBtn.disabled = true;
      if (syncFlag) syncFlag.textContent = 'Sincronizando…';
      try {
        const res = await fetch('/api/dashboard/invoices/sync', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok && res.status !== 207) throw new Error(data.error || 'Error');
        if (syncFlag) syncFlag.textContent = `${data.synced || 0} facturas sincronizadas${(data.errors || []).length ? ' (con errores)' : ''}`;
        setTimeout(() => window.location.reload(), 1000);
      } catch (err) {
        if (syncFlag) syncFlag.textContent = 'Error: ' + err.message;
        syncBtn.disabled = false;
      }
    });
  }

  // Modal de detalle (read-through a Alegra).
  const modal = document.querySelector('[data-invoice-modal]');
  const modalTitle = document.querySelector('[data-invoice-modal-title]');
  const modalBody = document.querySelector('[data-invoice-modal-body]');
  const closeModal = () => { if (modal) modal.hidden = true; };
  modal?.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
  document.querySelector('[data-invoice-modal-close]')?.addEventListener('click', closeModal);

  function renderDetail(data) {
    const inv = data.invoice || {};
    const client = inv.client || {};
    const items = Array.isArray(inv.items) ? inv.items : [];
    const number = (inv.numberTemplate || {}).fullNumber || inv.number || '-';
    const lines = items.map((it) => `<tr><td>${esc(it.name || it.description || '-')}</td><td>${esc(it.quantity || 1)}</td><td>${money(it.price)}</td></tr>`).join('') || '<tr><td colspan="3">Sin líneas</td></tr>';
    const pdf = data.pdf_url;
    const stamped = !!((inv.stamp || {}).cufe);
    const actions = [
      pdf ? `<a class="primary-btn" href="${esc(pdf)}" target="_blank" rel="noopener">Descargar PDF</a>` : '<button class="ghost-btn" disabled>PDF no disponible</button>',
      `<a class="ghost-btn" href="https://app.alegra.com/invoice/view/id/${esc(inv.id || '')}" target="_blank" rel="noopener">Abrir en Alegra</a>`,
      (locked || !stamped) ? '<button class="ghost-btn" disabled title="Bloqueado en pruebas / requiere emisión DIAN">Descargar XML</button>' : `<a class="ghost-btn" href="https://app.alegra.com/invoice/view/id/${esc(inv.id || '')}" target="_blank" rel="noopener">Descargar XML</a>`,
      locked ? '<button class="ghost-btn" disabled title="Bloqueado en entorno de pruebas">Reenviar por correo</button>' : '<button class="ghost-btn" data-invoice-resend disabled>Reenviar por correo</button>',
    ].join(' ');
    if (modalTitle) modalTitle.textContent = `Factura ${number}`;
    if (modalBody) modalBody.innerHTML = `
      <div class="invoice-detail-grid">
        <div><span>Cliente</span><strong>${esc(client.name || '-')}</strong></div>
        <div><span>NIT</span><strong>${esc((client.identificationObject || {}).number || client.identification || '-')}</strong></div>
        <div><span>Fecha</span><strong>${esc(String(inv.date || '-').slice(0, 10))}</strong></div>
        <div><span>Estado</span><strong>${esc(inv.status || '-')}</strong></div>
      </div>
      <table class="invoice-detail-table"><thead><tr><th>Concepto</th><th>Cant.</th><th>Precio</th></tr></thead><tbody>${lines}</tbody></table>
      <div class="invoice-detail-totals"><span>Neto: ${money(inv.subtotal)}</span><span>IVA: ${money(inv.tax)}</span><strong>Total: ${money(inv.total)}</strong></div>
      <div class="invoice-detail-actions">${actions}</div>
      ${data.source === 'cache' ? '<p class="muted-text">Mostrando datos del cache (Alegra deshabilitado).</p>' : ''}`;
  }

  document.querySelectorAll('[data-invoice-view]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.invoiceView;
      if (!modal) return;
      modal.hidden = false;
      if (modalBody) modalBody.innerHTML = '<p class="muted-text">Cargando…</p>';
      try {
        const res = await fetch('/api/dashboard/invoices/' + encodeURIComponent(id));
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Error');
        renderDetail(data);
      } catch (err) {
        if (modalBody) modalBody.innerHTML = `<p class="approval-notice error">${esc(err.message)}</p>`;
      }
    });
  });
})();
