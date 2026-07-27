-- 用户账号功能：每个账号独立的调整后用电量曲线
-- 调整后曲线从 public.daily_curves.adjusted_value（全局）迁移为按用户隔离存储。
-- 实际/预测用电量仍读公用 daily_curves。

CREATE TABLE IF NOT EXISTS public.user_adjustments (
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  curve_date date NOT NULL,
  hour integer NOT NULL CHECK (hour BETWEEN 0 AND 23),
  adjusted_value numeric NOT NULL CHECK (adjusted_value >= 0 AND adjusted_value <= 1000),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, curve_date, hour)
);

ALTER TABLE public.user_adjustments ENABLE ROW LEVEL SECURITY;

-- 每个登录用户只能读写自己的调整数据
CREATE POLICY user_adjustments_select ON public.user_adjustments
  FOR SELECT TO authenticated USING (user_id = auth.uid());

CREATE POLICY user_adjustments_insert ON public.user_adjustments
  FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());

CREATE POLICY user_adjustments_update ON public.user_adjustments
  FOR UPDATE TO authenticated USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY user_adjustments_delete ON public.user_adjustments
  FOR DELETE TO authenticated USING (user_id = auth.uid());

GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_adjustments TO authenticated;

-- 自动维护 updated_at
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END $$;

CREATE TRIGGER user_adjustments_updated_at
  BEFORE UPDATE ON public.user_adjustments
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
