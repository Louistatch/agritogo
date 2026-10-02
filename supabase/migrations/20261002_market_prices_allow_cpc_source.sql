-- market_prices.source : autoriser la source externe SIM-CPC.
--
-- La contrainte market_prices_source_check n'admettait que manual, kobo et admin.
-- Le premier passage complet du pipeline CPC (3 482 relevés, de janvier à octobre
-- 2026) a donc vu 808 publications refusées par la base. Seule la liste des
-- valeurs autorisées change ; les lignes existantes (toutes « manual ») restent valides.
--
-- Idempotente.

alter table public.market_prices drop constraint if exists market_prices_source_check;
alter table public.market_prices
  add constraint market_prices_source_check
  check (source = any (array['manual'::text, 'kobo'::text, 'admin'::text, 'SIM-CPC'::text]));
