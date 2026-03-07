create extension if not exists pgcrypto;

alter table if exists public.user_conservation
    add column if not exists id uuid default gen_random_uuid();

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'user_conservation_pkey'
    ) then
        alter table public.user_conservation
            add constraint user_conservation_pkey primary key (id);
    end if;
end $$;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'user_conservation_converstion_id_key'
    ) then
        alter table public.user_conservation
            add constraint user_conservation_converstion_id_key unique (converstion_id);
    end if;
end $$;

create table if not exists public.conversation (
    id uuid primary key default gen_random_uuid(),
    user_conversation_id uuid not null,
    conversation_id uuid not null,
    conversation jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    constraint conversation_user_conversation_id_fkey
        foreign key (user_conversation_id)
        references public.user_conservation(id),
    constraint conversation_conversation_id_fkey
        foreign key (conversation_id)
        references public.user_conservation(converstion_id)
);
