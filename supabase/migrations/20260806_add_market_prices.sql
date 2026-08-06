-- 为公用日电量曲线增加日前与实时市场电价。
-- 电价允许负值；空值表示 Excel 对应时段暂无价格。

ALTER TABLE public.daily_curves
  ADD COLUMN IF NOT EXISTS day_ahead_price numeric,
  ADD COLUMN IF NOT EXISTS real_time_price numeric;

COMMENT ON COLUMN public.daily_curves.day_ahead_price IS '日前电价，单位：元/MWh';
COMMENT ON COLUMN public.daily_curves.real_time_price IS '实时电价，单位：元/MWh';
