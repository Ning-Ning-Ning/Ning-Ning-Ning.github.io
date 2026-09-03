-- 复盘统计：review_summary 增加原始行序 ord（月度汇总 sheet 中项目首次出现的行号）
alter table public.review_summary add column if not exists ord integer;
