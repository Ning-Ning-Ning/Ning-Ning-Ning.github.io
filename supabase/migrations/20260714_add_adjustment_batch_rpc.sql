create or replace function public.update_daily_curve_adjustments(
  target_date date,
  updates jsonb
)
returns integer
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  item_count integer;
  updated_count integer;
begin
  if target_date is null then
    raise exception 'target_date is required';
  end if;
  if jsonb_typeof(updates) <> 'array' then
    raise exception 'updates must be an array';
  end if;

  item_count := jsonb_array_length(updates);
  if item_count < 1 or item_count > 24 then
    raise exception 'updates must contain between 1 and 24 items';
  end if;

  if exists (
    select 1
    from jsonb_array_elements(updates) item
    where jsonb_typeof(item) <> 'object'
      or not (item ? 'hour')
      or not (item ? 'adjusted_value')
      or jsonb_typeof(item->'hour') <> 'number'
      or jsonb_typeof(item->'adjusted_value') <> 'number'
  ) then
    raise exception 'each update must contain numeric hour and adjusted_value';
  end if;

  if exists (
    select 1
    from jsonb_to_recordset(updates) as item(hour numeric, adjusted_value numeric)
    where hour <> trunc(hour)
      or hour < 0 or hour > 23
      or adjusted_value < 0 or adjusted_value > 1000
  ) then
    raise exception 'hour or adjusted_value is out of range';
  end if;

  if (
    select count(distinct hour)
    from jsonb_to_recordset(updates) as item(hour integer, adjusted_value numeric)
  ) <> item_count then
    raise exception 'hours must be unique';
  end if;

  update public.daily_curves curves
  set adjusted_value = item.adjusted_value,
      updated_at = now()
  from jsonb_to_recordset(updates) as item(hour integer, adjusted_value numeric)
  where curves.date = target_date
    and curves.hour = item.hour;

  get diagnostics updated_count = row_count;
  if updated_count <> item_count then
    raise exception 'one or more target rows do not exist';
  end if;

  return updated_count;
end;
$$;

revoke all on function public.update_daily_curve_adjustments(date, jsonb)
  from public, anon, authenticated;
grant execute on function public.update_daily_curve_adjustments(date, jsonb)
  to service_role;
