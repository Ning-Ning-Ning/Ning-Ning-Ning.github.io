# 用户用电量曲线

GitHub Pages 页面通过 Supabase Data API 读取 `public.daily_curves`，按日期同时展示实际、预测和调整后用电量。

## 数据映射

源文件 `excel.xlsx` 的表头必须为：

`年月日 / 小时 / 实际用电量MWh / 预测用电量MWh / 调整后用电量MWh`

Excel 小时 `1..24` 导入为数据库 `hour = 0..23`：

- `实际用电量MWh` → `actual_value`；2026-05-24（含）起保存为 `NULL`；
- `预测用电量MWh` → `predicted_value`，空单元格保存为 `NULL`；
- `调整后用电量MWh` → `adjusted_value`，空单元格保存为 `NULL`。

页面展示时，如果 `adjusted_value` 为空，则默认采用同一时段的预测用电量；若预测也为空，则显示暂无数据，不按 0 处理。

## 图表和编辑

- 默认日期为浏览器本地系统日期的后一天；超出数据范围时使用最近边界。
- 重叠时从上到下为预测、调整后、实际；SVG 实际绘制顺序为实际 → 调整后 → 预测。
- 调整后用电量使用紫色虚线。
- 点击“框选调整点”后可在图中拖出选择框；只会选择调整后曲线的点，可多次框选累加。
- 明细表中的复选框提供键盘选择方式。
- 编辑面板提供两种调整模式：
  - **直接设置 MWh**：逐点输入最终数值，或”全部设为”批量填值。
  - **按预测值比例**：输入比例系数，`调整后用电量 = 预测用电量 × 比例`（例如预测 10 × 比例 1.2 = 12 MWh）。每点实时显示预测值和计算预览。”全部比例设为”可批量应用，各点按各自预测值计算出不同的最终 MWh。
  - 直接设置最小变化幅度为 0.001 MWh；比例范围 0–100，最终结果四舍五入到 3 位小数且不超过 1000 MWh。预测值为 0 时结果固定为 0；预测值为空时该时段不可使用比例模式。
  - 两套模式的未保存输入在切换时互相保留，日期变更、清空选择或保存后清理。
  - 无论哪种模式，最终保存的均为 MWh 数值，比例仅为前端计算方式，不影响数据库结构或写入协议。

调整值是**公开全局数据**：任何访问网页的人都能保存修改，修改会影响所有访问者。

## 写入安全边界

浏览器只能通过 Supabase Edge Function `update-curve-adjustments` 保存调整值。Edge Function 校验日期、唯一小时、1–24 项批量上限以及 0–1000 MWh 数值范围，再通过仅 `service_role` 可执行的数据库 RPC 原子更新。

`daily_curves` 对 `anon` 和 `authenticated` 仍只有 `SELECT` 权限，浏览器不能直接调用 REST `UPDATE`，secret/service-role key 不会出现在网页或 Git 中。公开编辑不等同于身份认证；Edge Function 的校验用于保护数据结构和事务完整性，不限制谁可以修改。

## 导入数据

```bash
export SUPABASE_URL="https://<project-ref>.supabase.co"
export SUPABASE_IMPORT_KEY="<temporary-write-capable-key>"
python scripts/import_excel.py /path/to/excel.xlsx
```

仅校验文件：

```bash
python scripts/import_excel.py /path/to/excel.xlsx --validate-only
```
