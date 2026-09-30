-- Advanced external market-data lineage for CPC/SIM and future feeds.
-- Bronze: raw payloads
-- Silver: normalized staging with quality state
-- Gold: verified market_prices records

create table if not exists public.market_ingestion_runs (
    id uuid primary key default gen_random_uuid(),
    source text not null,
    source_url text,
    status text not null default 'running',
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    endpoint_used text,
    extraction_mode text,
    staged_count integer not null default 0,
    promoted_count integer not null default 0,
    review_count integer not null default 0,
    rejected_count integer not null default 0,
    discovery jsonb,
    error text
);

create index if not exists idx_market_ingestion_runs_source_started
    on public.market_ingestion_runs (source, started_at desc);

create table if not exists public.market_raw_payloads (
    id uuid primary key default gen_random_uuid(),
    run_id uuid references public.market_ingestion_runs(id) on delete set null,
    source text not null,
    source_url text,
    content_type text,
    payload_hash text not null,
    payload_text text,
    extraction_mode text,
    fetched_at timestamptz not null default now(),
    unique (source, payload_hash)
);

create index if not exists idx_market_raw_payloads_run
    on public.market_raw_payloads (run_id);

create table if not exists public.market_price_staging (
    id uuid primary key default gen_random_uuid(),
    run_id uuid references public.market_ingestion_runs(id) on delete set null,
    raw_payload_id uuid references public.market_raw_payloads(id) on delete set null,
    source text not null,
    source_url text,
    record_hash text not null unique,
    market_raw text,
    market_canonical text,
    product_raw text,
    product_canonical text,
    region_raw text,
    locality_raw text,
    observed_at date,
    price numeric,
    unit text,
    currency text default 'FCFA',
    price_type text default 'unknown',
    quality_score numeric,
    quality_status text not null default 'accepted',
    quality_reason text,
    raw_record jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_market_price_staging_run_status
    on public.market_price_staging (run_id, quality_status);

create index if not exists idx_market_price_staging_source_date
    on public.market_price_staging (source, observed_at desc);

create table if not exists public.market_entity_aliases (
    id uuid primary key default gen_random_uuid(),
    source text not null,
    entity_type text not null check (entity_type in ('product', 'market')),
    raw_value text not null,
    canonical_value text not null,
    culture_id uuid references public.cultures(id) on delete set null,
    region_id uuid,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source, entity_type, raw_value)
);

alter table if exists public.market_prices
    add column if not exists source_record_hash text,
    add column if not exists price_type text default 'unknown',
    add column if not exists quality_score numeric,
    add column if not exists ingestion_run_id uuid references public.market_ingestion_runs(id) on delete set null;

do $$
begin
    alter table public.market_prices
        add constraint market_prices_source_record_hash_key unique (source_record_hash);
exception
    when duplicate_object then null;
end $$;

create index if not exists idx_market_prices_ingestion_run
    on public.market_prices (ingestion_run_id);

comment on table public.market_raw_payloads is
    'Bronze layer: immutable public payload snapshots or rendered table snapshots.';
comment on table public.market_price_staging is
    'Silver layer: normalized observations with quality and entity-mapping state.';
comment on table public.market_entity_aliases is
    'Controlled mapping from source labels to AgriTogo products and markets.';
