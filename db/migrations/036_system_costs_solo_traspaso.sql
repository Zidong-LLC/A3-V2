-- 036: El panel de sistema sigue solo los servicios que se TRASPASAN al cliente y que el
-- responsable técnico controla hasta entonces: OpenAI (automático), Render, Supabase y el
-- VPS de Chatwoot. WhatsApp, Alegra y dominios son gastos del cliente que no se miden acá
-- (decisión del usuario, 2026-10-26).
DELETE FROM system_costs WHERE service IN ('whatsapp', 'alegra', 'dominio');
