-- 全员总览对所有账号可见：放开 user_adjustments 的 SELECT（读全部）
-- 2026-08-07 用户需求：全员总览页面所有账号都能访问，
-- 需读取所有账号的电费变化数据。
-- 仅放开读取；INSERT/UPDATE/DELETE 仍限本人（策略不变）。

DROP POLICY IF EXISTS user_adjustments_select ON public.user_adjustments;

CREATE POLICY user_adjustments_select ON public.user_adjustments
  FOR SELECT TO authenticated
  USING (true);

-- 复核既有写入策略仍存在
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname='public' AND tablename='user_adjustments'
      AND policyname='user_adjustments_insert'
  ) THEN
    RAISE NOTICE 'user_adjustments_insert policy missing';
  END IF;
END $$;
