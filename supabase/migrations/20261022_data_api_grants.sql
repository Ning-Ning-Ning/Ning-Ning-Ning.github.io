-- Supabase 2026-10-30 Data API 授权变更应对
-- 变更内容：public 中新建的表不再自动获得 Data API 授权（anon/authenticated/service_role），
--          必须显式 GRANT；含 supabase db reset / 预览分支 / 全新项目。
-- 本迁移做两件事：
--   1) 对现有 public 表显式补授权（幂等，等于把当前已有权限固化下来）
--   2) 固化「默认权限」，让今后由 postgres 创建的表/序列/函数自动带上同样的授权
-- 约定（重要）：以后每个 CREATE TABLE 的迁移都必须自带 GRANT，见文末模板。

-- ---------- 1) 现有表：显式授权 ----------
do $$
declare
  t text;
begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('grant select on public.%I to anon', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);
    execute format('grant all on public.%I to service_role', t);
  end loop;
end $$;

-- 现有序列（bigserial 等）同样需要授权，否则 direct insert 会拿不到 nextval
do $$
declare
  s text;
begin
  for s in select sequence_name from information_schema.sequences where sequence_schema = 'public' loop
    execute format('grant usage, select on sequence public.%I to anon', s);
    execute format('grant usage, select on sequence public.%I to authenticated', s);
    execute format('grant usage, select on sequence public.%I to service_role', s);
  end loop;
end $$;

-- ---------- 2) 默认权限：今后新建对象自动授权 ----------
alter default privileges for role postgres in schema public grant select on tables to anon;
alter default privileges for role postgres in schema public grant select, insert, update, delete on tables to authenticated;
alter default privileges for role postgres in schema public grant all on tables to service_role;

alter default privileges for role postgres in schema public grant usage, select on sequences to anon;
alter default privileges for role postgres in schema public grant usage, select on sequences to authenticated;
alter default privileges for role postgres in schema public grant all on sequences to service_role;

alter default privileges for role postgres in schema public grant execute on functions to anon;
alter default privileges for role postgres in schema public grant execute on functions to authenticated;
alter default privileges for role postgres in schema public grant execute on functions to service_role;

-- 说明：RLS 仍然决定能读到哪些行；上面的 GRANT 只决定「能否走到 Data API」。
-- 新建表模板（复制到你的迁移里）：
--   create table public.xxx (...);
--   alter table public.xxx enable row level security;
--   create policy ... ;
--   grant select on public.xxx to anon;
--   grant select, insert, update, delete on public.xxx to authenticated;
--   grant all on public.xxx to service_role;
