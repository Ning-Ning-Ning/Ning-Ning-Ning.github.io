---
name: verify
summary: Verify the editable three-series Supabase electricity chart.
---

# Verify

1. Serve the workspace root with `python -m http.server 4173` and open `/Ning-Ning-Ning.github.io/`.
2. Confirm the default date is the browser-local date plus one day, clamped to the database range. With local date 2026-07-14, expect 2026-07-15.
3. Inspect SVG curve order: actual path first, adjusted second, predicted last. Confirm the legend says predicted top, adjusted middle/dashed, actual bottom.
4. Enable “框选调整点”, drag across multiple adjusted points, and confirm only adjusted hours enter selection. Repeat to accumulate; clear selection to reset.
5. Use table checkboxes as the keyboard alternative; disabled checkboxes must correspond to null adjusted effective values.
6. In the editor (default direct mode), test per-hour inputs and “全部设为”. Invalid/negative/out-of-range values must remain unsaved with an inline error.
7. Switch to “按预测值比例” mode. Verify each point shows predicted value, ratio input (default 1 when adjusted = predicted), and live MWh preview. Change a ratio to 1.2; confirm the preview updates to predicted × 1.2.
8. Test “全部比例设为 1.5”: all ratios update to 1.5 and each point's preview differs because predicted values differ.
9. Switch back to direct mode, then back to ratio: verify drafts in both modes are preserved. Click “取消修改” to confirm drafts reset.
10. If any selected hour has null predicted_value, ratio mode must show “无预测值，无法按比例调整” for that point and block save with an explicit error.
11. Test ratio edge cases: predicted = 0 → result = 0 regardless of ratio; ratio > 100 or negative → rejected; computed result > 1000 MWh → rejected.
12. Save 2–3 selected values via ratio mode. Confirm the Edge Function returns success, reload shows database values equal to predicted × ratio (rounded to 3 decimals), and then restore the original raw adjusted values to avoid test pollution.
13. Probe the function with duplicate hours, hour outside 0..23, negative/NaN/over-1000 value, more than 24 updates, wrong HTTP method, and oversized body. All must fail without partial writes.
14. Confirm anonymous REST PATCH remains HTTP 401 and anon cannot execute `update_daily_curve_adjustments` directly.
15. Resize to 375×812: normal mode permits horizontal chart scrolling; selection mode captures the drag; editor mode selector, batch rows, and ratio inputs remain usable.
16. Confirm no console errors, no failed Supabase requests, and no stale tooltip after date changes.
