---
name: verify
summary: Verify the static Supabase chart in a real browser.
---

# Verify

1. Serve the workspace root so the nested repository is reachable: `python -m http.server 4173`.
2. Open `/Ning-Ning-Ning.github.io/` in the browser preview.
3. Confirm the default latest date loads without failed network requests or console errors.
4. Select `2025-01-01`; expect 24 `.point` elements, 24 table rows, total `0.978 MWh`, and peak `0.060 MWh · 第 19 时段`.
5. Focus or hover a chart point and confirm the tooltip shows period, time range, and MWh value.
6. Resize to 375×812 and confirm controls and summary fit; the chart itself intentionally scrolls horizontally for readable labels.
7. Verify a REST SELECT with the publishable key returns 24 rows and an INSERT returns HTTP 401.
