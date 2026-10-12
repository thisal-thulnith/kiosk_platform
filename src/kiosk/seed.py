"""Demo data: one café with a small Sri Lankan menu, three languages, and example tax rules.

The Sinhala and Tamil text and the tax rates are placeholders. Have a native speaker check the
menu text, and a Sri Lankan tax adviser confirm the rules, before using this with real guests.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kiosk.auth.security import hash_secret
from kiosk.infra.models import (
    AdminUser,
    MenuCategory,
    MenuItem,
    Modifier,
    ModifierGroup,
    PlatformUser,
    Staff,
    TaxRule,
    Tenant,
    Venue,
)

# Dev-only platform operator login. Create real ones with `kiosk create-platform-admin`.
PLATFORM: dict[str, str] = {"email": "platform@kiosk.lk", "password": "platform12345"}

DEMO: dict[str, Any] = {
    "admin_email": "admin@demo.lk",
    "admin_password": "admin12345",
    "staff": [
        ("Nimal", "cashier", "1111"),
        ("Ravi", "kitchen", "2222"),
        ("Priya", "waiter", "3333"),
        ("Kamala", "manager", "9999"),
    ],
}


def t(en: str, si: str, ta: str) -> dict[str, str]:
    return {"en": en, "si": si, "ta": ta}


async def ensure_platform_admin(session: AsyncSession, email: str, password: str, name: str = "") -> bool:
    """Create a platform operator login if it does not exist. Returns True when created."""
    if await session.scalar(select(PlatformUser).where(PlatformUser.email == email.lower())):
        return False
    session.add(PlatformUser(email=email.lower(), name=name, password_hash=hash_secret(password)))
    await session.flush()
    return True


async def seed(session: AsyncSession) -> dict[str, Any]:
    await ensure_platform_admin(session, PLATFORM["email"], PLATFORM["password"], "Platform admin")
    if await session.scalar(select(Venue).where(Venue.code == "DEMO")):
        venue = await session.scalar(select(Venue).where(Venue.code == "DEMO"))
        assert venue
        return {"venue_id": venue.id, "created": False, **DEMO, "platform": PLATFORM}

    tenant = Tenant(name="Demo Hospitality (Pvt) Ltd")
    session.add(tenant)
    await session.flush()
    venue = Venue(tenant_id=tenant.id, name="Demo Café Colombo", code="DEMO", timezone="Asia/Colombo")
    session.add(venue)
    await session.flush()

    session.add(
        AdminUser(
            tenant_id=tenant.id,
            email=DEMO["admin_email"],
            password_hash=hash_secret(str(DEMO["admin_password"])),
            role="owner",
        )
    )
    for name, role, pin in DEMO["staff"]:
        session.add(Staff(venue_id=venue.id, name=name, role=role, pin_hash=hash_secret(pin)))
    await add_sample_menu(session, venue)
    return {"venue_id": venue.id, "created": True, **DEMO, "platform": PLATFORM}


async def add_sample_menu(session: AsyncSession, venue: Venue) -> None:
    """A small Sri Lankan menu with modifiers, a breakfast window, and example SC + VAT rules."""
    mains = MenuCategory(venue_id=venue.id, sort=1, name=t("Mains", "ප්‍රධාන ආහාර", "முதன்மை உணவுகள்"))
    sides = MenuCategory(venue_id=venue.id, sort=2, name=t("Sides", "අතුරු කෑම", "பக்க உணவுகள்"))
    drinks = MenuCategory(venue_id=venue.id, sort=3, name=t("Drinks", "බීම", "பானங்கள்"))
    breakfast = MenuCategory(
        venue_id=venue.id,
        sort=0,
        name=t("Breakfast", "උදෑසන ආහාර", "காலை உணவு"),
        windows=[{"days": [0, 1, 2, 3, 4, 5, 6], "start": "06:00", "end": "11:00"}],
    )
    session.add_all([mains, sides, drinks, breakfast])
    await session.flush()

    def spice() -> ModifierGroup:
        return ModifierGroup(
            name=t("Spice level", "සැර ප්‍රමාණය", "காரத்தின் அளவு"),
            min_select=1,
            max_select=1,
            modifiers=[
                Modifier(name=t("Mild", "අඩු සැර", "குறைந்த காரம்"), sort=0),
                Modifier(name=t("Medium", "මධ්‍යම", "நடுத்தர"), sort=1),
                Modifier(name=t("Spicy", "සැර", "காரம்"), sort=2),
            ],
        )

    extras = ModifierGroup(
        name=t("Extras", "අමතර", "கூடுதல்"),
        min_select=0,
        max_select=2,
        sort=1,
        modifiers=[
            Modifier(name=t("Extra egg", "අමතර බිත්තරයක්", "கூடுதல் முட்டை"), price_delta=10000),
            Modifier(name=t("Extra cheese", "අමතර චීස්", "கூடுதல் சீஸ்"), price_delta=15000, sort=1),
        ],
    )
    items = [
        MenuItem(
            venue_id=venue.id,
            category_id=mains.id,
            sort=1,
            price=120000,
            station="wok",
            name=t("Chicken Kottu", "චිකන් කොත්තු", "சிக்கன் கொத்து"),
            allergens=["gluten", "egg"],
            modifier_groups=[spice(), extras],
        ),
        MenuItem(
            venue_id=venue.id,
            category_id=mains.id,
            sort=2,
            price=110000,
            station="wok",
            name=t("Chicken Fried Rice", "චිකන් ෆ්‍රයිඩ් රයිස්", "சிக்கன் ஃபிரைட் ரைஸ்"),
            allergens=["egg", "soy"],
            modifier_groups=[spice()],
        ),
        MenuItem(
            venue_id=venue.id,
            category_id=mains.id,
            sort=3,
            price=150000,
            station="grill",
            name=t("Devilled Chicken", "ඩෙවල් චිකන්", "டெவில்ட் சிக்கன்"),
        ),
        MenuItem(
            venue_id=venue.id,
            category_id=mains.id,
            sort=4,
            price=95000,
            station="grill",
            name=t("Chicken Burger", "චිකන් බර්ගර්", "சிக்கன் பர்கர்"),
            allergens=["gluten"],
        ),
        MenuItem(
            venue_id=venue.id,
            category_id=sides.id,
            sort=1,
            price=45000,
            station="fryer",
            name=t("French Fries", "ෆ්‍රෙන්ච් ෆ්‍රයිස්", "பிரஞ்சு பொரியல்"),
        ),
        MenuItem(
            venue_id=venue.id,
            category_id=drinks.id,
            sort=1,
            price=35000,
            station="bar",
            tax_category="beverage",
            name=t("Lime Juice", "දෙහි යුෂ", "எலுமிச்சை சாறு"),
        ),
        MenuItem(
            venue_id=venue.id,
            category_id=drinks.id,
            sort=2,
            price=40000,
            station="bar",
            tax_category="beverage",
            name=t("Iced Milo", "අයිස් මයිලෝ", "ஐஸ் மைலோ"),
            allergens=["milk"],
        ),
        MenuItem(
            venue_id=venue.id,
            category_id=breakfast.id,
            sort=1,
            price=60000,
            station="kitchen",
            name=t("String Hoppers", "ඉඳිආප්ප", "இடியப்பம்"),
        ),
    ]
    session.add_all(items)
    await session.flush()
    by_name = {i.name["en"]: i for i in items}
    # "Goes well with" suggestions shown after adding an item (Manual-mode upsell).
    by_name["Chicken Burger"].suggest_ids = [by_name["French Fries"].id, by_name["Lime Juice"].id]
    by_name["Chicken Kottu"].suggest_ids = [by_name["Lime Juice"].id, by_name["Iced Milo"].id]
    session.add(
        MenuItem(
            venue_id=venue.id,
            category_id=mains.id,
            sort=5,
            price=130000,
            station="grill",
            name=t("Burger Meal", "බර්ගර් කෑම වේල", "பர்கர் உணவு"),
            description=t(
                "Chicken burger, fries and a drink", "චිකන් බර්ගර්, ෆ්‍රයිස් සහ බීමක්", "சிக்கன் பர்கர், பொரியல் மற்றும் பானம்"
            ),
            combo_slots=[
                {
                    "name": t("Burger", "බර්ගර්", "பர்கர்"),
                    "item_ids": [by_name["Chicken Burger"].id],
                    "upcharges": {},
                },
                {
                    "name": t("Side", "අතුරු කෑම", "பக்க உணவு"),
                    "item_ids": [by_name["French Fries"].id],
                    "upcharges": {},
                },
                {
                    "name": t("Drink", "බීම", "பானம்"),
                    "item_ids": [by_name["Lime Juice"].id, by_name["Iced Milo"].id],
                    "upcharges": {by_name["Iced Milo"].id: 5000},
                },
            ],
        )
    )

    start = datetime.fromisoformat("2024-01-01T00:00:00+05:30")
    session.add_all(
        [
            TaxRule(
                venue_id=venue.id,
                code="SC",
                sequence=1,
                rate_bp=1000,
                compound=False,
                name=t("Service Charge", "සේවා ගාස්තුව", "சேவைக் கட்டணம்"),
                effective_from=start,
            ),
            TaxRule(
                venue_id=venue.id,
                code="VAT",
                sequence=2,
                rate_bp=1800,
                compound=True,
                name=t("VAT", "වැට්", "வற்"),
                effective_from=start,
            ),
        ]
    )
    await session.flush()
