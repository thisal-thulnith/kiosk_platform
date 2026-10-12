import type { Network } from "./net";

export type Text = { en?: string; si?: string; ta?: string };
export type Staff = { id: string; name: string; role: string };

export type Me = {
  device: { id: string; type: string; name: string; station: string | null; table_ref: string | null };
  venue: { id: string; name: string; code: string; timezone: string; languages: string[]; release_rule: string; dine_in_mode: "tab" | "pay_first"; serve_mode: string; attract_images: string[]; board_page_seconds: number; brand?: { color: string; logo_url: string | null; theme: "light" | "dark" } };
  staff?: Staff | null;
  modules: string[] | null;
  payments: { cash: boolean; lankaqr: boolean; card: "reader" | "softpos" | null };
  network: Network;
  table: { ref: string; access: string; open: boolean } | null;
};

export type Modifier = { id: string; name: Text; price_delta: number; is_active?: boolean };
export type ModifierGroup = { id: string; name: Text; min_select: number; max_select: number; modifiers: Modifier[] };
export type ComboSlot = { name: Text; item_ids: string[]; upcharges?: Record<string, number> };
export type MenuItem = {
  id: string;
  category_id: string;
  name: Text;
  description: Text;
  price: number;
  station: string;
  image_url: string | null;
  allergens: string[];
  is_available: boolean;
  modifier_groups: ModifierGroup[];
  combo_slots: ComboSlot[];
  suggest_ids: string[];
  offer?: { price: number; discount_bp: number; ends_at: string };
};
export type Category = { id: string; name: Text; items: MenuItem[] };
export type Menu = { categories: Category[]; combo_parts: Record<string, { name: Text; is_available: boolean }> };

export type OrderItem = {
  id: string;
  position: number;
  menu_item_id: string;
  name: Text;
  unit_price: number;
  quantity: number;
  modifiers: { name: Text; price_delta: number }[];
  notes: string | null;
  allergens: string[];
  line_total: number;
  station: string;
  kds_status: "queued" | "in_progress" | "done" | "held" | "voided";
  parent_position: number | null;
};
export type Payment = { id: string; kind: "charge" | "refund"; method: string; amount: number; status: string; tendered: number | null; change_given: number | null; gateway_ref: string | null; qr_payload?: string | null; external_ref: string | null; staff_id: string | null; created_at: string };
export type PaymentHold = { staff_id: string | null; name: string | null; until: string };
export type PayWith = "cash" | "card" | "qr";
export type Order = {
  id: string;
  token: string;
  channel: string;
  table_ref: string | null;
  status: "placed" | "in_kitchen" | "ready" | "completed" | "cancelled" | "expired" | "voided";
  payment_status: "unpaid" | "pending" | "paid" | "refunded" | "part_refunded";
  priority: string;
  is_tab: boolean;
  payment_hold?: PaymentHold | null; // someone is taking this payment right now
  served_at: string | null;
  promised_at: string | null;
  subtotal: number;
  discount_total: number;
  discount_label: string | null;
  tax_lines: { code: string; name: Text; rate_bp: number; amount: number }[];
  tax_total: number;
  total: number;
  paid_total: number;
  created_at: string;
  items: OrderItem[];
  payments: Payment[];
};

export type TableState = "calling" | "bill" | "ready" | "waiting_payment" | "cooking" | "eating" | "cleaning" | "free" | "closed";
export type Feedback = { id: string; rating: number; tags: string[]; comment: string | null; table_ref: string | null; order_id: string | null; low: boolean; created_at: string; seen: boolean; seen_by: string | null };
export type TableInfo = {
  table_ref: string;
  state: TableState;
  open: boolean;
  requests: { id: string; kind: string; status: string; coming: string | null; pay_with?: PayWith | null }[];
  orders: { id: string; token: string; status: string; payment_status: string; total: number; paid_total: number; is_tab: boolean; served: boolean }[];
  open_total: number;
  to_serve: { id: string; token: string }[]; // food ready in the kitchen: take it to the table
  occupied_since: string | null; // guests are at the table since
  needs_cleaning: boolean; // guests left: clean it before the next guests
  feedback: Feedback | null; // what these guests said (last 3 hours)
};
export type ServiceRequest = { id: string; kind: "call_waiter" | "request_bill" | "help"; where: string; table_ref: string | null; device_id: string; status: "open" | "acknowledged" | "done"; created_at: string; coming: { staff_id: string; name: string | null } | null; pay_with?: PayWith | null };
export type Shift = { id: string; opening_float: number; opened_at: string; live: { expected_cash: number; by_method: Record<string, { count: number; charges: number; refunds: number }> } };
export type LedgerLine = { id: string; ref: string; at: string; kind: string; status: string; method: string; amount: number; tendered: number | null; change_given: number | null; token: string; table: string | null; channel: string; collected_by: string | null; device: string | null; outside_ref: string | null; invoice: string | null };
export type Ledger = { day: string; lines: LedgerLine[]; total: number; count: number; by_method: Record<string, number>; by_staff: Record<string, number> };
export type Bill = { table_ref: string; orders: { id: string; token: string; due: number; is_tab: boolean }[]; lines: { name: Text; quantity: number; line_total: number; part: boolean }[]; subtotal: number; discount_total: number; tax_total: number; total: number; paid_total: number; due: number; printed_at?: string[] };
/** What a payment call returns: the payment, the order after it, and where the receipt printed. */
export type PayResult = { payment: Payment; order: Order; printed_at?: string[] };
