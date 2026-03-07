create table if not exists public.webhook_message_dedup (
    message_id text primary key,
    entity_id text,
    phone_number_id text,
    phone_number text,
    received_at timestamptz not null default now()
);
