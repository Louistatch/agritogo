-- AgriTogo Market Intelligence provenance + forecast separation
-- Safe to run in Supabase SQL editor.

alter table if exists public.market_prices
    add column if not exists source text default 'manual',
    add column if not exists source_url text,
    add column if not exists observed_at timestamptz,
    add column if not exists data_kind text default 'observation',
    add column if not exists ingested_at timestamptz default now();

create index if not exists idx_market_prices_observed
    on public.market_prices (culture_id, market_name, created_at desc);

create index if not exists idx_market_prices_source
    on public.market_prices (source);

create table if not exists public.market_price_forecasts (
    id uuid primary key default gen_random_uuid(),
    culture_id uuid not null references public.cultures(id) on delete cascade,
    region_id uuid,
    market_name text not null,
    forecast_price numeric not null,
    target_date date not null,
    confidence numeric,
    unit text default 'kg',
    currency text default 'FCFA',
    model text default 'agritogo',
    model_version text,
    created_at timestamptz default now()
);

create index if not exists idx_market_price_forecasts_lookup
    on public.market_price_forecasts (culture_id, market_name, target_date desc);

comment on column public.market_prices.source is
    'Origin of the observed price, e.g. SIM-CPC, manual, partner import.';
comment on column public.market_prices.data_kind is
    'Observation only in market_prices. Forecasts belong in market_price_forecasts.';
