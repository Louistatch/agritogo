-- Source registry and market-observation quality controls.

create table if not exists public.market_data_sources (
    code text primary key,
    name text not null,
    base_url text,
    source_type text not null default 'public_market_system',
    enabled boolean not null default true,
    trust_weight numeric not null default 1.0
        check (trust_weight >= 0 and trust_weight <= 1),
    freshness_target_hours integer,
    poll_interval_minutes integer,
    notes text,
    last_success_at timestamptz,
    last_observation_at timestamptz,
    last_status text,
    last_error text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

insert into public.market_data_sources (
    code, name, base_url, source_type, trust_weight,
    freshness_target_hours, poll_interval_minutes, notes
) values (
    'SIM-CPC',
    'SIM-CPC Togo',
    'https://www.cpc-togo.com/',
    'public_market_system',
    1.0,
    48,
    360,
    'Primary Togolese market feed. Trust weight is configurable; lineage and anomaly checks remain mandatory.'
)
on conflict (code) do update set
    name = excluded.name,
    base_url = excluded.base_url,
    updated_at = now();

alter table if exists public.market_price_staging
    add column if not exists anomaly_score numeric,
    add column if not exists anomaly_status text default 'unchecked',
    add column if not exists source_trust_weight numeric default 1.0,
    add column if not exists effective_quality_score numeric;

alter table if exists public.market_prices
    add column if not exists source_trust_weight numeric default 1.0,
    add column if not exists anomaly_score numeric,
    add column if not exists anomaly_status text default 'unchecked';

create index if not exists idx_market_price_staging_anomaly
    on public.market_price_staging (anomaly_status, quality_status);

create index if not exists idx_market_prices_source_observed
    on public.market_prices (source, observed_at desc);

comment on column public.market_data_sources.trust_weight is
    'Operator-configurable weight used with record quality; it is not a claim that every observation is correct.';
comment on column public.market_price_staging.anomaly_score is
    'Robust deviation score versus recent same-product/same-market observations.';
