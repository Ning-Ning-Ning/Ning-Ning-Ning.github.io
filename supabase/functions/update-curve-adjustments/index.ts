import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2.95.0";

const ALLOWED_ORIGINS = new Set([
  "https://ning-ning-ning.github.io",
  "http://localhost:4173",
  "http://127.0.0.1:4173",
]);
const MAX_BODY_BYTES = 16_384;

type Update = { hour: number; adjusted_value: number };

function corsHeaders(origin: string | null): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": origin && ALLOWED_ORIGINS.has(origin)
      ? origin
      : "https://ning-ning-ning.github.io",
    "Access-Control-Allow-Headers": "apikey, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    Vary: "Origin",
  };
}

function jsonResponse(origin: string | null, body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(origin), "Content-Type": "application/json" },
  });
}

function validatePayload(payload: unknown): { date: string; updates: Update[] } {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("请求体必须是对象");
  const { date, updates } = payload as { date?: unknown; updates?: unknown };
  if (typeof date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error("date 必须是 YYYY-MM-DD");
  const parsedDate = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(parsedDate.getTime()) || parsedDate.toISOString().slice(0, 10) !== date) throw new Error("date 不是有效日期");
  if (!Array.isArray(updates) || updates.length < 1 || updates.length > 24) throw new Error("updates 必须包含 1 至 24 项");

  const seen = new Set<number>();
  return updates.map((item, index) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) throw new Error(`第 ${index + 1} 项格式错误`);
    const { hour, adjusted_value } = item as { hour?: unknown; adjusted_value?: unknown };
    if (!Number.isInteger(hour) || (hour as number) < 0 || (hour as number) > 23) throw new Error(`第 ${index + 1} 项 hour 必须是 0..23 的整数`);
    if (seen.has(hour as number)) throw new Error("hour 不能重复");
    seen.add(hour as number);
    if (typeof adjusted_value !== "number" || !Number.isFinite(adjusted_value) || adjusted_value < 0 || adjusted_value > 1000) {
      throw new Error(`第 ${index + 1} 项 adjusted_value 必须是 0..1000 的有限数值`);
    }
    return { hour: hour as number, adjusted_value };
  });
}

Deno.serve(async (request: Request) => {
  const origin = request.headers.get("Origin");
  if (origin !== null && !ALLOWED_ORIGINS.has(origin)) return jsonResponse(origin, { error: "不允许的来源" }, 403);
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders(origin) });
  if (request.method !== "POST") return jsonResponse(origin, { error: "仅支持 POST" }, 405);
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) return jsonResponse(origin, { error: "Content-Type 必须是 application/json" }, 415);
  if (Number(request.headers.get("content-length") || 0) > MAX_BODY_BYTES) return jsonResponse(origin, { error: "请求体过大" }, 413);

  try {
    const rawBody = await request.text();
    if (new TextEncoder().encode(rawBody).byteLength > MAX_BODY_BYTES) return jsonResponse(origin, { error: "请求体过大" }, 413);
    const payload = validatePayload(JSON.parse(rawBody));
    const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
      auth: { persistSession: false, autoRefreshToken: false },
    });
    const { data, error } = await supabase.rpc("update_daily_curve_adjustments", {
      target_date: payload.date,
      updates: payload.updates,
    });
    if (error) throw error;
    return jsonResponse(origin, { updated: data });
  } catch (error) {
    console.error(error);
    return jsonResponse(origin, { error: error instanceof Error ? error.message : "请求处理失败" }, 400);
  }
});
