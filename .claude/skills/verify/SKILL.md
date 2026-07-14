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
6. In the editor, test per-hour inputs and “全部设为”. Invalid/negative/out-of-range values must remain unsaved with an inline error.
7. Save 2–3 selected values. Confirm the Edge Function returns success, reload shows database values, and then restore the original raw adjusted values to avoid test pollution.
8. Probe the function with duplicate hours, hour outside 0..23, negative/NaN/over-1000 value, more than 24 updates, wrong HTTP method, and oversized body. All must fail without partial writes.
9. Confirm anonymous REST PATCH remains HTTP 401 and anon cannot execute `update_daily_curve_adjustments` directly.
10. Resize to 375×812: normal mode permits horizontal chart scrolling; selection mode captures the drag; editor and table remain usable.
11. Confirm no console errors, no failed Supabase requests, and no stale tooltip after date changes.
