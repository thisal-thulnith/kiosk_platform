"""Module catalogue, packages and tiers, from the Product Details and Full Plan.

A venue's plan is a set of modules plus the number of screens of each type it paid for.
Packs are presets; Custom picks modules one by one; Hotel is custom only.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Module:
    code: str
    name: str
    kind: str  # "required" | "optional" | "recommended"
    device_type: str | None = None  # the screen this module sells, if any
    hotel: bool = False


MODULES: dict[str, Module] = {
    m.code: m
    for m in [
        Module("R-CORE", "Core platform: order engine, dashboard, tax engine, reports", "required"),
        Module("R-KDS", "Kitchen display", "required", "kds"),
        Module("R-STATUS", "Order status board", "optional", "status"),
        Module("R-SELF", "Self-order kiosk", "optional", "kiosk"),
        Module("R-CASH", "Cashier screen", "optional", "cashier"),
        Module("R-TABLE", "Table screen", "optional", "table"),
        Module("R-WAITER", "Waiter assist and handheld", "optional", "waiter"),
        Module("R-BOARD", "Overhead menu board", "optional", "board"),
        Module("R-PAY", "Payments: LankaQR, card, cash slip", "recommended"),
        Module("R-SPLIT", "Split bill", "optional"),
        Module("R-VOICE", "Voice ordering (Sinhala, Tamil, English)", "optional"),
        Module("R-AI", "AI Autonomous Mode", "optional"),
        Module("R-LOYAL", "Loyalty and customer profiles", "optional"),
        Module("R-INV", "Inventory and auto stock-out", "optional"),
        Module("R-BRIDGE", "Bridge to existing POS", "optional"),
        Module("R-POS", "Full native POS and back office", "optional"),
        Module("R-MULTI", "Multi-branch central control", "optional"),
        Module("R-ANALYTICS", "Advanced analytics and forecasts", "optional"),
        Module("H-CORE", "Room kiosk, guest profile, staff app", "required", "room", hotel=True),
        Module("H-DINE", "In-room dining", "optional", hotel=True),
        Module("H-HK", "Housekeeping and amenities", "optional", hotel=True),
        Module("H-MAINT", "Maintenance requests", "optional", hotel=True),
        Module("H-SPA", "Spa and wellness", "optional", hotel=True),
        Module("H-CONC", "Concierge", "optional", hotel=True),
        Module("H-LOYAL", "Hotel loyalty and preferences", "optional", hotel=True),
        Module("H-FOLIO", "Bill posting to the room folio", "optional", hotel=True),
        Module("H-INFO", "Hotel and local guide", "optional", hotel=True),
        Module("H-FEED", "Feedback", "optional", hotel=True),
        Module("H-KDS", "Hotel kitchen display", "optional", "kds", hotel=True),
        Module("H-PMS", "Native PMS", "optional", hotel=True),
        Module("H-BRIDGE", "Bridge to existing PMS", "optional", hotel=True),
        Module("H-OPS", "Operations dashboard", "optional", hotel=True),
        Module("H-AI", "AI request routing", "optional", hotel=True),
    ]
}

DEVICE_MODULE = {
    "kds": "R-KDS",
    "status": "R-STATUS",
    "kiosk": "R-SELF",
    "cashier": "R-CASH",
    "table": "R-TABLE",
}
DEVICE_MODULE |= {"waiter": "R-WAITER", "board": "R-BOARD", "room": "H-CORE"}

BASE = ["R-CORE", "R-KDS", "R-PAY"]
# Offered on every tier: the order status board is optional (some restaurants serve at the table).
# Waiter handhelds and menu boards are kept as add-ons for older packages but are not offered.
OPTIONAL = ["R-STATUS", "R-WAITER", "R-BOARD"]


@dataclass(frozen=True)
class Tier:
    screens: dict[str, int]
    modules: list[str]
    addons: list[str] = field(default_factory=list)  # can be added for a fee


PACKS: dict[str, dict[str, Any]] = {
    "pack1": {
        "name": "Pack 1 · Self-Serve",
        "tiers": {
            "starter": Tier(
                {"kiosk": 1, "kds": 1}, BASE + ["R-SELF"], OPTIONAL + ["R-VOICE", "R-AI", "R-LOYAL"]
            ),
            "standard": Tier(
                {"kiosk": 2, "kds": 2}, BASE + ["R-SELF", "R-VOICE"], OPTIONAL + ["R-AI", "R-LOYAL"]
            ),
            "premium": Tier(
                {"kiosk": 3, "kds": 2},
                BASE + ["R-SELF", "R-VOICE", "R-AI", "R-LOYAL", "R-ANALYTICS"],
                OPTIONAL,
            ),
        },
    },
    "pack2": {
        "name": "Pack 2 · Counter + Table",
        "tiers": {
            "starter": Tier(
                {"cashier": 1, "kds": 1, "table": 6},
                BASE + ["R-CASH", "R-TABLE"],
                OPTIONAL + ["R-SPLIT", "R-VOICE", "R-AI", "R-LOYAL"],
            ),
            "standard": Tier(
                {"cashier": 1, "kds": 2, "table": 12},
                BASE + ["R-CASH", "R-TABLE", "R-SPLIT"],
                OPTIONAL + ["R-VOICE", "R-AI", "R-LOYAL"],
            ),
            "premium": Tier(
                {"cashier": 2, "kds": 2, "table": 20},
                BASE + ["R-CASH", "R-TABLE", "R-SPLIT", "R-VOICE", "R-AI", "R-LOYAL", "R-ANALYTICS"],
                OPTIONAL,
            ),
        },
    },
}


def _hybrid(tier: str) -> Tier:
    """Pack 3 = Pack 1 + Pack 2 on one system: one kitchen, one menu, one report."""
    a, b = PACKS["pack1"]["tiers"][tier], PACKS["pack2"]["tiers"][tier]
    screens = dict(b.screens)
    screens["kiosk"] = a.screens["kiosk"]
    for kind in ("kds", "board", "status"):
        screens[kind] = max(a.screens.get(kind, 0), b.screens.get(kind, 0))
    modules = sorted(set(a.modules) | set(b.modules))
    addons = sorted((set(a.addons) | set(b.addons)) - set(modules))
    return Tier({k: v for k, v in screens.items() if v}, modules, addons)


PACKS["pack3"] = {
    "name": "Pack 3 · Hybrid Pro",
    "tiers": {t: _hybrid(t) for t in ("starter", "standard", "premium")},
}
PACKS["custom"] = {"name": "Pack 4 · Custom", "tiers": {}}
PACKS["hotel"] = {"name": "Hotel · Custom", "tiers": {}}


# Physical equipment installed with the screens (sold or leased with the package).
HARDWARE: dict[str, str] = {
    "router": "Internet router and Wi-Fi for the screens",
    "receipt_printer": "Counter receipt printer",
    "cash_drawer": "Cash drawer",
    "kiosk_printer": "Kiosk receipt printer (order number)",
    "kitchen_printer": "Kitchen ticket printer (backup)",
    "card_reader": "Card reader",
    "scanner": "Barcode / QR scanner",
    "hub": "Restaurant hub (works without internet)",
    "ups": "UPS power backup",
}


@dataclass(frozen=True)
class Need:
    """Choosing `because` makes `item` required: at least `per` of it for each one chosen."""

    because: str
    item: str
    per: int  # 0 = at least one in total, whatever the count
    reason: str
    module: str | None = None  # the module that comes with the required screen
    unless: str | None = None  # not needed when the plan has this module


# If a restaurant uses X, it must also have Y. The package builder adds Y by itself (locked).
NEEDS: list[Need] = [
    Need("kiosk", "kiosk_printer", 1, "Each kiosk prints the guest's order number"),
    Need("kiosk", "kds", 0, "Kiosk orders go to the kitchen display", "R-KDS"),
    Need(
        "table",
        "cashier",
        0,
        "Table guests can pay at the cashier (cash, card, bill)",
        "R-CASH",
        unless="R-BRIDGE",  # the restaurant's own POS is the cashier
    ),
    Need("table", "kds", 0, "Table orders go to the kitchen display", "R-KDS"),
    Need("waiter", "table", 0, "Waiter handhelds serve table screens", "R-TABLE"),
    Need("cashier", "receipt_printer", 1, "Each cashier prints receipts"),
    Need("cashier", "cash_drawer", 1, "Each cashier takes cash"),
    Need("cashier", "scanner", 0, "The cashier scans the barcode on pay-at-cashier slips"),
    Need("hub", "ups", 0, "The hub must keep running in a power cut"),
    Need("*", "router", 0, "Every screen needs the restaurant's network"),
]
SCREEN_KINDS = ("table", "kiosk", "cashier", "kds", "status", "waiter", "board", "room")


@dataclass(frozen=True)
class Flow:
    """A way the restaurant works. Choosing it brings the screens, modules, equipment and settings it
    needs; flows it depends on are chosen with it."""

    code: str
    name: str
    about: str
    screens: dict[str, int] = field(default_factory=dict)
    modules: tuple[str, ...] = ()
    hardware: dict[str, int] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    needs: tuple[str, ...] = ()  # other flows
    group: str = "core"  # core: shown first · more: under "More options" · hidden: not offered


FLOWS: dict[str, Flow] = {
    f.code: f
    for f in [
        Flow(
            "kiosk_self_order",
            "Self-order kiosks",
            "Guests order and pay alone at a kiosk; the number is on their receipt and the kiosk screen",
            {"kiosk": 1, "kds": 1},
            ("R-SELF", "R-KDS", "R-PAY"),
            settings={"release_rule": "A", "serve_mode": "self_pickup"},
        ),
        Flow(
            "table_order",
            "Order at the table",
            "A screen on each table: guests order, call the waiter, ask for the bill",
            {"table": 1, "kds": 1},
            ("R-TABLE", "R-KDS", "R-PAY"),
            settings={"dine_in_mode": "pay_first"},
        ),
        Flow(
            "table_tab",
            "Pay after eating",
            "One check per table: rounds go to the kitchen at once, the waiter brings the bill at the end",
            modules=("R-TABLE",),
            settings={"dine_in_mode": "tab"},
            needs=("table_order",),
            group="core",
        ),
        Flow(
            "table_lock",
            "Staff open each table",
            "An empty table's screen is locked; staff open it on the POS when guests sit down",
            settings={"table_access": "staff_opens"},
            needs=("table_order",),
            group="more",
        ),
        Flow(
            "counter_pos",
            "POS (our cashier)",
            "Staff take orders and payments, run the tables and get every call on our POS screen",
            {"cashier": 1, "kds": 1},
            ("R-CASH", "R-KDS", "R-PAY"),
        ),
        Flow(
            "waiter_service",
            "Waiter app",
            "Waiters take orders, bring the bill and collect payment at the table on a phone or tablet",
            {"waiter": 1},
            ("R-WAITER",),
            settings={"serve_mode": "waiter"},
            needs=("table_order",),
        ),
        Flow(
            "existing_pos",
            "Keep the restaurant's current POS",
            "Orders go to their POS; their POS takes payment and tells us; menu imported by PLU code",
            modules=("R-BRIDGE",),
            group="more",
        ),
        Flow(
            "status_display",
            "Order status display (optional)",
            "A wall screen shows Preparing and Ready numbers. Leave it out if guests are served at the table",
            {"status": 1},
            ("R-STATUS",),
        ),
        Flow(
            "menu_board",
            "Menu board",
            "A big screen above the counter",
            {"board": 1},
            ("R-BOARD",),
            group="hidden",
        ),
        Flow(
            "kitchen_printing",
            "Kitchen ticket printer",
            "Tickets also print in the kitchen (backup for the display)",
            hardware={"kitchen_printer": 1},
            settings={"print_kitchen_backup": True},
            group="more",
        ),
        Flow(
            "offline_hybrid",
            "Works without internet (Hybrid)",
            "A hub in the restaurant keeps screens and kitchen working when the internet is down",
            hardware={"hub": 1},
            settings={"network_mode": "hybrid"},
            group="more",
        ),
        Flow(
            "guest_sms",
            "Texts to guests",
            '"Your order is ready" and receipt link by SMS',
            settings={"sms_ready": True, "sms_receipt": True},
            group="more",
        ),
    ]
}


def expand_flows(codes: list[str]) -> list[str]:
    """The chosen flows plus the flows they depend on, in catalogue order."""
    unknown = set(codes) - set(FLOWS)
    if unknown:
        raise PlanError("unknown_flow", f"Unknown flows: {', '.join(sorted(unknown))}")
    chosen = set(codes)
    for _ in range(3):
        for c in list(chosen):
            chosen |= set(FLOWS[c].needs)
    return [c for c in FLOWS if c in chosen]


def requirements(counts: dict[str, int], modules: set[str] | None = None) -> dict[str, tuple[int, list[str]]]:
    """Minimum of each item for these counts (screens and hardware): {item: (minimum, [reasons])}."""
    out: dict[str, tuple[int, list[str]]] = {}
    any_screen = sum(counts.get(k, 0) for k in SCREEN_KINDS)
    for need in NEEDS:
        if need.unless and modules and need.unless in modules:
            continue
        n = any_screen if need.because == "*" else counts.get(need.because, 0)
        if not n:
            continue
        minimum = n * need.per if need.per else 1
        have, reasons = out.get(need.item, (0, []))
        out[need.item] = (max(have, minimum), [*reasons, need.reason])
    return out


def apply_requirements(
    chosen: set[str], counts: dict[str, int], hardware: dict[str, int]
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Raise screens and hardware to what the chosen ones need. Returns (hardware, requirements)."""
    hw = {k: max(0, int(v)) for k, v in hardware.items() if k in HARDWARE}
    for _ in range(4):  # a screen added for one rule can bring its own needs (table -> cashier -> printer)
        for item, (minimum, _reasons) in requirements({**counts, **hw}, chosen).items():
            if item in HARDWARE:
                hw[item] = max(hw.get(item, 0), minimum)
            elif counts.get(item, 0) < minimum:
                counts[item] = minimum
                module = next((n.module for n in NEEDS if n.item == item and n.module), None)
                if module:
                    chosen.add(module)
    reqs = [
        {"item": item, "min": minimum, "reasons": reasons}
        for item, (minimum, reasons) in sorted(requirements({**counts, **hw}, chosen).items())
    ]
    return {k: v for k, v in sorted(hw.items()) if v}, reqs


# What a screen's hardware has built in. Choosing a model in the Setup console sets up its built-in
# printer, card reader and scanner in one go (the installer only types the reader's serial).
HARDWARE_MODELS: dict[str, dict[str, dict[str, Any]]] = {
    "kiosk": {
        "all_in_one": {
            "name": "All-in-one kiosk (built-in printer, card reader, QR scanner)",
            "printer": True,
            "card_reader": True,
            "scanner": True,
        },
        "tablet_printer": {"name": "Tablet on a stand + USB receipt printer", "printer": True},
        "tablet": {"name": "Tablet on a stand (no printer, LankaQR / pay at cashier)"},
    },
    "cashier": {
        "pos_terminal": {
            "name": "POS terminal (built-in printer, cash drawer port, scanner, customer display)",
            "printer": True,
            "cash_drawer": True,
            "scanner": True,
            "customer_display": True,
        },
        "tablet_pos": {"name": "Tablet + USB printer and cash drawer", "printer": True, "cash_drawer": True},
    },
    "kds": {
        "kitchen_screen": {"name": "Kitchen screen (splash-proof, wall mount)"},
        "kitchen_screen_printer": {"name": "Kitchen screen + ticket printer", "kitchen_printer": True},
    },
}


class PlanError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def build_plan(
    pack: str,
    tier: str | None = None,
    add: list[str] | None = None,
    screens: dict[str, int] | None = None,
    modules: list[str] | None = None,
    hardware: dict[str, int] | None = None,
    flows: list[str] | None = None,
) -> dict[str, Any]:
    """Turn a pack + tier (+ add-ons, extra screens) or a custom module list into a stored plan.

    Returns {"pack", "tier", "modules", "screens", "hardware", "requirements", "warnings"}.
    Anything the chosen equipment depends on is added (see NEEDS). Raises PlanError on broken rules.
    """
    if pack not in PACKS:
        raise PlanError("unknown_pack", f"Unknown package {pack}")
    warnings: list[str] = []
    if pack in ("custom", "hotel"):
        chosen = set(modules or [])
        counts = dict(screens or {})
        tier = None
    else:
        tiers = PACKS[pack]["tiers"]
        if tier not in tiers:
            raise PlanError("unknown_tier", f"{PACKS[pack]['name']} has tiers: {', '.join(tiers)}")
        base: Tier = tiers[tier]
        extra = set(add or [])
        unknown_extra = extra - set(MODULES)
        if unknown_extra:
            raise PlanError("unknown_module", f"Unknown modules: {', '.join(sorted(unknown_extra))}")
        not_addon = extra - set(base.addons) - set(base.modules)
        if not_addon:
            raise PlanError(
                "not_an_addon",
                f"{', '.join(sorted(not_addon))} can't be added to this tier. "
                "Use Pack 4 Custom for other layouts",
            )
        chosen = set(base.modules) | extra
        counts = dict(base.screens)
        for kind, n in (screens or {}).items():  # extra screens are added one by one on top of the tier
            counts[kind] = counts.get(kind, 0) + n

    # Service flows: each brings its screens, modules, equipment and settings (and the flows it needs).
    flow_codes = expand_flows(flows or [])
    hardware = dict(hardware or {})
    flow_settings: dict[str, Any] = {}
    for code in flow_codes:
        f = FLOWS[code]
        if pack not in ("custom", "hotel"):
            base_tier: Tier = PACKS[pack]["tiers"][tier]
            outside = set(f.modules) - set(base_tier.modules) - set(base_tier.addons)
            if outside:
                raise PlanError(
                    "not_an_addon",
                    f"{f.name} needs {', '.join(sorted(outside))}, which this tier can't add. "
                    "Use Pack 4 Custom",
                )
        chosen |= set(f.modules)
        for kind, n in f.screens.items():
            counts[kind] = max(counts.get(kind, 0), n)
        for item, n in f.hardware.items():
            hardware[item] = max(int(hardware.get(item, 0)), n)
        flow_settings.update(f.settings)

    unknown = chosen - set(MODULES)
    if unknown:
        raise PlanError("unknown_module", f"Unknown modules: {', '.join(sorted(unknown))}")
    if pack == "hotel":
        if "H-CORE" not in chosen:
            raise PlanError("module_required", "The hotel package always includes H-CORE (room kiosk)")
        chosen.add("R-CORE")
    else:
        missing = {"R-CORE", "R-KDS"} - chosen
        if missing:
            raise PlanError(
                "module_required",
                "R-CORE and R-KDS are always required (every package has a kitchen display)",
            )
    if {"R-BRIDGE", "R-POS"} <= chosen:
        raise PlanError("bridge_or_pos", "Choose R-BRIDGE (connect your POS) or R-POS (use ours), not both")
    if {"H-BRIDGE", "H-PMS"} <= chosen:
        raise PlanError("bridge_or_pms", "Choose H-BRIDGE (connect your PMS) or H-PMS (use ours), not both")
    from kiosk.config import settings  # status boards may be "coming soon": then don't push them

    if (
        chosen & {"R-SELF", "R-CASH"}
        and "R-STATUS" not in chosen
        and "status" not in settings.coming_soon_types
    ):
        warnings.append("R-STATUS (order status board) is strongly recommended with kiosks or a cashier")
    if "R-AI" in chosen:
        warnings.append("R-AI needs about 2 months of sales data; it starts in 'suggest only' mode")

    # Every screen type needs its module; a module that sells a screen needs at least one.
    for kind, n in list(counts.items()):
        if n < 0:
            raise PlanError("bad_screens", "Screen counts cannot be negative")
        if n and DEVICE_MODULE.get(kind) not in chosen and not (kind == "kds" and "H-KDS" in chosen):
            raise PlanError("module_missing", f"{n} {kind} screen(s) need module {DEVICE_MODULE.get(kind)}")
    for code in chosen:
        dev = MODULES[code].device_type
        if dev and counts.get(dev, 0) == 0:
            counts[dev] = 1
    unknown_hw = set(hardware) - set(HARDWARE)
    if unknown_hw:
        raise PlanError("unknown_hardware", f"Unknown equipment: {', '.join(sorted(unknown_hw))}")
    before = set(chosen)
    hw, reqs = apply_requirements(chosen, counts, hardware)
    for code in sorted(chosen - before):
        warnings.append(f"{code} added: {MODULES[code].name} is required by the chosen screens")
    return {
        "pack": pack,
        "tier": tier,
        "modules": sorted(chosen),
        "screens": {k: v for k, v in sorted(counts.items()) if v},
        "hardware": hw,
        "requirements": reqs,
        "flows": flow_codes,
        "settings": flow_settings,  # applied to the venue when the plan is set
        "warnings": warnings,
    }


def has_module(plan: dict[str, Any] | None, code: str) -> bool:
    """No plan (demo / dev venues) means everything is allowed."""
    return plan is None or not plan or code in plan.get("modules", [])


def screen_limit(plan: dict[str, Any] | None, device_type: str) -> int | None:
    """How many screens of this type the venue paid for. None means no limit."""
    if not plan:
        return None
    return int(plan.get("screens", {}).get(device_type, 0))


def catalog() -> dict[str, Any]:
    packs = {}
    for code, p in PACKS.items():
        packs[code] = {
            "name": p["name"],
            "tiers": {
                t: {"screens": tier.screens, "modules": tier.modules, "addons": tier.addons}
                for t, tier in p["tiers"].items()
            },
        }
    return {
        "modules": [m.__dict__ for m in MODULES.values()],
        "packs": packs,
        "hardware": HARDWARE,
        "needs": [n.__dict__ for n in NEEDS],
        "flows": [
            {**{k: v for k, v in f.__dict__.items() if k != "settings"}, "settings": f.settings}
            for f in FLOWS.values()
        ],
        "hardware_models": HARDWARE_MODELS,
    }


def quote(plan: dict[str, Any], prices: dict[str, dict[str, int]]) -> dict[str, Any]:
    """Monthly software + one-time hardware from a price book.

    prices: {"module:R-TABLE": {"monthly": 0, "once": 0}, "screen:table": {"monthly": x, "once": y}, ...}
    All amounts are LKR cents. Missing prices count as 0 and are listed so sales can fill them in.
    """
    lines, missing = [], []
    for code in plan["modules"]:
        p = prices.get(f"module:{code}")
        if p is None:
            missing.append(f"module:{code}")
        p = p or {}
        lines.append({"item": f"module:{code}", "name": MODULES[code].name, "qty": 1, **_amounts(p, 1)})
    for kind, n in plan["screens"].items():
        p = prices.get(f"screen:{kind}")
        if p is None:
            missing.append(f"screen:{kind}")
        lines.append({"item": f"screen:{kind}", "name": f"{kind} screen", "qty": n, **_amounts(p or {}, n)})
    for item, n in plan.get("hardware", {}).items():
        p = prices.get(f"hardware:{item}")
        if p is None:
            missing.append(f"hardware:{item}")
        lines.append({"item": f"hardware:{item}", "name": HARDWARE[item], "qty": n, **_amounts(p or {}, n)})
    return {
        "lines": lines,
        "monthly_total": sum(line["monthly"] for line in lines),
        "once_total": sum(line["once"] for line in lines),
        "missing_prices": missing,
    }


def _amounts(p: dict[str, int], qty: int) -> dict[str, int]:
    return {"monthly": int(p.get("monthly", 0)) * qty, "once": int(p.get("once", 0)) * qty}
