from datetime import datetime
from typing import Any

from kiosk.infra.models import (
    Invoice,
    MenuCategory,
    MenuItem,
    Order,
    OrderItem,
    Payment,
    Staff,
    TaxRule,
    utcnow,
)


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def item_dict(i: OrderItem) -> dict[str, Any]:
    return {
        "id": i.id,
        "position": i.position,
        "menu_item_id": i.menu_item_id,
        "name": i.name,
        "unit_price": i.unit_price,
        "quantity": i.quantity,
        "modifiers": i.modifiers,
        "notes": i.notes,
        "allergens": i.allergens,
        "line_total": i.line_total,
        "station": i.station,
        "tax_category": i.tax_category,
        "kds_status": i.kds_status,
        "parent_position": i.parent_position,
        "remake_count": i.remake_count,
        "source": i.source,
        "started_at": _dt(i.started_at),
        "done_at": _dt(i.done_at),
    }


def payment_dict(p: Payment) -> dict[str, Any]:
    return {
        "id": p.id,
        "kind": p.kind,
        "method": p.method,
        "amount": p.amount,
        "status": p.status,
        "tendered": p.tendered,
        "change_given": p.change_given,
        "gateway_ref": p.gateway_ref,
        "qr_payload": p.qr_payload if p.status == "pending" else None,
        "external_ref": p.external_ref,
        "shift_id": p.shift_id,
        "staff_id": p.staff_id,
        "device_id": p.device_id,
        "reason": p.reason,
        "created_at": _dt(p.created_at),
        "completed_at": _dt(p.completed_at),
    }


def order_dict(o: Order) -> dict[str, Any]:
    return {
        "id": o.id,
        "venue_id": o.venue_id,
        "token": o.token,
        "business_date": o.business_date,
        "channel": o.channel,
        "table_ref": o.table_ref,
        "status": o.status,
        "payment_status": o.payment_status,
        "release_rule": o.release_rule,
        "priority": o.priority,
        "is_tab": o.is_tab,
        # Someone is taking this payment right now (others see who, and can't start a second one).
        "payment_hold": {
            "staff_id": o.pay_hold_by,
            "name": o.pay_hold_name,
            "until": o.pay_hold_until.isoformat(),
        }
        if o.pay_hold_until and o.pay_hold_until > utcnow()
        else None,
        "served_at": _dt(o.served_at),
        "promised_at": _dt(o.promised_at),
        "subtotal": o.subtotal,
        "discount_bp": o.discount_bp,
        "discount_total": o.discount_total,
        "discount_label": o.discount_label,
        "customer_id": o.customer_id,
        "notify": bool(o.notify_phone),  # the number itself never goes to screens
        "points_earned": o.points_earned,
        "tax_lines": o.tax_lines,
        "tax_total": o.tax_total,
        "total": o.total,
        "paid_total": o.paid_total,
        "notes": o.notes,
        "device_id": o.device_id,
        "placed_by_staff_id": o.placed_by_staff_id,
        "expires_at": _dt(o.expires_at),
        "released_at": _dt(o.released_at),
        "ready_at": _dt(o.ready_at),
        "completed_at": _dt(o.completed_at),
        "created_at": _dt(o.created_at),
        "updated_at": _dt(o.updated_at),
        "version": o.version,
        "items": [item_dict(i) for i in o.items],
        "payments": [payment_dict(p) for p in o.payments],
    }


def invoice_dict(inv: Invoice) -> dict[str, Any]:
    return {
        "id": inv.id,
        "order_id": inv.order_id,
        "number": inv.number,
        "total": inv.total,
        "issued_at": _dt(inv.issued_at),
        "snapshot": inv.snapshot,
    }


def menu_item_dict(m: MenuItem) -> dict[str, Any]:
    return {
        "id": m.id,
        "category_id": m.category_id,
        "name": m.name,
        "description": m.description,
        "price": m.price,
        "external_code": m.external_code,
        "station": m.station,
        "prep_minutes": m.prep_minutes,
        "tax_category": m.tax_category,
        "allergens": m.allergens,
        "image_url": m.image_url,
        "windows": m.windows,
        "sort": m.sort,
        "is_active": m.is_active,
        "is_available": m.is_available,
        "combo_slots": m.combo_slots or [],
        "suggest_ids": m.suggest_ids or [],
        "modifier_groups": [
            {
                "id": g.id,
                "name": g.name,
                "min_select": g.min_select,
                "max_select": g.max_select,
                "sort": g.sort,
                "modifiers": [
                    {
                        "id": mod.id,
                        "name": mod.name,
                        "price_delta": mod.price_delta,
                        "sort": mod.sort,
                        "is_active": mod.is_active,
                    }
                    for mod in g.modifiers
                ],
            }
            for g in m.modifier_groups
        ],
    }


def category_dict(c: MenuCategory) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "sort": c.sort,
        "windows": c.windows,
        "is_active": c.is_active,
    }


def tax_rule_dict(r: TaxRule) -> dict[str, Any]:
    return {
        "id": r.id,
        "code": r.code,
        "name": r.name,
        "rate_bp": r.rate_bp,
        "applies_to": r.applies_to,
        "compound": r.compound,
        "sequence": r.sequence,
        "effective_from": _dt(r.effective_from),
        "effective_to": _dt(r.effective_to),
        "is_active": r.is_active,
    }


def staff_dict(s: Staff) -> dict[str, Any]:
    return {"id": s.id, "name": s.name, "role": s.role, "is_active": s.is_active}
