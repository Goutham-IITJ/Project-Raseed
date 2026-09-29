export type Decimal = string;
export type Query = Record<string, string | number | undefined>;
export interface Preferences { currency: string; timezone: string; locale: string }
export interface Receipt { id: string; original_filename: string; mime_type: string; file_size: number; status: string; purchase_id: string | null; attempt_count: number; failure_message: string | null; failure_code: string | null; uploaded_at: string | null; created_at: string }
export interface LineItem { id: string; raw_name: string; product_id: string | null; category_id: string | null; quantity: Decimal | null; unit: string | null; unit_price: Decimal | null; line_total: Decimal | null }
export interface Purchase { id: string; receipt_id: string | null; merchant_id: string | null; category_id: string | null; merchant_name_raw: string; purchased_at: string; currency: string; grand_total: Decimal; subtotal: Decimal | null; tax_total: Decimal | null; discount_total: Decimal | null; shipping_total: Decimal | null; payment_status: string; notes: string | null; line_items: LineItem[]; payments: { id: string; method: string; amount: Decimal; currency: string; last4: string | null }[] }
export interface Period { start_date: string; end_date: string; timezone: string }
export interface Summary { period: Period; currencies: { currency: string; total_spent: Decimal; purchase_count: number; average_purchase: Decimal | null; recorded_payment_total: Decimal }[] }
export interface Comparison { period: Period; comparison_period: Period; currencies: { currency: string; current_total: Decimal; comparison_total: Decimal; percentage_change: Decimal | null; absolute_change: Decimal }[] }
export interface CategoryGroup { category_id: string | null; category_name: string | null; currency: string; total_amount: Decimal | null; share_of_known_total_percent: Decimal | null; purchase_count: number }
export interface Categories { groups: CategoryGroup[]; has_more: boolean }
export interface Merchants { groups: { merchant_id: string | null; merchant_name: string | null; currency: string }[]; has_more: boolean }
export interface InventoryItem { id: string; name: string; unit: string; quantity_remaining: Decimal; lot_count: number }
export interface Lot { id: string; item_id: string; purchase_id: string; line_item_id: string; name: string; unit: string; quantity_acquired: Decimal; quantity_remaining: Decimal; acquired_at: string; version: number; expiry: { date: string | null; source: string; provenance: string; confidence: Decimal | null; status: string } }
export interface InventoryEvent { id: string; sequence: number; event_type: string; quantity_delta: Decimal; reason: string; source: string; created_at: string }
export interface InventoryCommand { idempotency_key: string; expected_version: number; event_type: "CONSUMED" | "DISCARDED" | "CORRECTION"; reason: string; quantity?: string; quantity_remaining?: string }
export interface Insight { id: string; type: string; title: string; summary: string; status: string; version: number; provenance: string; confidence: string | null; source_data: Record<string, unknown>; calculation: Record<string, unknown>; evaluated_at: string; expires_at: string }
export interface WalletPass { id: string; purchase_id: string; status: string; attempt_count: number; next_attempt_at: string; last_error_code: string | null; synced_at: string | null }
export interface Conversation { id: string; title: string | null; updated_at: string }
export interface Citation { name: string; tool_name: string; pointer: string; value: string | number | boolean | null }
export interface ToolExecution { id: string; tool_name: string; status: string; result: { data: unknown; error: { message: string } | null } | null }
export interface Message { id: string; sequence: number; role: "USER" | "ASSISTANT"; status: string; content: string | null; idempotency_key: string | null; reply_to_id: string | null; failure_message: string | null; evidence: { citations: Citation[] } | null; tool_executions: ToolExecution[]; created_at: string }
export interface Turn { user_message: Message; assistant_message: Message; replayed: boolean }
