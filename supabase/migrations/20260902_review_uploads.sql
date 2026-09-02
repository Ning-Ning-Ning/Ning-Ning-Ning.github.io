-- 复盘表上传：文件元数据 + 解析数据表 + Storage 私有桶 + RLS
-- 解析数据来源：复盘表 xlsx 的「月度汇总」sheet（B 列项目 × D~AH 列 1~31 日）

create table if not exists public.review_uploads (
    username    text        not null,
    month       text        not null,            -- 'YYYY-MM'
    file_name   text        not null,
    file_path   text        not null,            -- storage 对象路径 {username}/{month}.xlsx
    uploaded_at timestamptz not null default now(),
    primary key (username, month)
);

create table if not exists public.review_summary (
    username text    not null,
    month    text    not null,
    item     text    not null,                    -- 月度汇总 B 列项目名
    day      int     not null,                    -- 0=月汇总(C列), 1~31=日值(D~AH列)
    value    numeric,
    primary key (username, month, item, day)
);

alter table public.review_uploads  enable row level security;
alter table public.review_summary  enable row level security;

-- ============ review_uploads ============
drop policy if exists "rv_up_select_own_or_gly" on public.review_uploads;
create policy "rv_up_select_own_or_gly" on public.review_uploads
    for select using (
        username = split_part(coalesce(auth.email(), ''), '@', 1)
        or auth.email() = 'gly@curve.local'
    );

drop policy if exists "rv_up_insert_own" on public.review_uploads;
create policy "rv_up_insert_own" on public.review_uploads
    for insert with check (
        username = split_part(coalesce(auth.email(), ''), '@', 1)
    );

drop policy if exists "rv_up_update_own" on public.review_uploads;
create policy "rv_up_update_own" on public.review_uploads
    for update using (
        username = split_part(coalesce(auth.email(), ''), '@', 1)
    ) with check (
        username = split_part(coalesce(auth.email(), ''), '@', 1)
    );

drop policy if exists "rv_up_delete_own" on public.review_uploads;
create policy "rv_up_delete_own" on public.review_uploads
    for delete using (
        username = split_part(coalesce(auth.email(), ''), '@', 1)
    );

-- ============ review_summary ============
drop policy if exists "rv_su_select_own_or_gly" on public.review_summary;
create policy "rv_su_select_own_or_gly" on public.review_summary
    for select using (
        username = split_part(coalesce(auth.email(), ''), '@', 1)
        or auth.email() = 'gly@curve.local'
    );

drop policy if exists "rv_su_insert_own" on public.review_summary;
create policy "rv_su_insert_own" on public.review_summary
    for insert with check (
        username = split_part(coalesce(auth.email(), ''), '@', 1)
    );

drop policy if exists "rv_su_update_own" on public.review_summary;
create policy "rv_su_update_own" on public.review_summary
    for update using (
        username = split_part(coalesce(auth.email(), ''), '@', 1)
    ) with check (
        username = split_part(coalesce(auth.email(), ''), '@', 1)
    );

drop policy if exists "rv_su_delete_own" on public.review_summary;
create policy "rv_su_delete_own" on public.review_summary
    for delete using (
        username = split_part(coalesce(auth.email(), ''), '@', 1)
    );

-- ============ Storage 私有桶 ============
insert into storage.buckets (id, name, public)
values ('review-uploads', 'review-uploads', false)
on conflict (id) do nothing;

-- storage.objects 策略：本人路径 {username}/ 读写删，gly 全读
drop policy if exists "rvo_select_own_or_gly" on storage.objects;
create policy "rvo_select_own_or_gly" on storage.objects
    for select using (
        bucket_id = 'review-uploads'
        and (
            name like split_part(coalesce(auth.email(), ''), '@', 1) || '/%'
            or auth.email() = 'gly@curve.local'
        )
    );

drop policy if exists "rvo_insert_own" on storage.objects;
create policy "rvo_insert_own" on storage.objects
    for insert with check (
        bucket_id = 'review-uploads'
        and name like split_part(coalesce(auth.email(), ''), '@', 1) || '/%'
    );

drop policy if exists "rvo_update_own" on storage.objects;
create policy "rvo_update_own" on storage.objects
    for update using (
        bucket_id = 'review-uploads'
        and name like split_part(coalesce(auth.email(), ''), '@', 1) || '/%'
    ) with check (
        bucket_id = 'review-uploads'
        and name like split_part(coalesce(auth.email(), ''), '@', 1) || '/%'
    );

drop policy if exists "rvo_delete_own" on storage.objects;
create policy "rvo_delete_own" on storage.objects
    for delete using (
        bucket_id = 'review-uploads'
        and name like split_part(coalesce(auth.email(), ''), '@', 1) || '/%'
    );
