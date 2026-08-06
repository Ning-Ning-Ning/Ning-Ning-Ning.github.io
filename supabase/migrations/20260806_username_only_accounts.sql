-- 固定账号免密登录改造（仅用户名，无注册）
-- 12 个固定账号：gly(管理员)、wanliyang、songningning、zhangchenyue、
-- liangweiqi、liubingyan、liuziye、luna、songyihan、wangyanshu、
-- xumanli、zhengkezhuo
--
-- 前端只显示用户名输入框；密码由前端按固定规则从用户名派生（仓库内公开，
-- 等价于“仅用户名”安全级别，用户已确认接受该风险）。
-- user_adjustments 增加 username 冗余列，用于按账号读取数据；
-- 管理员 gly 可 SELECT 所有账号的调整数据（只读查看），写入仍限本人。

-- 1) 增加 username 列，并迁移既有行（按 auth.users.email 前缀回填）
ALTER TABLE public.user_adjustments
  ADD COLUMN IF NOT EXISTS username text;

UPDATE public.user_adjustments ua
SET username = split_part(au.email, '@', 1)
FROM auth.users au
WHERE au.id = ua.user_id
  AND ua.username IS NULL;

-- 无法匹配到合法固定账号的旧数据删除（历史测试数据，正常应为空表）
DELETE FROM public.user_adjustments
WHERE username IS NULL
   OR username NOT IN (
     'gly','wanliyang','songningning','zhangchenyue','liangweiqi',
     'liubingyan','liuziye','luna','songyihan','wangyanshu',
     'xumanli','zhengkezhuo'
   );

ALTER TABLE public.user_adjustments
  ALTER COLUMN username SET NOT NULL;

CREATE INDEX IF NOT EXISTS user_adjustments_username_curve_date_idx
  ON public.user_adjustments (username, curve_date, hour);

-- 2) RLS 辅助函数：从 JWT 中取当前用户名和管理员判断
-- 使用受信任的 email 声明（由 Auth 服务签发，用户不可自行修改）
-- 而非 user_metadata（用户可编辑，不能用于授权决策）。
CREATE OR REPLACE FUNCTION public.jwt_username()
RETURNS text LANGUAGE sql STABLE AS $$
  SELECT nullif(split_part(coalesce(auth.jwt()->>'email',''), '@', 1), '');
$$;

CREATE OR REPLACE FUNCTION public.jwt_is_admin()
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT auth.jwt()->>'email' = 'gly@curve.local';
$$;

-- 3) 重建 RLS 策略：普通账号仅读写本人；管理员可读全部、仅写本人
DROP POLICY IF EXISTS user_adjustments_select ON public.user_adjustments;
DROP POLICY IF EXISTS user_adjustments_insert ON public.user_adjustments;
DROP POLICY IF EXISTS user_adjustments_update ON public.user_adjustments;
DROP POLICY IF EXISTS user_adjustments_delete ON public.user_adjustments;

CREATE POLICY user_adjustments_select ON public.user_adjustments
  FOR SELECT TO authenticated
  USING (username = public.jwt_username() OR public.jwt_is_admin());

CREATE POLICY user_adjustments_insert ON public.user_adjustments
  FOR INSERT TO authenticated
  WITH CHECK (username = public.jwt_username() AND user_id = auth.uid());

CREATE POLICY user_adjustments_update ON public.user_adjustments
  FOR UPDATE TO authenticated
  USING (username = public.jwt_username() AND user_id = auth.uid())
  WITH CHECK (username = public.jwt_username() AND user_id = auth.uid());

CREATE POLICY user_adjustments_delete ON public.user_adjustments
  FOR DELETE TO authenticated
  USING (username = public.jwt_username() AND user_id = auth.uid());

-- 4) 确保函数可被 authenticated 调用（默认 PUBLIC EXECUTE 已包含）
GRANT EXECUTE ON FUNCTION public.jwt_username() TO authenticated;
GRANT EXECUTE ON FUNCTION public.jwt_is_admin() TO authenticated;
