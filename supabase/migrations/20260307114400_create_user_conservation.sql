create extension if not exists pgcrypto;

create table if not exists public.user_conservation (
    user_id uuid default gen_random_uuid(),
    converstion_id uuid default gen_random_uuid(),
    entity_id text,
    phone_number_id text,
    phone_number text,
    profile_name text,
    msg_initated_at timestamptz,
    msg_delivered_at timestamptz
);
