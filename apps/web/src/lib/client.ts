import { ApiError } from "./api";
import type { Categories, Comparison, Conversation, Insight, InventoryCommand, InventoryEvent, InventoryItem, Lot, Merchants, Message, Preferences, Purchase, Query, Receipt, Summary, Turn, WalletPass } from "./types";

export function queryString(query: Query = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) if (value !== undefined && value !== "") params.set(key, String(value));
  return params.size ? "?" + params.toString() : "";
}
export class RaseedApi {
  constructor(private token: () => Promise<string>, private base = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "")) {}
  private async response(path: string, options: RequestInit = {}) {
    const token = await this.token();
    options.signal?.throwIfAborted();
    const response = await fetch(this.base + "/api/v1" + path, { ...options, credentials: "omit", cache: "no-store", headers: { Authorization: "Bearer " + token, ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers } });
    if (!response.ok) throw new ApiError(response.status);
    return response;
  }
  private async read<T>(path: string, signal?: AbortSignal): Promise<T> {
    const body = await (await this.response(path, { signal })).json();
    if (!body || !("data" in body)) throw new ApiError(502);
    return body.data as T;
  }
  private async write<T>(path: string, body: unknown, method = "POST"): Promise<T> {
    return (await (await this.response(path, { method, body: JSON.stringify(body) })).json()).data as T;
  }
  preferences = (signal?: AbortSignal) => this.read<Preferences>("/me/preferences", signal);
  savePreferences = (value: Preferences) => this.write<Preferences>("/me/preferences", value, "PATCH");
  purchases = (query: Query = {}, signal?: AbortSignal) => this.read<Purchase[]>("/purchases" + queryString(query), signal);
  purchase = (id: string, signal?: AbortSignal) => this.read<Purchase>("/purchases/" + encodeURIComponent(id), signal);
  receipts = (query: Query = {}, signal?: AbortSignal) => this.read<Receipt[]>("/receipts" + queryString(query), signal);
  receipt = (id: string, signal?: AbortSignal) => this.read<Receipt>("/receipts/" + encodeURIComponent(id), signal);
  receiptFile = async (id: string, signal?: AbortSignal) => (await this.response("/receipts/" + encodeURIComponent(id) + "/file", { signal })).blob();
  summary = (query: Query, signal?: AbortSignal) => this.read<Summary>("/analytics/spending-summary" + queryString(query), signal);
  comparison = (query: Query, signal?: AbortSignal) => this.read<Comparison>("/analytics/period-comparison" + queryString(query), signal);
  categories = (query: Query, signal?: AbortSignal) => this.read<Categories>("/analytics/spending-by-category" + queryString(query), signal);
  merchants = (query: Query, signal?: AbortSignal) => this.read<Merchants>("/analytics/spending-by-merchant" + queryString(query), signal);
  items = (query: Query = {}, signal?: AbortSignal) => this.read<InventoryItem[]>("/inventory/items" + queryString(query), signal);
  item = (id: string, signal?: AbortSignal) => this.read<InventoryItem>("/inventory/items/" + encodeURIComponent(id), signal);
  lots = (query: Query = {}, signal?: AbortSignal) => this.read<Lot[]>("/inventory/lots" + queryString(query), signal);
  itemLots = (id: string, query: Query = {}, signal?: AbortSignal) => this.read<Lot[]>("/inventory/items/" + encodeURIComponent(id) + "/lots" + queryString(query), signal);
  events = (id: string, query: Query = {}, signal?: AbortSignal) => this.read<InventoryEvent[]>("/inventory/lots/" + encodeURIComponent(id) + "/events" + queryString(query), signal);
  inventoryAction = (id: string, value: InventoryCommand) => this.write<InventoryEvent>("/inventory/lots/" + encodeURIComponent(id) + "/events", value);
  insights = (query: Query = {}, signal?: AbortSignal) => this.read<Insight[]>("/insights" + queryString(query), signal);
  insight = (id: string, signal?: AbortSignal) => this.read<Insight>("/insights/" + encodeURIComponent(id), signal);
  updateInsight = (id: string, status: "READ" | "DISMISSED", expected_version: number) => this.write<Insight>("/insights/" + encodeURIComponent(id), { status, expected_version }, "PATCH");
  passes = (query: Query = {}, signal?: AbortSignal) => this.read<WalletPass[]>("/wallet/passes" + queryString(query), signal);
  ensurePass = (purchase_id: string) => this.write<WalletPass>("/wallet/passes", { purchase_id });
  syncPass = (id: string) => this.write<WalletPass>("/wallet/passes/" + encodeURIComponent(id) + "/sync", {});
  savePass = (id: string) => this.write<{ save_url: string }>("/wallet/passes/" + encodeURIComponent(id) + "/add-to-wallet", {});
  conversations = (query: Query = {}, signal?: AbortSignal) => this.read<Conversation[]>("/assistant/conversations" + queryString(query), signal);
  createConversation = (title?: string) => this.write<Conversation>("/assistant/conversations", title ? { title } : {});
  messages = (id: string, query: Query = {}, signal?: AbortSignal) => this.read<Message[]>("/assistant/conversations/" + encodeURIComponent(id) + "/messages" + queryString(query), signal);
  sendMessage = (id: string, content: string, idempotency_key: string) => this.write<Turn>("/assistant/conversations/" + encodeURIComponent(id) + "/messages", { content, idempotency_key });
  async upload(file: File, progress: (value: number) => void, signal?: AbortSignal): Promise<Receipt> {
    const token = await this.token();
    signal?.throwIfAborted();
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const abort = () => xhr.abort();
      const cleanup = () => signal?.removeEventListener("abort", abort);
      xhr.open("POST", this.base + "/api/v1/receipts");
      xhr.setRequestHeader("Authorization", "Bearer " + token);
      xhr.timeout = 120000;
      xhr.upload.onprogress = event => { if (event.lengthComputable) progress(Math.round(event.loaded / event.total * 100)); };
      xhr.onerror = xhr.ontimeout = () => { cleanup(); reject(new ApiError(0)); };
      xhr.onabort = () => { cleanup(); reject(new DOMException("Upload cancelled", "AbortError")); };
      xhr.onload = () => {
        cleanup();
        if (xhr.status < 200 || xhr.status >= 300) { reject(new ApiError(xhr.status)); return; }
        try { const body = JSON.parse(xhr.responseText); if (!body.data?.id) throw new Error(); resolve(body.data); }
        catch { reject(new ApiError(502)); }
      };
      signal?.addEventListener("abort", abort, { once: true });
      const form = new FormData(); form.append("file", file); xhr.send(form);
    });
  }
}
export function validateReceipt(file: File): string | null {
  if (!/\.(jpe?g|png|pdf)$/i.test(file.name) || !["image/jpeg", "image/png", "application/pdf"].includes(file.type)) return "Choose a JPG, PNG or PDF receipt.";
  if (!file.size) return "This file is empty. Choose another receipt.";
  if (file.size > 10 * 1024 * 1024) return "Choose a receipt smaller than 10 MB.";
  return null;
}
export function walletUrl(value: string): string {
  const url = new URL(value);
  if (url.origin !== "https://pay.google.com" || !url.pathname.startsWith("/gp/v/save/") || url.username || url.password) throw new ApiError(502);
  return url.href;
}
