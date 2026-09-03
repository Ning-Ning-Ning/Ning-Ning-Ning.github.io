-- 中长期持仓/申报：复盘 xlsx「持仓数据」「交易记录」sheet 解析表 + RLS（复刻 review_summary 策略）

create table if not exists public.review_holding (
    username text not null,
    month    text not null,                 -- 'YYYY-MM'
    block    text not null,                 -- 预估用电量 / 中长期合约电量剩余可买限额(MWh) / 中长期合约电量(MWh) / 中长期合约加权电价(元/MWh)
    hour     int  not null,                 -- 0~23；-1=日合计行
    day      int  not null,                 -- 1~31
    value    numeric,
    primary key (username, month, block, hour, day)
);

create table if not exists public.review_holding_summary (
    username    text not null,
    month       text not null,
    item        text not null,              -- 年度+月度电量 / 月度+月内电量 / 持仓电量 / 累计交易电量 / <block>｜月合计
    value       numeric,
    limit_kind  text,                       -- 下限 / 上限 / null
    limit_value numeric,
    primary key (username, month, item)
);

create table if not exists public.review_trades (
    username text not null,
    month    text not null,
    win      text not null,                 -- 交易窗口（年度双边交易…月内周双边交易）
    metric   text not null,                 -- 电量 / 电价
    hour     int  not null,                 -- 0~23；-1=日合计行
    day      int  not null,                 -- 1~31
    value    numeric,
    primary key (username, month, win, metric, hour, day)
);

create table if not exists public.review_trades_summary (
    username    text not null,
    month       text not null,
    win         text not null,
    metric      text not null,              -- 电量 / 电价
    month_total numeric,
    primary key (username, month, win, metric)
);

alter table public.review_holding          enable row level security;
alter table public.review_holding_summary  enable row level security;
alter table public.review_trades           enable row level security;
alter table public.review_trades_summary   enable row level security;

-- ============ review_holding ============
drop policy if exists "rv_ho_select_own_or_gly" on public.review_holding;
create policy "rv_ho_select_own_or_gly" on public.review_holding
    for select using (
        username = split_part(coalesce(auth.email(), ''), '@', 1)
        or auth.email() = 'gly@curve.local'
    );
drop policy if exists "rv_ho_insert_own" on public.review_holding;
create policy "rv_ho_insert_own" on public.review_holding
    for insert with check (username = split_part(coalesce(auth.email(), ''), '@', 1));
drop policy if exists "rv_ho_update_own" on public.review_holding;
create policy "rv_ho_update_own" on public.review_holding
    for update using (username = split_part(coalesce(auth.email(), ''), '@', 1))
    with check (username = split_part(coalesce(auth.email(), ''), '@', 1));
drop policy if exists "rv_ho_delete_own" on public.review_holding;
create policy "rv_ho_delete_own" on public.review_holding
    for delete using (username = split_part(coalesce(auth.email(), ''), '@', 1));

-- ============ review_holding_summary ============
drop policy if exists "rv_hs_select_own_or_gly" on public.review_holding_summary;
create policy "rv_hs_select_own_or_gly" on public.review_holding_summary
    for select using (
        username = split_part(coalesce(auth.email(), ''), '@', 1)
        or auth.email() = 'gly@curve.local'
    );
drop policy if exists "rv_hs_insert_own" on public.review_holding_summary;
create policy "rv_hs_insert_own" on public.review_holding_summary
    for insert with check (username = split_part(coalesce(auth.email(), ''), '@', 1));
drop policy if exists "rv_hs_update_own" on public.review_holding_summary;
create policy "rv_hs_update_own" on public.review_holding_summary
    for update using (username = split_part(coalesce(auth.email(), ''), '@', 1))
    with check (username = split_part(coalesce(auth.email(), ''), '@', 1));
drop policy if exists "rv_hs_delete_own" on public.review_holding_summary;
create policy "rv_hs_delete_own" on public.review_holding_summary
    for delete using (username = split_part(coalesce(auth.email(), ''), '@', 1));

-- ============ review_trades ============
drop policy if exists "rv_tr_select_own_or_gly" on public.review_trades;
create policy "rv_tr_select_own_or_gly" on public.review_trades
    for select using (
        username = split_part(coalesce(auth.email(), ''), '@', 1)
        or auth.email() = 'gly@curve.local'
    );
drop policy if exists "rv_tr_insert_own" on public.review_trades;
create policy "rv_tr_insert_own" on public.review_trades
    for insert with check (username = split_part(coalesce(auth.email(), ''), '@', 1));
drop policy if exists "rv_tr_update_own" on public.review_trades;
create policy "rv_tr_update_own" on public.review_trades
    for update using (username = split_part(coalesce(auth.email(), ''), '@', 1))
    with check (username = split_part(coalesce(auth.email(), ''), '@', 1));
drop policy if exists "rv_tr_delete_own" on public.review_trades;
create policy "rv_tr_delete_own" on public.review_trades
    for delete using (username = split_part(coalesce(auth.email(), ''), '@', 1));

-- ============ review_trades_summary ============
drop policy if exists "rv_ts_select_own_or_gly" on public.review_trades_summary;
create policy "rv_ts_select_own_or_gly" on public.review_trades_summary
    for select using (
        username = split_part(coalesce(auth.email(), ''), '@', 1)
        or auth.email() = 'gly@curve.local'
    );
drop policy if exists "rv_ts_insert_own" on public.review_trades_summary;
create policy "rv_ts_insert_own" on public.review_trades_summary
    for insert with check (username = split_part(coalesce(auth.email(), ''), '@', 1));
drop policy if exists "rv_ts_update_own" on public.review_trades_summary;
create policy "rv_ts_update_own" on public.review_trades_summary
    for update using (username = split_part(coalesce(auth.email(), ''), '@', 1))
    with check (username = split_part(coalesce(auth.email(), ''), '@', 1));
drop policy if exists "rv_ts_delete_own" on public.review_trades_summary;
create policy "rv_ts_delete_own" on public.review_trades_summary
    for delete using (username = split_part(coalesce(auth.email(), ''), '@', 1));
