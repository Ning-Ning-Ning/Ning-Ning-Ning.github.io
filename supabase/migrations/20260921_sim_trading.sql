-- 模拟交易（中长期「模拟」页）：服务端行情生成 + 撮合 + 分账号盈亏
-- 方案 B'：pg_cron 每分钟触发 sim_advance()，每 5 分钟产生一个新订单/行情槽；数据滚动保留 30 天
-- 2026-09-21

create extension if not exists pg_cron;

-- ---------- 表 ----------
create table if not exists public.sim_market (
  trade_date  date primary key,
  base_price  numeric(10,2) not null,
  params      jsonb not null default '{}'::jsonb,
  last_slot   int not null default -1,
  created_at  timestamptz not null default now()
);

create table if not exists public.sim_ticks (
  trade_date  date not null,
  slot        int  not null,               -- 0..287，每 5 分钟一个槽
  price       numeric(10,2) not null,
  volume      numeric(12,2) not null default 0,
  ladder      jsonb,                       -- 该槽的买五卖五快照
  created_at  timestamptz not null default now(),
  primary key (trade_date, slot)
);

create table if not exists public.sim_orders (
  id          bigserial primary key,
  trade_date  date not null,
  username    text,                        -- null = 模拟市场挂单
  side        text not null check (side in ('buy','sell')),
  qty         numeric(12,2) not null check (qty > 0),
  price       numeric(10,2) not null,
  filled_qty  numeric(12,2) not null default 0,
  status      text not null default 'pending' check (status in ('pending','partial','filled','cancelled')),
  origin      text not null default 'user' check (origin in ('user','system')),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists sim_orders_open_idx on public.sim_orders (trade_date, status, side, price desc);
create index if not exists sim_orders_user_idx on public.sim_orders (username, trade_date desc, id desc);

create table if not exists public.sim_trades (
  id          bigserial primary key,
  trade_date  date not null,
  slot        int  not null,
  price       numeric(10,2) not null,
  qty         numeric(12,2) not null,
  buyer       text,
  seller      text,
  source      text not null default 'market' check (source in ('market','user')),
  created_at  timestamptz not null default now()
);
create index if not exists sim_trades_day_idx on public.sim_trades (trade_date desc, slot desc, id desc);
create index if not exists sim_trades_user_idx on public.sim_trades (buyer, seller);

create table if not exists public.sim_positions (
  username     text primary key,
  net_qty      numeric(12,2) not null default 0,
  avg_cost     numeric(12,4) not null default 0,
  realized_pnl numeric(14,2) not null default 0,
  updated_at   timestamptz not null default now()
);

-- ---------- 工具函数 ----------
create or replace function public.sim_hash01(p_key text)
returns numeric language sql immutable as $$
  select ((('x' || substr(md5(p_key), 1, 8))::bit(32)::bigint % 1000000)::numeric / 1000000::numeric);
$$;

-- 基准价：优先取当日日前均价（daily_curves），无则 380
create or replace function public.sim_base_price(p_date date)
returns numeric language plpgsql stable as $$
declare v numeric;
begin
  select round(avg(day_ahead_price)::numeric, 2) into v
    from public.daily_curves
   where date = p_date and day_ahead_price is not null and day_ahead_price > 0;
  if v is null or v <= 0 then v := 380.00; end if;
  return greatest(v, 80)::numeric(10,2);
end $$;

-- 日内季节因子（早晚双峰），slot -> 0..1
create or replace function public.sim_season(p_slot int)
returns numeric language sql immutable as $$
  with h as (select (p_slot * 5) / 60.0 as hh)
  select least(1.0, (
      0.55 * exp(-power((select hh from h) - 11.5, 2) / 16.0)
    + 1.00 * exp(-power((select hh from h) - 19.5, 2) / 12.0)
    + 0.25 * exp(-power((select hh from h) - 8.0, 2) / 8.0)
  ))::numeric;
$$;

-- 该槽的阶梯挂单（买五卖五）
create or replace function public.sim_ladder(p_date date, p_slot int, p_price numeric)
returns jsonb language plpgsql immutable as $$
declare
  i int; bid_p numeric; ask_p numeric; bid_q numeric; ask_q numeric;
  bids jsonb := '[]'::jsonb; asks jsonb := '[]'::jsonb;
begin
  for i in 1..5 loop
    bid_p := round((p_price - 0.5 * i - 0.1 * floor(sim_hash01(p_date::text || ':' || p_slot || ':bidp:' || i) * 5))::numeric, 1);
    ask_p := round((p_price + 0.5 * i + 0.1 * floor(sim_hash01(p_date::text || ':' || p_slot || ':askp:' || i) * 5))::numeric, 1);
    bid_q := round((20 + 480 * power(sim_hash01(p_date::text || ':' || p_slot || ':bidq:' || i), 2.2))::numeric, 0);
    ask_q := round((20 + 480 * power(sim_hash01(p_date::text || ':' || p_slot || ':askq:' || i), 2.2))::numeric, 0);
    bids := bids || jsonb_build_object('price', bid_p, 'qty', bid_q);
    asks := asks || jsonb_build_object('price', ask_p, 'qty', ask_q);
  end loop;
  return jsonb_build_object('bids', bids, 'asks', asks);
end $$;

-- ---------- 持仓与盈亏 ----------
create or replace function public.sim_apply_fill(p_user text, p_side text, p_qty numeric, p_price numeric)
returns void language plpgsql as $$
declare
  pos public.sim_positions%rowtype;
  close_qty numeric; new_net numeric; pnl numeric := 0;
begin
  if p_user is null then return; end if;
  select * into pos from public.sim_positions where username = p_user;
  if not found then
    insert into public.sim_positions(username) values (p_user) returning * into pos;
  end if;

  if p_side = 'buy' then
    if pos.net_qty >= 0 then
      new_net := pos.net_qty + p_qty;
      pos.avg_cost := (pos.net_qty * pos.avg_cost + p_qty * p_price) / new_net;
    else
      close_qty := least(p_qty, -pos.net_qty);
      pnl := (pos.avg_cost - p_price) * close_qty;        -- 空头平仓
      new_net := pos.net_qty + p_qty;
      if new_net > 0 then pos.avg_cost := p_price; end if;
      if new_net = 0 then pos.avg_cost := 0; end if;
    end if;
  else
    if pos.net_qty <= 0 then
      new_net := pos.net_qty - p_qty;
      pos.avg_cost := (abs(pos.net_qty) * pos.avg_cost + p_qty * p_price) / abs(new_net);
    else
      close_qty := least(p_qty, pos.net_qty);
      pnl := (p_price - pos.avg_cost) * close_qty;        -- 多头平仓
      new_net := pos.net_qty - p_qty;
      if new_net < 0 then pos.avg_cost := p_price; end if;
      if new_net = 0 then pos.avg_cost := 0; end if;
    end if;
  end if;

  update public.sim_positions
     set net_qty = new_net,
         avg_cost = round(pos.avg_cost::numeric, 4),
         realized_pnl = realized_pnl + pnl,
         updated_at = now()
   where username = p_user;
end $$;

-- 分账号总盈亏（已实现 + 浮动）
create or replace function public.sim_accounts_pnl()
returns table(username text, net_qty numeric, avg_cost numeric, realized_pnl numeric, unrealized_pnl numeric, total_pnl numeric, last_price numeric)
language plpgsql stable security definer set search_path = public as $$
declare v_last numeric;
begin
  select t.price into v_last
    from public.sim_ticks t
   order by t.trade_date desc, t.slot desc
   limit 1;
  v_last := coalesce(v_last, 0);
  return query
  select p.username, p.net_qty, p.avg_cost, p.realized_pnl,
         round((p.net_qty * (v_last - p.avg_cost))::numeric, 2) as unrealized_pnl,
         round((p.realized_pnl + p.net_qty * (v_last - p.avg_cost))::numeric, 2) as total_pnl,
         v_last
    from public.sim_positions p
   order by 6 desc;
end $$;

-- ---------- 撮合 ----------
create or replace function public.sim_match_slot(p_date date, p_slot int)
returns int language plpgsql as $$
declare
  v_price numeric; v_rec record; v_filled int := 0; v_join boolean;
begin
  select price into v_price from public.sim_ticks where trade_date = p_date and slot = p_slot;
  if v_price is null then return 0; end if;

  for v_rec in
    select * from public.sim_orders
     where trade_date = p_date and status in ('pending','partial')
       and ((side = 'buy' and price >= v_price) or (side = 'sell' and price <= v_price))
     order by (case when side = 'buy' then 0 else 1 end), price desc, id
  loop
    v_join := (v_rec.price = v_price);
    update public.sim_orders
       set filled_qty = qty, status = 'filled', updated_at = now()
     where id = v_rec.id;

    insert into public.sim_trades(trade_date, slot, price, qty, buyer, seller, source)
    values (p_date, p_slot, v_price, v_rec.qty - v_rec.filled_qty,
            case when v_rec.side = 'buy' then v_rec.username else null end,
            case when v_rec.side = 'sell' then v_rec.username else null end,
            case when v_rec.origin = 'user' then 'user' else 'market' end);

    if v_rec.origin = 'user' then
      perform public.sim_apply_fill(v_rec.username, v_rec.side, v_rec.qty - v_rec.filled_qty, v_price);
    end if;
    v_filled := v_filled + 1;
  end loop;
  return v_filled;
end $$;

-- 推进到当前槽（可补齐历史槽，幂等）
create or replace function public.sim_advance(p_until timestamp with time zone default now())
returns jsonb language plpgsql as $$
declare
  v_date date := (p_until at time zone 'Asia/Shanghai')::date;
  v_slot int := floor(extract(epoch from (p_until at time zone 'Asia/Shanghai')::time) / 300);
  v_last int; v_prev numeric; v_base numeric; v_price numeric;
  v_season numeric; v_ref numeric; v_n numeric; v_vol numeric; v_s int;
  v_side text; v_qq numeric; v_op numeric; v_new int := 0; v_matched int := 0;
  v_orders int := 0; v_created boolean;
begin
  if v_slot > 287 then v_slot := 287; end if;

  insert into public.sim_market(trade_date, base_price)
  values (v_date, public.sim_base_price(v_date))
  on conflict (trade_date) do nothing;

  select base_price, last_slot into v_base, v_last from public.sim_market where trade_date = v_date;

  for v_s in (v_last + 1)..v_slot loop
    select price into v_prev from public.sim_ticks where trade_date = v_date and slot = v_s - 1;
    if v_prev is null then v_prev := v_base; end if;

    v_season := public.sim_season(v_s);
    v_ref := v_base * (0.88 + 0.24 * v_season);
    v_n := (public.sim_hash01(v_date::text || ':n:' || v_s) - 0.5) * 2.0;
    v_price := v_prev + 0.08 * (v_ref - v_prev) + v_ref * 0.006 * v_n;
    if public.sim_hash01(v_date::text || ':jump:' || v_s) > 0.994 then
      v_price := v_price * (1 + 0.02 * ((public.sim_hash01(v_date::text || ':js:' || v_s) - 0.5) * 2));
    end if;
    v_price := round(greatest(v_price, v_base * 0.6)::numeric, 2);
    v_vol := round((80 * exp(1.1 * (public.sim_hash01(v_date::text || ':v:' || v_s) - 0.4))
                    * (0.6 + v_season))::numeric, 2);

    insert into public.sim_ticks(trade_date, slot, price, volume, ladder)
    values (v_date, v_s, v_price, v_vol, public.sim_ladder(v_date, v_s, v_price))
    on conflict (trade_date, slot) do nothing;
    v_created := found;
    v_new := v_new + 1;

    -- 每槽生成 1 笔模拟市场订单（5 分钟一个新订单）
    v_side := case when public.sim_hash01(v_date::text || ':side:' || v_s) > 0.5 then 'buy' else 'sell' end;
    v_qq := round((5 + 55 * power(public.sim_hash01(v_date::text || ':q:' || v_s), 1.6))::numeric, 0);
    v_op := round((v_price + (case when v_side = 'buy' then -1 else 1 end)
                   * (0.5 * floor(public.sim_hash01(v_date::text || ':op:' || v_s) * 4)))::numeric, 1);
    insert into public.sim_orders(trade_date, username, side, qty, price, origin, status)
    values (v_date, null, v_side, v_qq, v_op, 'system', 'pending');
    v_orders := v_orders + 1;

    v_matched := v_matched + public.sim_match_slot(v_date, v_s);
  end loop;

  update public.sim_market set last_slot = greatest(last_slot, v_slot) where trade_date = v_date;

  return jsonb_build_object('date', v_date, 'slot', v_slot, 'new_ticks', v_new,
                            'new_orders', v_orders, 'matched', v_matched);
end $$;

-- ---------- 下单 / 撤单（前端走 RPC） ----------
create or replace function public.sim_place_order(p_username text, p_side text, p_qty numeric, p_price numeric)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  v_date date := (now() at time zone 'Asia/Shanghai')::date;
  v_slot int; v_price numeric; v_id bigint; v_status text; v_matched jsonb;
begin
  if p_side not in ('buy','sell') then raise exception '方向必须是 buy 或 sell'; end if;
  if p_qty is null or p_qty <= 0 then raise exception '电量必须大于 0'; end if;
  if p_price is null or p_price <= 0 then raise exception '价格必须大于 0'; end if;

  perform public.sim_advance();
  select max(slot), max(price) into v_slot, v_price from public.sim_ticks where trade_date = v_date;
  if v_price is null then raise exception '行情尚未生成，请稍后重试'; end if;

  insert into public.sim_orders(trade_date, username, side, qty, price, origin, status)
  values (v_date, p_username, p_side, p_qty, p_price, 'user', 'pending')
  returning id into v_id;

  if (p_side = 'buy' and p_price >= v_price) or (p_side = 'sell' and p_price <= v_price) then
    update public.sim_orders set filled_qty = qty, status = 'filled', updated_at = now() where id = v_id;
    insert into public.sim_trades(trade_date, slot, price, qty, buyer, seller, source)
    values (v_date, v_slot, v_price, p_qty,
            case when p_side = 'buy' then p_username else null end,
            case when p_side = 'sell' then p_username else null end, 'user');
    perform public.sim_apply_fill(p_username, p_side, p_qty, v_price);
    v_status := 'filled';
  else
    v_status := 'pending';
  end if;

  select jsonb_build_object('id', id, 'side', side, 'qty', qty, 'price', price, 'status', status,
                            'filled_qty', filled_qty, 'market_price', v_price)
    into v_matched from public.sim_orders where id = v_id;
  return v_matched;
end $$;

create or replace function public.sim_cancel_order(p_username text, p_id bigint)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_row public.sim_orders%rowtype;
begin
  select * into v_row from public.sim_orders
   where id = p_id and username = p_username and status in ('pending','partial');
  if not found then
    return jsonb_build_object('ok', false, 'message', '委托不存在或不可撤销');
  end if;
  update public.sim_orders set status = 'cancelled', updated_at = now() where id = p_id;
  return jsonb_build_object('ok', true, 'id', p_id);
end $$;

-- ---------- 保留 30 天 ----------
create or replace function public.sim_purge(p_days int default 30)
returns jsonb language plpgsql as $$
declare v_cut date := ((now() at time zone 'Asia/Shanghai')::date - p_days);
        c1 int; c2 int; c3 int; c4 int; c5 int;
begin
  delete from public.sim_trades   where trade_date < v_cut; get diagnostics c1 = row_count;
  delete from public.sim_orders   where trade_date < v_cut; get diagnostics c2 = row_count;
  delete from public.sim_ticks    where trade_date < v_cut; get diagnostics c3 = row_count;
  delete from public.sim_market   where trade_date < v_cut; get diagnostics c4 = row_count;
  delete from public.sim_orders   where origin = 'system' and status in ('pending','partial')
                                     and trade_date < ((now() at time zone 'Asia/Shanghai')::date - 3);
  get diagnostics c5 = row_count;
  return jsonb_build_object('cut', v_cut, 'trades', c1, 'orders', c2, 'ticks', c3, 'market', c4, 'stale_system_orders', c5);
end $$;

-- ---------- RLS ----------
alter table public.sim_market    enable row level security;
alter table public.sim_ticks     enable row level security;
alter table public.sim_orders    enable row level security;
alter table public.sim_trades    enable row level security;
alter table public.sim_positions enable row level security;

drop policy if exists sim_market_read on public.sim_market;
create policy sim_market_read on public.sim_market for select to authenticated using (true);

drop policy if exists sim_ticks_read on public.sim_ticks;
create policy sim_ticks_read on public.sim_ticks for select to authenticated using (true);

drop policy if exists sim_trades_read on public.sim_trades;
create policy sim_trades_read on public.sim_trades for select to authenticated using (true);

drop policy if exists sim_orders_read on public.sim_orders;
create policy sim_orders_read on public.sim_orders for select to authenticated
  using (origin = 'system'
         or username = split_part(coalesce(auth.email(), ''), '@', 1)
         or split_part(coalesce(auth.email(), ''), '@', 1) = 'gly');

drop policy if exists sim_orders_write on public.sim_orders;
create policy sim_orders_write on public.sim_orders for all to authenticated
  using (username = split_part(coalesce(auth.email(), ''), '@', 1))
  with check (username = split_part(coalesce(auth.email(), ''), '@', 1) and origin = 'user');

drop policy if exists sim_positions_read on public.sim_positions;
create policy sim_positions_read on public.sim_positions for select to authenticated using (true);

-- ---------- 权限 ----------
grant select on public.sim_market, public.sim_ticks, public.sim_orders, public.sim_trades, public.sim_positions to authenticated;
grant execute on function public.sim_accounts_pnl() to authenticated;
grant execute on function public.sim_place_order(text, text, numeric, numeric) to authenticated;
grant execute on function public.sim_cancel_order(text, bigint) to authenticated;
grant execute on function public.sim_advance(timestamp with time zone) to authenticated;

-- ---------- 定时任务 ----------
do $$
begin
  if exists (select 1 from cron.job where jobname = 'sim-advance') then
    perform cron.unschedule('sim-advance');
  end if;
  if exists (select 1 from cron.job where jobname = 'sim-purge') then
    perform cron.unschedule('sim-purge');
  end if;
end $$;
select cron.schedule('sim-advance', '* * * * *', $$select public.sim_advance();$$);
select cron.schedule('sim-purge', '10 3 * * *', $$select public.sim_purge();$$);
