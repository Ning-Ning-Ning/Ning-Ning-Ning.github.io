# 光伏发电量曲线

GitHub Pages 页面通过 Supabase Data API 读取 `public.daily_curves`，按日期展示 24 个时段的发电量折线图。

## 数据映射

源文件 `excel.xlsx` 的表头为 `年月日 / 小时 / 电量MWh`。Excel 中的小时 `1..24` 表示第 1 至第 24 时段；导入时映射为数据库 `hour = 0..23`：

- Excel 小时 1 → 数据库 hour 0 → 00:00–01:00
- Excel 小时 24 → 数据库 hour 23 → 23:00–24:00

图表横轴范围为 0–24，共 24 个时段；每个数据点绘制在对应时段中点。

## 导入数据

脚本会校验表头、空值、重复项、小时范围以及每天是否恰好 24 条记录。写入凭据必须通过环境变量传入，不得提交到仓库。

```bash
export SUPABASE_URL="https://<project-ref>.supabase.co"
export SUPABASE_IMPORT_KEY="<temporary-write-capable-key>"
python scripts/import_excel.py /path/to/excel.xlsx
```

仅校验文件：

```bash
python scripts/import_excel.py /path/to/excel.xlsx --validate-only
```

## 安全模型

浏览器中只使用 Supabase publishable key。`daily_curves` 已启用 Row Level Security，匿名和已认证客户端仅有 `SELECT` 权限；写入操作只能通过受控的导入通道执行。publishable key 可以出现在静态前端中，但 secret/service-role key 绝不能写入网页或提交到 Git。
