-- Persistent cache of discovered market-data endpoints.
-- Browser discovery is the fallback; successful endpoints become the fast path.

create table if not exists public.market_source_endpoints (
    id uuid primary key default gen_random_uuid(),
    source text not null references public.market_data_sources(code)
        on update cascade on delete cascade,
    url text not null,
    method text not null default 'GET',
    request_post_data text,
    content_type text,
    discovered_via text,
    discovery_score integer not null default 0,
    etag text,
    last_modified text,
    active boolean not null default true,
    success_count integer not null default 0,
    failure_count integer not null default 0,
    consecutive_failures integer not null default 0,
    last_checked_at timestamptz,
    last_success_at timestamptz,
    last_error text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source, method, url)
);

create index if not exists idx_market_source_endpoints_best
    on public.market_source_endpoints (
        source,
        active,
        consecutive_failures,
        discovery_score desc,
        last_success_at desc
    );

comment on table public.market_source_endpoints is
    'Discovered public data endpoints. Successful endpoints are reused before browser rediscovery.';
comment on column public.market_source_endpoints.etag is
    'HTTP validator used with If-None-Match when supported.';
comment on column public.market_source_endpoints.last_modified is
    'HTTP validator used with If-Modified-Since when ETag is unavailable.';
