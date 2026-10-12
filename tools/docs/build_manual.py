# ruff: noqa: E501  (manual text: long prose lines are the content)
"""Build the complete user and setup manual as a PDF, with screenshots from the browser test runs.

    uv run --with reportlab --with pillow python tools/docs/build_manual.py
    -> docs/Kiosk-Platform-Manual.pdf

Run the browser suites first (tools/screens/e2e*.py) so the screenshots are current.
"""

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "Kiosk-Platform-Manual.pdf"
BRAND = colors.HexColor("#c8102e")
INK = colors.HexColor("#1c1917")
MUTED = colors.HexColor("#6b625b")
SOFT = colors.HexColor("#f6f1ec")
LINE = colors.HexColor("#e5ddd5")
OKC = colors.HexColor("#15803d")

ss = getSampleStyleSheet()
S = {
    "title": ParagraphStyle("t", parent=ss["Title"], fontSize=30, leading=36, textColor=INK, spaceAfter=10),
    "subtitle": ParagraphStyle(
        "st", parent=ss["Normal"], fontSize=14, leading=20, textColor=MUTED, alignment=TA_CENTER
    ),
    "h1": ParagraphStyle(
        "h1", parent=ss["Heading1"], fontSize=20, leading=25, textColor=BRAND, spaceBefore=4, spaceAfter=10
    ),
    "h2": ParagraphStyle(
        "h2", parent=ss["Heading2"], fontSize=14, leading=18, textColor=INK, spaceBefore=12, spaceAfter=6
    ),
    "h3": ParagraphStyle(
        "h3", parent=ss["Heading3"], fontSize=11.5, leading=15, textColor=INK, spaceBefore=8, spaceAfter=4
    ),
    "body": ParagraphStyle("b", parent=ss["Normal"], fontSize=10, leading=14.5, textColor=INK, spaceAfter=5),
    "small": ParagraphStyle("s", parent=ss["Normal"], fontSize=8.5, leading=11.5, textColor=MUTED),
    "cell": ParagraphStyle("c", parent=ss["Normal"], fontSize=9, leading=12, textColor=INK),
    "cellb": ParagraphStyle(
        "cb", parent=ss["Normal"], fontSize=9, leading=12, textColor=INK, fontName="Helvetica-Bold"
    ),
    "caption": ParagraphStyle(
        "cap",
        parent=ss["Normal"],
        fontSize=8.5,
        leading=11,
        textColor=MUTED,
        alignment=TA_CENTER,
        spaceAfter=10,
    ),
    "bullet": ParagraphStyle(
        "bl",
        parent=ss["Normal"],
        fontSize=10,
        leading=14,
        textColor=INK,
        leftIndent=14,
        bulletIndent=4,
        spaceAfter=2,
    ),
    "box": ParagraphStyle("bx", parent=ss["Normal"], fontSize=9.5, leading=13.5, textColor=INK),
}
story: list = []


def h1(t: str) -> None:
    story.append(PageBreak())
    p = Paragraph(t, S["h1"])
    p.toc_level = 0  # type: ignore[attr-defined]
    story.append(p)


def h2(t: str) -> None:
    p = Paragraph(t, S["h2"])
    p.toc_level = 1  # type: ignore[attr-defined]
    story.append(p)


def h3(t: str) -> None:
    story.append(Paragraph(t, S["h3"]))


def p(t: str) -> None:
    story.append(Paragraph(t, S["body"]))


def bullets(items: list[str]) -> None:
    for it in items:
        story.append(Paragraph(it, S["bullet"], bulletText="•"))
    story.append(Spacer(1, 4))


def steps(items: list[str]) -> None:
    for i, it in enumerate(items, 1):
        story.append(Paragraph(it, S["bullet"], bulletText=f"{i}."))
    story.append(Spacer(1, 4))


def box(title: str, text: str, color: colors.Color = BRAND) -> None:
    inner = Paragraph(f"<b>{title}</b><br/>{text}", S["box"])
    t = Table([[inner]], colWidths=[16.4 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("LINEBEFORE", (0, 0), (0, -1), 3, color),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(Spacer(1, 3))
    story.append(t)
    story.append(Spacer(1, 7))


def table(head: list[str], rows: list[list[str]], widths: list[float] | None = None) -> None:
    data = [[Paragraph(x, S["cellb"]) for x in head]] + [[Paragraph(x, S["cell"]) for x in r] for r in rows]
    widths = widths or [16.4 / len(head)] * len(head)
    t = Table(data, colWidths=[w * cm for w in widths], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1e4e0")),
        ("LINEBELOW", (0, 0), (-1, 0), 1, BRAND),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fbf8f5")))
    t.setStyle(TableStyle(style))
    story.append(t)
    story.append(Spacer(1, 8))


def shot(rel: str, caption: str, max_w: float = 15.5, max_h: float = 10.5) -> None:
    path = ROOT / rel
    if not path.exists():
        return
    img = Image(str(path))
    iw, ih = img.imageWidth, img.imageHeight
    scale = min(max_w * cm / iw, max_h * cm / ih)
    img.drawWidth, img.drawHeight = iw * scale, ih * scale
    frame = Table([[img]], colWidths=[img.drawWidth + 6])
    frame.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(KeepTogether([Spacer(1, 4), frame, Paragraph(caption, S["caption"])]))


def two_shots(a: str, ca: str, b: str, cb: str, max_h: float = 9.5) -> None:
    cells = []
    for rel, cap in ((a, ca), (b, cb)):
        path = ROOT / rel
        if not path.exists():
            cells.append(Paragraph("", S["caption"]))
            continue
        img = Image(str(path))
        scale = min(7.8 * cm / img.imageWidth, max_h * cm / img.imageHeight)
        img.drawWidth, img.drawHeight = img.imageWidth * scale, img.imageHeight * scale
        cells.append([img, Paragraph(cap, S["caption"])])
    t = Table([cells], colWidths=[8.2 * cm, 8.2 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    story.append(KeepTogether([Spacer(1, 4), t]))


class Doc(SimpleDocTemplate):
    def afterFlowable(self, flowable):  # noqa: N802 - reportlab hook name
        level = getattr(flowable, "toc_level", None)
        if level is not None:
            self.notify("TOCEntry", (level, flowable.getPlainText(), self.page))


def on_page(canvas, doc):  # noqa: ANN001
    canvas.saveState()
    w, hgt = A4
    canvas.setStrokeColor(LINE)
    canvas.line(2 * cm, hgt - 1.4 * cm, w - 2 * cm, hgt - 1.4 * cm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(2 * cm, hgt - 1.2 * cm, "AI Hospitality Kiosk Platform · Manual")
    canvas.drawRightString(w - 2 * cm, 1.2 * cm, f"Page {doc.page}")
    canvas.drawString(2 * cm, 1.2 * cm, f"Version {date.today().isoformat()}")
    canvas.restoreState()


def on_first(canvas, doc):  # noqa: ANN001
    canvas.saveState()
    w, hgt = A4
    canvas.setFillColor(BRAND)
    canvas.rect(0, hgt - 6 * cm, w, 6 * cm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 44)
    canvas.drawString(2 * cm, hgt - 3.6 * cm, "K")
    canvas.restoreState()


# =====================================================================================  COVER
story.append(Spacer(1, 6.5 * cm))
story.append(Paragraph("AI Hospitality Kiosk Platform", S["title"]))
story.append(
    Paragraph(
        "The complete manual: how the system works, how to set up a restaurant, and how every person uses every screen",
        S["subtitle"],
    )
)
story.append(Spacer(1, 1.2 * cm))
table(
    ["Part", "What it covers", "Who reads it"],
    [
        ["1  The system", "What it is, the people, how an order travels, cloud and Hybrid", "Everyone"],
        [
            "2  Setting up a restaurant",
            "Sales visit, Platform console, the 7 setup steps, going live",
            "Sales, installers",
        ],
        [
            "3  Hardware",
            "Kiosks, POS terminals, printers, card readers, network, hub, SMS, the restaurant's own POS",
            "Installers, support",
        ],
        [
            "4  Using every screen",
            "Guest kiosk and table, cashier, kitchen, waiter, boards, owner, menu editor",
            "Restaurant staff, owners, trainers",
        ],
        ["5  Rules", "Every business rule the system follows", "Everyone"],
        [
            "6  Daily routine and support",
            "Opening, service, closing, problems and fixes",
            "Restaurant staff, support",
        ],
        ["7  Reference", "Logins for testing, addresses, words used", "Everyone"],
    ],
    [4.2, 8.2, 4.0],
)
story.append(Spacer(1, 0.6 * cm))
story.append(
    Paragraph(
        "Written for: our team (sales, installation, support) and the restaurants we set up (owners, managers, cashiers, kitchen staff, waiters). Screenshots are from the system's own test runs.",
        S["small"],
    )
)

story.append(PageBreak())
story.append(Paragraph("Contents", S["h1"]))
toc = TableOfContents()
toc.levelStyles = [
    ParagraphStyle("toc0", fontName="Helvetica-Bold", fontSize=11, leading=16, leftIndent=0, textColor=INK),
    ParagraphStyle("toc1", fontName="Helvetica", fontSize=9.5, leading=13, leftIndent=16, textColor=MUTED),
]
story.append(toc)

# =====================================================================================  PART 1
h1("Part 1 · The system")
h2("1.1 What it is")
p(
    "A permanent screen network for restaurants in Sri Lanka, run from one cloud, with <b>five screens</b>: <b>table screens</b> and <b>self-order kiosks</b> where guests order and pay, the <b>POS</b> (cashier) where staff run orders, tables, payments and every alert, the <b>kitchen display (KDS)</b>, and an optional <b>order status board</b>. The owner sees everything live on the <b>Owner dashboard</b>. We deliver it turnkey: screens, network, printers, installation, training and support."
)
bullets(
    [
        "<b>One app for every screen.</b> A one-time setup code decides whether a tablet becomes Table T5, Kiosk 1, the grill kitchen or the cashier.",
        "<b>Every restaurant is separate.</b> Each sees only its own menu, orders, staff and reports. Branches of one restaurant share an owner, loyalty members and reports.",
        "<b>Three languages</b> on guest screens: English, Sinhala, Tamil. Money in LKR; service charge, VAT and SSCL are handled as tax rules.",
        "<b>Manual or AI mode.</b> Restaurants start in Manual. AI mode (levels 1–4) can give insights, suggest add-ons, reorder screens when the kitchen is busy, and propose discounts on stock close to its use-by time, always within the owner's limits.",
    ]
)

h2("1.2 The people and what they use")
table(
    ["Person", "Uses", "Logs in with", "Can do"],
    [
        [
            "Our platform admin",
            "Platform console",
            "Team email + password",
            "Create restaurants, packages, prices; open any restaurant's Setup console",
        ],
        [
            "Our installer / support",
            "Setup console (per restaurant)",
            "Team email + password",
            "Screens, hardware, printers, payments, POS, hub, go-live checklist",
        ],
        [
            "Restaurant owner",
            "Owner dashboard, Menu editor",
            "Owner email + password",
            "Sales, reports, tax ledger, stock, AI mode, loyalty, menu and prices",
        ],
        [
            "Manager",
            "Cashier, kitchen, table (staff mode)",
            "Staff PIN",
            "Everything a cashier can, plus voids, refunds, screen settings",
        ],
        [
            "Cashier",
            "Cashier POS",
            "Staff PIN",
            "Take orders and payments, cash shift, hand over ready orders",
        ],
        [
            "Kitchen staff",
            "Kitchen display (KDS)",
            "No login (the screen is set up)",
            "Start, bump, recall, sold out, remake, waste",
        ],
        [
            "Floor staff",
            "POS (Tables), table screen staff mode",
            "Staff PIN",
            "Open and close tables, answer calls, order for guests, take payment at the table",
        ],
        [
            "Guest",
            "Kiosk, table screen",
            "Nothing",
            "Order, pay, call the waiter, join rewards, get a text when ready",
        ],
    ],
    [3.1, 3.6, 3.3, 6.4],
)
box(
    "Rule",
    "Screens, printers, payments, the hub and the POS connection are set up only by our team (Setup console). The restaurant never sees the Setup console; it runs the restaurant through the Owner dashboard, the Menu editor and the screens.",
)

h2("1.3 How one order travels")
steps(
    [
        "A guest orders on a <b>table screen</b> or <b>kiosk</b> (or staff on the <b>POS</b>). The order gets its number at once: K007 (kiosk), T008 (table), A012 (counter).",
        "The <b>server prices it</b> from the menu. It never trusts a price sent by a screen. Member discounts and approved deals come off first, then service charge, VAT and SSCL are added.",
        "<b>Payment</b>: QR payment or card, where the bank's signed confirmation is the only proof; cash at the cashier; or the restaurant's own POS says it was paid. Table guests can instead keep an open tab and pay at the end.",
        "<b>Kitchen</b>: the order goes to the kitchen display, split by station (grill, wok, bar…), rush and VIP first, each with a promised time. Portions come off stock; at zero the item is sold out on every screen.",
        "<b>Ready</b>: the number shows on the status board, the cashier sees it in <i>Ready to hand over</i>, the waiter sees it to serve, and the guest gets a text if they left a number.",
        "<b>Receipt</b>: it prints where the guest paid (the kiosk's own printer, or the till's). It carries the invoice number and points earned, and the guest can also get it by text.",
        "The <b>owner</b> sees it live: sales, taxes, late orders, voids and remakes, and the tax ledger for IRD.",
        "<b>Every alert goes to the POS</b>: new table and kiosk orders, guests calling staff or asking for the bill, and ready orders ring there with the table number.",
    ]
)
two_shots(
    "e2e-react-shots/6-kds-ticket.png",
    "Kitchen display: tickets by station",
    "e2e-react-shots/7-board-ready.png",
    "Status board: Preparing and Ready",
)

h2("1.4 Online and offline: Cloud or Hybrid")
p("Each restaurant is one of two kinds, chosen with its package:")
table(
    ["", "Cloud", "Hybrid"],
    [
        [
            "What is in the restaurant",
            "Screens, printers and the router",
            "The same, plus a small <b>hub</b> box next to the router, on the UPS",
        ],
        [
            "Screens talk to",
            "The cloud, over the internet",
            "The hub, over the restaurant's own Wi-Fi (the cloud only if the hub is down)",
        ],
        [
            "Internet goes down",
            "Screens show <i>Offline — retrying</i>; no new orders until it is back",
            "<b>Nothing stops.</b> Tables, kiosks, cashier, kitchen, boards and printers keep working. QR payment switches off (it needs the bank); cash and card terminals with their own SIM still work",
        ],
        [
            "Internet comes back",
            "Screens carry on",
            "The hub sends everything it kept, each order exactly once",
        ],
        [
            "Hub breaks",
            "–",
            "Screens switch to the cloud by themselves (numbers continue from 500). When the hub returns it catches up, then takes over again",
        ],
    ],
    [3.6, 5.4, 7.4],
)
p(
    "Every screen shows where it is connected: <b>Live · Local</b> (through the hub) or <b>Cloud (hub down)</b>."
)
two_shots(
    "e2e-hybrid-shots/h1-kiosk-local.png",
    "Hybrid kiosk working through the hub",
    "e2e-hybrid-shots/h2-kiosk-cloud-backup.png",
    "Hub down: the same kiosk works through the cloud (order K502)",
)
h3("The local network: what our installers do")
bullets(
    [
        "Set every tablet up from the <b>hub's address</b>: the Setup console's QR code already points there for a Hybrid restaurant.",
        "In the router, <b>reserve the hub's IP address</b> (DHCP reservation). The hub also finds its own address and tells the cloud every minute, so if the router changes it anyway, the screens find the hub again by themselves.",
        "A screen opened from the cloud address (https) cannot reach the hub (plain http on the Wi-Fi): browsers block that. It moves itself to the hub's address the first time the cloud says the hub is in charge, with its setup.",
        "Web screens served by the hub can't keep an offline copy of themselves, so a full reload while the hub restarts shows an error until it is back. The Android app keeps its screens inside the app, so it does not have this problem; use it for unattended screens.",
    ]
)
box(
    "Rule",
    "Only one side changes orders at a time. While the hub is alive the cloud sends screens back to it and hands it the bank's payment confirmations. So the two copies never conflict.",
)

# =====================================================================================  PART 2
h1("Part 2 · Setting up a restaurant")
p("The whole path, from the first visit to a restaurant that runs by itself:")
table(
    ["Stage", "Where", "Time"],
    [
        ["A. Sales visit: decide what the restaurant needs", "At the restaurant", "1 hour"],
        ["B. Create the restaurant (4 parts)", "Platform console", "5 minutes"],
        [
            "C. Setup steps 1, 2, 5 (details, menu, staff, payments)",
            "Setup console, at the office",
            "1–3 hours",
        ],
        [
            "D. Setup steps 3, 4, 6, 7 (network, screens, printers, test)",
            "Setup console, on site",
            "Half a day",
        ],
        ["E. Training and go live", "At the restaurant", "1 hour"],
    ],
    [9.4, 4.4, 2.6],
)

h2("2.1 Sales visit")
p(
    "Write down: the number of tables, counters and kiosks wanted; the kitchen stations (grill, wok, bar…); the internet line; where the power sockets are; and whether they already have a POS they want to keep. Then decide <b>how the restaurant works</b>. These are the <i>flows</i> you tick when you create it:"
)
table(
    ["The restaurant wants…", "Flow to tick", "It brings (added automatically, locked)"],
    [
        [
            "Guests order and pay alone at a kiosk",
            "Self-order kiosks",
            "Kiosk, kitchen display, a kiosk printer per kiosk; kitchen starts after payment; guests pick up",
        ],
        [
            "A screen on every table",
            "Order at the table",
            "Table screens, kitchen display, a cashier to pay at (unless they keep their own POS)",
        ],
        [
            "Guests pay after eating (the waiter brings the bill)",
            "Pay after eating",
            "One check per table; Order at the table",
        ],
        [
            "Waiters take orders and payment at the table",
            "Waiter app",
            "Waiter phone or tablet; Order at the table",
        ],
        [
            "Staff take orders and run the tables on our till",
            "POS (our cashier)",
            "POS; a receipt printer, cash drawer and scanner per POS",
        ],
        [
            "Empty tables must not take orders",
            "Staff open each table (More options)",
            "Order at the table; tables stay locked until staff open them on the POS",
        ],
        [
            "To keep their current till",
            "Keep the restaurant's current POS",
            "The POS bridge; their POS acts as the cashier",
        ],
        [
            "A Preparing / Ready wall screen (optional)",
            "Order status display",
            "Status board; leave it out when food is served at the table",
        ],
        [
            "Paper tickets in the kitchen too",
            "Kitchen ticket printer",
            "Kitchen printer; every ticket also prints",
        ],
        ["Never to stop when the internet drops", "Works without internet (Hybrid)", "The hub and a UPS"],
        ["To text guests when food is ready", "Texts to guests", "Ready texts and receipt links"],
    ],
    [4.6, 3.8, 8.0],
)
box(
    "Tip",
    "You do not have to remember what goes with what. When you tick a flow, everything it needs is added and locked, with the reason shown. Packs 1–3 accept only the flows their tier can add; anything else is Pack 4 Custom.",
)

h2("2.2 Platform console: create the restaurant")
p(
    "Open <b>/platform</b> and log in with your team login. Press <b>New restaurant</b>. The form has four numbered parts:"
)
steps(
    [
        "<b>The restaurant</b>: company or brand, first branch name, branch code (printed on invoices), time zone.",
        "<b>The owner's login</b>: their email, a password (one is suggested), the first manager PIN, and whether to start with the sample menu.",
        "<b>Package and how it works</b>: package and tier, the flows, add-ons (AI mode, loyalty, inventory, split bill…), extra screens, and equipment (router, printers, drawers, readers, scanners, hub, UPS). The preview lists every screen, every piece of equipment and the monthly and one-time price.",
        "<b>Create</b>: this makes the restaurant, the owner's login and every <b>screen slot</b> (Table T1…Tn, Kiosk 1, Kitchen 1, Cashier 1…).",
    ]
)
shot(
    "e2e-react-shots/14-platform.png",
    "Equipment in the package: items required by the chosen screens are locked with their minimum and reason",
    max_h=9,
)
p(
    "Give the owner their email and password. Each restaurant's row shows <b>Setup n / 11</b> (12 for Hybrid) and the button <b>Open setup console</b>."
)

h2("2.3 Setup console: the 7 steps")
p(
    "The Setup console guides you. Numbered steps run across the top; each says in one line what to do, gets a tick when it is done, and the console opens on the first step that is not finished. <b>Show everything</b> puts all cards on one page for experienced installers."
)
shot("e2e-react-shots/15a-setup-restaurant.png", "Setup console, step 1 of 7", max_h=9.5)
h3("Step 1 · Restaurant (office)")
bullets(
    [
        "<b>Package</b>: check the screens and slots are as sold.",
        "<b>Business details</b>: legal name, VAT registration number (with it, receipts say <i>Tax invoice</i>), receipt footer.",
        "<b>How this restaurant works</b>: set by the flows; check table orders (pay first or tab), ready food (pick up or waiter), texts, the kitchen start rule, unpaid order expiry, cooks per shift.",
        "<b>Welcome photos</b> for kiosks and tables, and <b>Add a branch</b> if the restaurant has more than one.",
    ]
)
h3("Step 2 · Menu & staff (office)")
bullets(
    [
        "<b>Open the menu editor</b>: categories and when they are served (breakfast, lunch…); items in English, Sinhala and Tamil with photo, price, kitchen station, allergens, cooking time, add-ons, meals (combos), and the POS code (PLU) if they keep their POS.",
        "<b>Taxes</b>: service charge 10%, VAT 18%, SSCL 2.5% (as rules with start dates).",
        "<b>Staff and PINs</b>: every cashier, waiter, kitchen person and manager.",
    ]
)
shot(
    "e2e-systems-shots/3b-menu-new-item.png",
    "Menu editor: an item in three languages with photo, price and station",
    max_h=8.5,
)
h3("Step 3 · Network & equipment (on site, first)")
steps(
    [
        "Router in, with a <b>separate Wi-Fi for the screens</b> (never the guest Wi-Fi). Put the router, the hub and the cashier on the UPS.",
        "<b>Hybrid only</b>: press <b>Hub setup code</b>, run the command it shows on the hub box (<i>kiosk hub-setup …</i>), start the hub. It turns <b>Online</b>.",
        "<b>Equipment</b>: tick the router and UPS as installed. Printers, cash drawers, card readers and scanners are counted by themselves.",
    ]
)
h3("Step 4 · Screens (on site)")
steps(
    [
        "Find the tablet's slot in the list and press <b>Setup code</b>. A window shows the server address, a 6-digit code and a QR code.",
        "On the tablet open the app, scan the QR code (or type the code) and press <b>Connect</b>. It opens as that screen, for good.",
        "Press <b>Hardware</b> and choose what it is. An <b>all-in-one kiosk</b> brings a built-in printer, card reader and QR scanner; a <b>POS terminal</b> a printer, cash drawer and scanner; a <b>kitchen screen</b> is plain or has a ticket printer. Type the card reader's serial if it has one.",
        "For kitchen screens, choose the station (or all stations).",
    ]
)
two_shots(
    "e2e-react-shots/15-setup-screens.png",
    "Setup code: server address, 6-digit code and QR",
    "e2e-systems-shots/28h-setup-all-in-one-kiosk.png",
    "Hardware: all-in-one kiosk, with what is still to do",
)
h3("Step 5 · Payments")
bullets(
    [
        "<b>Ways to pay</b>: cash, QR payment, card. What is switched off disappears from the screens.",
        "<b>QR payment merchant account</b>: provider, merchant ID and key from the bank, then <b>Test connection</b> until it says <i>Connection OK</i>. Keep <i>Live payments</i> off while testing.",
        "<b>Card readers</b>: every screen with a reader, then <b>Test reader</b>. For tables choose a reader (the guest pays alone) or tap on the tablet (only with a waiter logged in).",
        "<b>Restaurant's own POS</b> (if they keep it): see Part 3.7.",
    ]
)
h3("Step 6 · Printers (on site)")
bullets(
    [
        "Built-in printers from step 4 are already listed: on that screen tap <b>Connect printer</b>.",
        "Other printers: <b>+ Add printer</b>, then choose <b>Cloud printer</b> (type the URL shown into the printer's own settings page) or <b>Plugged into a screen</b> (USB, then tap Connect on that screen).",
        "Choose what it prints (receipts, order numbers, kitchen tickets for some or all stations) and whether a cash drawer is connected. Then <b>Print test page</b>. The printer ticks itself when the page comes out.",
    ]
)
h3("Step 7 · Test & go live")
steps(
    [
        "Run one real order through every path the restaurant uses: table, kitchen, ready, paid; kiosk with QR payment or card, status board, collect; cash at the cashier with drawer and receipt; a waiter card tap; their POS marking an order paid.",
        "Hybrid: pull the internet cable, take one more order, plug it back and watch it sync.",
        "Every line green means <b>Ready to go live</b>. Press any red line and the console opens the step that fixes it.",
    ]
)
shot("e2e-react-shots/17-setup-go-live.png", "Go-live checklist", max_h=10)

h2("2.4 Training and going live")
table(
    ["Who", "Show them (about 1 hour in total)"],
    [
        [
            "Cashier",
            "PIN login; open and close the cash shift; take payment; the pay-at-cashier list; hand over ready orders; refunds need a manager",
        ],
        ["Kitchen", "Tickets by station; start and bump; recall; sold out; remake with a reason; log waste"],
        [
            "Floor staff",
            "POS Tables: open and close tables, answer calls, take payment; staff mode on the table screen",
        ],
        [
            "Owner",
            "Dashboard; menu and price changes; reports and the tax ledger; stock; AI mode (starts in Manual); loyalty members",
        ],
    ],
    [3, 13.4],
)

# =====================================================================================  PART 3
h1("Part 3 · Hardware and connections")
h2("3.1 Tablets and screens")
table(
    ["Screen", "Typical hardware", "How it is set up"],
    [
        [
            "Table screen",
            '8" Android tablet on a stand, charging cable',
            "Setup code; table number comes from the slot",
        ],
        [
            "Self-order kiosk",
            "All-in-one kiosk (screen, 80 mm printer, card reader, QR scanner)",
            "Setup code, then Hardware: All-in-one kiosk + reader serial",
        ],
        [
            "Cashier POS",
            "POS terminal (printer, cash drawer port, scanner, customer display) or tablet + USB printer + drawer",
            "Setup code, then Hardware: POS terminal",
        ],
        [
            "Kitchen display",
            "Splash-proof screen on the wall, optional bump bar and ticket printer",
            "Setup code, station, then Hardware",
        ],
        ["Order status board (optional)", 'TV (32–55") with an Android stick or box', "Setup code"],
    ],
    [3.2, 7.0, 6.2],
)
box(
    "Rule",
    "A screen is set up once. It never logs out and opens straight to its screen after every restart or power cut. Only <b>Re-pair</b> or <b>Disable</b> in the Setup console ends its setup (for example when a tablet is replaced). Holding its top-left corner for 3 seconds opens screen settings with a manager PIN; making it forget its setup needs an installer login.",
)

h3("Set up once, opens by itself")
bullets(
    [
        "Every tablet's start page is the launcher (<b>/</b>; the server's own address opens it too). Scan the QR code from the Setup console with the tablet's camera, or type the 6-digit code.",
        "From then on, every start (power cut, restart, update) opens that screen by itself. The setup is kept for good; only <b>Set up again</b> or <b>Turn off</b> in the Setup console ends it.",
        "Each tablet tells the Setup console what it is: model, Android version, browser or app version, screen size and its address on the network. If one tablet was set up as two screens, the console says so.",
        "<b>Identify</b> in the Setup console makes that screen show its name in big letters for 8 seconds, so you know which tablet is which.",
    ]
)

h2("3.2 The self-order kiosk")
steps(
    [
        "Mount it, connect power and the screen Wi-Fi (or cable).",
        "Open the app and scan the QR code of its <b>Kiosk</b> slot.",
        "Setup console, <b>Hardware</b>: <b>All-in-one kiosk</b>, type the card reader's serial, Save. Its built-in printer (receipts and order numbers, for this kiosk only), the card reader and the scanner are set up.",
        "On the kiosk tap <b>Connect printer</b>, then <b>Print test page</b>; in Payments press <b>Test reader</b>.",
    ]
)
p(
    "<b>How guests use it:</b> welcome photos; choose a language (Easy reach moves everything down for wheelchair users and children); browse categories for the time of day; choose options and meals; suggestions after adding; optional Rewards with a phone number; confirm, and the number appears; pay by QR payment, card, or at the cashier (a slip with a barcode prints); the receipt prints on the kiosk; optionally <i>Text me when it's ready</i>; watch the status board and collect. The kiosk resets itself when nobody touches it, so nothing of the last guest stays on screen."
)
two_shots(
    "e2e-react-shots/3-kiosk-pay.png",
    "Kiosk: tap or insert the card on the reader",
    "e2e-systems-shots/28e-kiosk-receipt-on-own-printer.png",
    "The receipt prints on the kiosk's own printer",
)

h2("3.3 Printers")
table(
    ["Type", "Best for", "How to connect"],
    [
        [
            "Cloud printer (Star CloudPRNT)",
            "Counter and kitchen",
            "Printer on the network. In its settings page: CloudPRNT, Server URL (shown in the Setup console), polling 5 s. In Hybrid the URL points at the hub, so printing works without internet",
        ],
        [
            "USB printer into a screen",
            "Kiosk built-in printers; a printer next to a till",
            "Plug into the tablet (OTG adapter on Android). Tap Connect printer on that screen once; it reconnects by itself",
        ],
    ],
    [4.2, 4.2, 8.0],
)
bullets(
    [
        "<b>Receipts</b> print on the printer of the screen where the guest paid; if that screen has none, a shared counter printer prints it.",
        "<b>Order-number slips</b>: the kiosk's or till's printer (or the receipt printer if there is no slip printer).",
        "<b>Kitchen tickets</b>: every kitchen printer, or only its stations (a bar printer prints drinks only).",
        "<b>Cash drawer</b>: connected to a receipt printer; it opens on cash payments.",
        "Every slip waits in a print queue, so a printer that was off or out of paper prints what it missed. Failures show on the cashier and kitchen screens.",
    ]
)

h2("3.4 Card payments")
table(
    ["Where", "Hardware", "How it works"],
    [
        [
            "Kiosk",
            "Certified built-in reader (e.g. PAX IM30)",
            "The kiosk sends the amount; the guest taps or inserts; the bank's signed confirmation completes it. Card numbers never reach our system",
        ],
        [
            "Cashier",
            "A reader, or SoftPOS (tap on the staff tablet)",
            "Same. A countertop bank terminal that is not connected also works: the cashier types the approval code",
        ],
        [
            "Table",
            "A small certified NFC reader (e.g. PAX IM15), or tap on the table tablet",
            "With a reader the guest pays alone. With tap-on-tablet the guest sees <i>Paying by card? Call your waiter</i>; staff enter a PIN on the table, then the guest taps the tablet. Or the guest pays at the POS",
        ],
    ],
    [2.6, 5.0, 8.8],
)
box(
    "Rule",
    "Card-scheme rules allow tap-on-tablet (SoftPOS) only on devices operated by staff. A guest alone can pay by card only with a certified reader. The system enforces this.",
)
shot(
    "e2e-systems-shots/30a-table-card-call-waiter.png",
    "Table with tap-on-tablet: the guest is asked to call staff",
    max_h=8,
)

h2("3.5 Network, UPS and hub")
bullets(
    [
        "<b>Router</b>: business line, a 4G backup if possible, a separate screen Wi-Fi.",
        "<b>UPS</b>: router, hub and cashier.",
        "<b>Hub</b> (Hybrid only): a small fanless computer next to the router with a fixed IP address. Setup console, Network, <b>Hub setup code</b>; on the box run <i>kiosk hub-setup --cloud … --code … --lan-url http://&lt;hub-ip&gt;:8000</i> once, then start it. It shows Online with its last contact and how many changes are waiting to send.",
    ]
)
shot("e2e-systems-shots/28g-setup-hub-code.png", "Connecting a hub with a one-time code", max_h=8)

h2("3.6 Texts (SMS) to guests")
p(
    "On the kiosk, the table screen or at the cashier, the guest can leave a mobile number for that order only. They get one text when the kitchen finishes (<i>Your order K007 is ready</i>) and a private receipt link after payment. The number is never shown on any screen. Each message can be switched off in step 1 (<i>How this restaurant works</i>). A Sri Lankan SMS gateway account (sender name and API key) is needed for real texts."
)

h2("3.7 The restaurant's own POS")
p(
    "For a restaurant that keeps its current till and accounts, tick <b>Keep the restaurant's current POS</b> in the package. In step 5, on <b>Restaurant's own POS</b>:"
)
steps(
    [
        "<b>POS name and order address</b>: the URL of their POS that receives our orders.",
        "<b>Secret</b>: every order event we send is signed with it, so their POS knows it came from us.",
        "<b>Events to send</b>: order created, round added, paid, cancelled, voided (and optionally released, ready, completed).",
        "<b>Send test</b>: shows what their POS answered.",
        "<b>Create API key</b>: give it to the POS company once. Their POS calls our API with it to mark orders paid, fetch orders, and send its menu.",
        "<b>Import the POS menu</b> from their CSV export (plu, name, price, category). Items are matched by PLU; prices and names follow their POS.",
    ]
)
p(
    "<b>Live:</b> a kiosk or table order goes to their POS with PLU codes; their cashier takes the money; their POS tells us <i>paid</i>; then the kitchen starts, the receipt prints and points are earned. If their POS was down, events are sent again until it answers, and the same POS receipt sent twice is counted once."
)
shot("e2e-systems-shots/28i-setup-pos-bridge.png", "Connecting the restaurant's own POS", max_h=9)
box(
    "Choice",
    "The customer decides: <b>our POS</b> (Counter POS flow, our cashier screen), <b>their POS</b> (the POS bridge), or no counter at all (kiosk-only). Our cashier and their POS can also run together, for example while a restaurant moves over.",
)

# =====================================================================================  PART 4
h1("Part 4 · Using every screen")
h2("4.1 Guest: table screen")
p(
    "The table screen is our Android tablet app (built to the contract in docs/TABLE_APP_API.md). It is set up once with a code like every other screen and works the same way on cloud or Hybrid."
)
steps(
    [
        "Tap the screen and choose English, Sinhala or Tamil.",
        "Browse the categories; tap an item; choose options (spice, extras) or <i>Make it a meal</i>; add a note; <b>Add to order</b>.",
        "<b>Review order</b>, then <b>Confirm order</b>. The order number appears.",
        "Pay: <b>Pay here with QR payment</b> (scan with any Sri Lankan banking app), card (if the table has a reader), or <b>Pay at the cashier</b>. With an open tab, keep ordering rounds and press <b>Pay the bill</b> at the end.",
        "Watch the steps: Order placed, Paid, Preparing, Ready.",
    ]
)
bullets(
    [
        "<b>Call waiter</b> and <b>Request bill</b> are always at the top.",
        "<b>Rewards</b>: type a mobile number to join (with consent) or to be recognised; members see their tier price and <i>Your usual</i>.",
        "<b>Text me when it's ready</b>: one text when the food is ready, plus the receipt link.",
        "A table with an unpaid pay-first order is locked until it is paid, so guests cannot keep ordering without paying.",
    ]
)
two_shots(
    "e2e-react-shots/2-kiosk-menu.png",
    "Table: the order",
    "e2e-react-shots/3-kiosk-pay.png",
    "Table: how to pay",
)

h2("4.2 Guest: self-order kiosk")
p(
    "The same as the table screen, standing up, plus: welcome photos while idle; <b>Easy reach</b> for wheelchair users and children; suggestions (<i>Goes well with</i>) after adding; deal prices shown crossed out; <b>Pay at the cashier</b> prints a slip with the number and a barcode; the receipt prints on the kiosk; the kiosk resets itself after a short time without a touch."
)
two_shots(
    "e2e-react-shots/2-kiosk-menu.png",
    "Kiosk: suggestions after adding",
    "e2e-react-shots/4-kiosk-counter.png",
    "Kiosk: Text me when it's ready",
)

h2("4.3 Cashier POS")
steps(
    [
        "<b>Log in</b>: choose your name and type your PIN.",
        "<b>Open the cash shift</b>: count the drawer and type the opening float.",
        "<b>Takeaway order</b>: tap items (categories at the top), then <b>Place &amp; pay</b>.",
        "<b>Payment</b>: cash (quick amounts, change shown, drawer opens), card (reader, tap on tablet, or type the bank's approval code), QR payment on the screen. <b>Split</b> the bill by 2, 3, 4 or any amount.",
        "<b>Waiting for payment</b>: kiosk and table orders whose guests chose <i>Pay at the cashier</i>. Find them by number or scan the slip's barcode.",
        "<b>Ready to hand over</b>: call the number, give the food, press <b>Hand over</b>.",
        "<b>Close the shift</b> at the end: count the cash; the screen shows expected cash and any difference.",
    ]
)
bullets(
    [
        "<b>Rush / VIP</b> moves an order to the top of the kitchen. <b>Fire</b> sends held courses. <b>Receipt</b> reprints.",
        "<b>Voids and refunds</b> need a manager PIN. Cash refunds need an open shift.",
        "Guest calls from tables (waiter, bill) pop up with a sound.",
        "The cashier locks itself after 5 minutes without a touch; log in again with the PIN.",
    ]
)
two_shots(
    "e2e-react-shots/5-pos-cash.png",
    "Cashier: waiting for payment and ready lists",
    "e2e-react-shots/5-pos-cash.png",
    "Cashier: splitting a bill",
)

h2("4.4 Kitchen display (KDS)")
steps(
    [
        "New tickets arrive with a sound, rush and VIP first, then by promised time. Each shows the number, table or channel, items with options, notes and allergens, and <i>Due</i> (turning <i>LATE</i> when overdue).",
        "Tap an item to start it, tap again when it is done. <b>Bump</b> finishes the whole ticket. The order then shows as Ready everywhere.",
        "<b>Recall</b> brings back the last bumped ticket. <b>Remake</b> an item with a reason (burnt, dropped, wrong item…); the reason goes into the owner's reports.",
        "Held items wait with a <i>Fire</i> button until the waiter or cashier sends the next course.",
        "<b>Sold out</b>: switch an item off; it disappears from every screen at once. Waiting orders with that item are listed so staff can talk to the guest.",
        "<b>Stock</b> (if the restaurant counts stock): see what is left, log waste and shelf counts.",
    ]
)
bullets(
    [
        "Keyboard or bump bar: 1–9 select a ticket, Enter bump, F fire, R recall, S sound on/off.",
        "The top shows kitchen load: OK, Busy or Overloaded.",
    ]
)
shot(
    "e2e-react-shots/6-kds-ticket.png",
    "Kitchen display: a rush order first, a held item waiting for fire",
    max_h=8,
)

h2("4.5 Running the tables on the POS")
p("The POS is where the floor is run. Press <b>Tables</b> (the red number counts tables that need you).")
bullets(
    [
        "Each table shows its state: <b>Closed</b>, <b>Open · no order</b>, <b>Waiting payment</b>, <b>Cooking</b>, <b>Food ready</b>, <b>Wants the bill</b>, <b>Calling</b> (blinking), with what it still owes.",
        "Tap a table: its orders (with <b>Take payment</b>), its calls (<b>Coming</b>, <b>Done</b>), and <b>Open table</b> or <b>Guests left · close table</b>.",
        "Every call, new table or kiosk order and ready order rings on the POS with the table number.",
    ]
)
h3("When staff open each table (setting: Staff open each table)")
steps(
    [
        "An empty table's screen shows <i>Welcome! Our staff will open this table for you</i> with only <b>Call staff</b>. Nobody can order from it.",
        "Guests sit down (or press Call staff): on the POS tap the table, then <b>Open table</b>. The table screen shows the menu by itself and the call is answered.",
        "Guests order; the order goes to the kitchen display and the POS. The POS can also add items to a table's check (<b>Add items</b>) and print its bill (<b>Print bill</b>). Take payment from the table's card on the POS, or the waiter takes it at the table.",
        "Guests leave: <b>Guests left · close table</b>. It is refused while the table still owes money. The table screen goes back to the welcome screen with nothing of the last guests. A paid tab closes its table by itself.",
    ]
)
two_shots(
    "e2e-systems-shots/31a-table-locked.png",
    "A closed table: only Call staff",
    "e2e-react-shots/8a-pos-tables.png",
    "POS Tables: T22 calling, T21 cooking, T8 closed",
)
p(
    "<b>Staff on a table screen</b>: tap the small <i>Staff</i> button and enter a PIN to order for guests (with hold and fire; this also opens a closed table) or take a card tap on the tablet. It locks again by itself after 2 minutes."
)

h2("4.6 Waiter app: the bill and payment at the table")
p(
    "Restaurants where guests <b>pay after eating</b> run one <b>check per table</b>: every round goes to the kitchen at once and is added to the same check; at the end the waiter brings the bill and collects the payment at the table. The guest never walks to the counter."
)
steps(
    [
        "Log in with your PIN. The tables show their state in colour: red calling, amber wants the bill, green food ready, blue eating.",
        "Tap a table: its check shows <b>To pay</b> in big numbers, every item with its kitchen status, and four buttons: <b>Add items</b>, <b>Bill</b>, <b>Take payment</b>, <b>Close table</b>.",
        "The guest taps <b>Ask for the bill</b> on the table: your phone rings with <i>T8: Wants the bill</i>. Open the table, press <b>Bill</b> to show it and <b>Print bill</b> to bring it on paper.",
        "<b>Take payment</b>: <b>Cash</b> (type what you received or tap Exact / a note; the change to give is shown in big green numbers), <b>Card</b> (tap on the phone or the reader), or <b>QR payment</b>.",
        "When everything is paid, press <b>Close table</b> (or it closes itself). The table screen goes back to its welcome screen.",
        "<b>My cash</b> shows the cash you collected. At the end of service hand it over: type what you hand over; any difference is recorded.",
    ]
)
two_shots(
    "e2e-react-shots/9-waiter-table-check.png",
    "Waiter app: the table's check, with its calls on top",
    "e2e-react-shots/10-waiter-my-payments.png",
    "My payments: everything this waiter took today",
)
h3("Who is coming")
bullets(
    [
        "A call (<i>Calling staff</i>, <i>Wants the bill</i>) rings on the POS and on every waiter phone at once.",
        "On a waiter phone, <b>Coming</b> puts <b>your name</b> on it. On the POS, <b>Coming</b> asks <i>Who is going?</i>: tap the waiter's name.",
        "Every screen then shows <b>Priya is coming</b>, and so does the guest's table. Sent the wrong person? Press <b>Change who</b>.",
        "<b>Done</b> clears the call. When a table's bill is paid, its <i>Wants the bill</i> call clears by itself.",
    ]
)
shot("e2e-react-shots/8-pos-pick-waiter.png", "POS: pick who goes to the table", max_h=7)
h3("Today's payments: every payment can be traced")
p(
    "Press <b>Payments</b> on the POS (a waiter sees <b>My payments</b>). Every line shows the time, the order number, the table or channel, the way paid (cash, card, QR payment), <b>who took it</b> on which screen, the amount (refunds in minus), and a short reference you can read out (#DZAQMQC1). Card and QR payment lines also keep the bank's reference. The owner downloads the same list as a spreadsheet (CSV) for any day from the admin reports."
)
shot("e2e-react-shots/11-pos-ledger.png", "POS: today's payments, with who took each one", max_h=7)

h2("4.7 Order status board (optional)")
bullets(
    [
        "<i>Preparing</i> and <i>Ready</i> order numbers, updated live; guests collect when their number is in Ready.",
        "Leave it out when food is brought to the table: guests then follow their order on the table or kiosk screen and on the receipt (and by text if switched on).",
    ]
)
shot("e2e-react-shots/7-board-ready.png", "Order status board", max_h=7)

h2("4.8 Owner app")
p(
    "Open <b>/demo/owner</b> on a phone or laptop and log in with the owner email and password. Everything is live (it refreshes itself every 20 seconds). Pick <b>Today</b>, <b>Yesterday</b>, <b>This week</b>, <b>This month</b> or any dates."
)
table(
    ["Tab", "What you see and do"],
    [
        [
            "Sales",
            "Sales, paid orders, average bill, open orders, kitchen time; sales by hour; where orders came from; how guests paid; top staff; top items; service charge and taxes",
        ],
        [
            "Staff",
            "Every person: <b>orders taken</b> (and extra rounds, items, value), <b>payments collected</b> by way (cash, card, QR payment), cash shifts and cash difference, <b>table visits</b> (calls answered + food taken to tables), <b>how fast they answered</b> (average and slowest), time spent at the table, voids. Orders guests placed themselves show as <i>Guest (self-service)</i>. Download it as a CSV",
        ],
        ["Tables", "Every table: orders, sales, average bill, guest calls, answer time, which waiters went"],
        [
            "Payments",
            "Every payment of a day: time, order, table, way, who took it on which screen, invoice, bank reference, refunds in minus; totals by way and by person; CSV",
        ],
        [
            "Kitchen & service",
            "Kitchen load now, kitchen time, late orders, calls answered, finished or dropped by channel, voids, refunds and remakes with reasons, meals and suggestion sales",
        ],
        ["Stock", "Items you count: deliveries, counts, waste, use-by times, what is low or out"],
        ["Guests", "Loyalty members; export a member's data or forget them (PDPA)"],
        [
            "AI",
            "Manual or AI (levels 1–4); deals to approve or stop; insights; why each AI decision was made",
        ],
        [
            "Accounting",
            "Tax ledger, all orders and staff CSVs for any dates; check the day's card and QR payments against the bank's settlement file",
        ],
        ["Screens", "Every screen: online or when it was last seen, and which tablet it is"],
    ],
    [3, 13.4],
)
two_shots(
    "e2e-react-shots/12-owner-sales.png",
    "Owner app: sales",
    "e2e-react-shots/13-owner-staff.png",
    "Owner app: what each person did",
)

h2("4.9 Menu editor")
bullets(
    [
        "Categories: name in 3 languages, order, and the times they are served.",
        "Items: names, description, photo, price, kitchen station, tax category, allergens, cooking time, POS code (PLU), add-on groups (min / max choices), meals (combo slots with choices and upcharges), <i>Goes well with</i> suggestions.",
        "Taxes: add or change a rule with its start date (for example a new VAT rate from a given day).",
        "Every change reaches all screens within a second.",
    ]
)
shot("e2e-react-shots/16-menu-editor.png", "Menu editor: building a meal (combo)", max_h=8.5)

# =====================================================================================  PART 5
h1("Part 5 · The rules the system follows")
h2("5.1 Orders and the kitchen")
table(
    ["Rule", "What it means"],
    [
        [
            "Kitchen start (release rule)",
            "<b>A</b>: the kitchen starts only after payment (safest, default for kiosks). <b>B</b>: it starts at once and the order is handed over only when paid",
        ],
        [
            "Pay at the cashier",
            "An unpaid kiosk or table order waits in the cashier's list and expires after 10 minutes (setting)",
        ],
        [
            "Unpaid table",
            "A table with an unpaid pay-first order cannot order more until it is paid; staff can",
        ],
        [
            "Staff open tables",
            "With this setting a table takes guest orders only after staff open it on the POS; closing needs everything paid and clears the table; a paid tab closes its table; opening a table answers its call",
        ],
        [
            "Alerts",
            "Calls, bill requests, new table and kiosk orders and ready orders ring on the POS with the table number; kitchen events ring on the KDS",
        ],
        [
            "Pay after eating",
            "One check per table: rounds go to the kitchen at once and are added to the check; the guest asks for the bill, the waiter brings it and takes payment at the table; a paid check closes the table",
        ],
        [
            "Waiter cash",
            "Cash a waiter takes goes into their own cash bag (opened by itself, float 0); they hand it over at the end of service and any difference is recorded",
        ],
        ["Hold and fire", "Only staff can hold items for a later course; <i>Fire</i> sends them"],
        [
            "Promised time",
            "From cooking times, open tickets and cooks on shift; the kitchen shows Due and LATE",
        ],
        ["Kitchen colours", "Warning after 8 minutes, late after 12 (settings)"],
        [
            "Sold out",
            "Switching an item off hides it everywhere at once; with stock counting it happens automatically at zero and comes back after a delivery",
        ],
    ],
    [4.2, 12.2],
)
h2("5.2 Money and taxes")
table(
    ["Rule", "What it means"],
    [
        ["Prices", "Always from the menu on the server; a screen can never set a price"],
        [
            "Order of charges",
            "Member discount and deals first, then service charge, then VAT on the total with service charge, then SSCL; each rule has a start date",
        ],
        [
            "Payment proof",
            "QR payment and card count only when the bank's signed confirmation arrives. Money that arrives for a cancelled order is refunded automatically",
        ],
        [
            "Invoices",
            "Every paid order gets an invoice number (branch code + number); with a VAT number the receipt says Tax invoice",
        ],
        [
            "Voids and refunds",
            "Need a manager PIN; cash refunds need an open cash shift; everything is in the audit log",
        ],
        ["Split bill", "Pay by 2, 3, 4 or any amount (split bill module)"],
        ["Cash shifts", "Open with a float, close with a count; the difference is recorded"],
    ],
    [4.2, 12.2],
)
h2("5.3 Guests, loyalty, AI and privacy")
table(
    ["Rule", "What it means"],
    [
        [
            "Loyalty",
            "Joining needs consent (the consent text is stored). 1 point per Rs 100 paid; tiers (e.g. Silver from 500 points, Gold from 2000) give a discount before taxes; refunds take points back; members can be exported or forgotten",
        ],
        [
            "Texts",
            "A number is used for that order only, never shown on screens; one ready text and one receipt link; switchable per restaurant",
        ],
        [
            "AI mode",
            "Starts in Manual. Levels 1–3 never change prices. Level 4 only lowers prices, within the owner's cap (at most 50%), on stock close to its use-by time, and by default only after the owner approves. Every decision is logged; Back to Manual stops all of it",
        ],
        [
            "Kiosk privacy",
            "The kiosk resets after a short time without a touch; nothing of the last guest (order, number, typed phone) stays",
        ],
    ],
    [3.4, 13.0],
)
h2("5.4 Screens, security and setup")
table(
    ["Rule", "What it means"],
    [
        [
            "Who sets up",
            "Only our team (platform login) sets up screens, hardware, printers, payments, POS and hub. Restaurants use the Owner dashboard and Menu editor",
        ],
        [
            "Setup codes",
            "6 digits, single use, 10 minutes; after 10 wrong tries from one network, wait 5 minutes (the same for wrong passwords)",
        ],
        ["Screen keys", "Each screen has its own key; it never expires; Re-pair or Disable ends it at once"],
        [
            "Staff",
            "Each person has their own PIN; shared counters lock after 5 minutes idle; table staff mode after 2 minutes",
        ],
        ["Card rules", "Tap-on-tablet only with staff present; card numbers never reach our system"],
        ["Merchant keys", "Stored encrypted; never sent to screens"],
        [
            "Hybrid",
            "One side changes orders at a time; backup numbers from 500 and a separate invoice series; every change arrives exactly once",
        ],
        [
            "Packages",
            "Screens and modules are limited to what was sold; flows bring what they need automatically",
        ],
    ],
    [3.4, 13.0],
)

# =====================================================================================  PART 6
h1("Part 6 · Daily routine and support")
h2("6.1 A normal day")
table(
    ["When", "Who", "What"],
    [
        [
            "Opening",
            "Anyone",
            "Switch on the power. Every screen opens by itself; check the status pill says Live",
        ],
        ["Opening", "Cashier", "Log in with PIN; open the cash shift with the float"],
        [
            "Opening",
            "Kitchen",
            "Check sold-out items for today; log the morning delivery and counts if stock is counted",
        ],
        [
            "Service",
            "Everyone",
            "Screens update live. Menu, price and sold-out changes reach all screens within a second",
        ],
        ["Closing", "Cashier", "Hand over the last orders; close the shift with the counted cash"],
        [
            "Closing",
            "Owner",
            "Look at today's sales, late orders, voids and remakes; download the tax ledger at month end",
        ],
    ],
    [2.2, 2.4, 11.8],
)
h2("6.2 Problems and fixes")
table(
    ["Problem", "What to do"],
    [
        [
            "A screen says Offline — retrying",
            "Check its power and Wi-Fi. It carries on by itself when it is back; orders are not lost",
        ],
        [
            "A screen shows Set up this screen",
            "It was re-paired or disabled in the Setup console. Ask support for a new setup code",
        ],
        ["Cashier locked", "Log in again with your PIN"],
        [
            "A printer failed (message on the cashier or kitchen)",
            "Check paper, power and cable. It prints what it missed when it is back",
        ],
        [
            "QR payment is not offered",
            "The internet is down (Hybrid), or QR payment is switched off in the restaurant's payment settings",
        ],
        ["A card is declined", "Try again, or use QR payment or cash"],
        [
            "The hub is down (Hybrid)",
            "Screens switch to the cloud by themselves (Cloud (hub down)). Support replaces or restarts the hub; it catches up",
        ],
        [
            "A tablet is broken",
            "Support presses Re-pair and scans the code on the new tablet: about 2 minutes, nothing lost",
        ],
        [
            "Need more screens or a new flow",
            "Support changes the package in the Platform console; new slots appear in step 4",
        ],
    ],
    [5.6, 10.8],
)
h2("6.3 What support sees")
bullets(
    [
        "Setup console, step 4: every screen online or offline with its last contact; <b>Reload</b> and <b>Identify</b> (shows the screen's name in big letters on it) remotely.",
        "Network card: the hub, its last contact, changes waiting to send, open orders.",
        "Printers: online state, test status, jobs waiting. POS: the last events sent and their answers.",
        "The go-live checklist and the audit log of every setup change.",
    ]
)

# =====================================================================================  PART 7
h1("Part 7 · Reference")
h2("7.1 Addresses")
table(
    ["Page", "Address (under the server)", "Who"],
    [
        ["Tablet app start page", "/ (the server address)", "Every screen"],
        ["Platform console", "/platform", "Our team"],
        ["Setup console", "/demo/setup (opened from the Platform console)", "Our team"],
        ["Owner app", "/demo/owner", "Restaurant owner"],
        ["Menu editor", "/demo/menu", "Owner (and our team)"],
        [
            "Screens directly",
            "/demo/pos, ui/waiter/, ui/kds/, ui/kiosk/, ui/status/",
            "Testing",
        ],
        ["Table screen", "Android app (web reference: /screens/table.html)", "Guests"],
    ],
    [3.8, 8.4, 4.2],
)
h2("7.2 Test logins (demo data)")
table(
    ["Login", "Email / name", "Password / PIN"],
    [
        ["Platform (our team)", "platform@kiosk.lk", "platform12345"],
        ["Demo restaurant owner", "admin@demo.lk", "admin12345"],
        ["Cashier", "Nimal", "1111"],
        ["Manager", "Kamala", "9999"],
    ],
    [5, 6, 5.4],
)
p(
    "Start a test server: <i>uv run kiosk initdb</i>, <i>uv run kiosk seed</i>, <i>uv run kiosk serve --port 8000</i>. Payments, card readers and texts are simulated in testing: screens show <i>Simulate payment</i> and <i>Simulate tap</i> buttons."
)
h2("7.3 Words used")
table(
    ["Word", "Meaning"],
    [
        ["Slot", "A screen place in a restaurant (Table T5, Kiosk 1) waiting for a tablet"],
        ["Setup code", "The one-time 6-digit code (or QR) that turns a tablet into a slot's screen"],
        [
            "Flow",
            "A way the restaurant works (self-order kiosks, table ordering, waiter service…) chosen with the package",
        ],
        ["KDS", "Kitchen display system"],
        ["Station", "A part of the kitchen (grill, wok, bar) with its own tickets"],
        ["86 / sold out", "An item switched off because it has run out"],
        ["Hold and fire", "Keep items for a later course, then send them to the kitchen"],
        ["Tab", "Order in rounds, pay once at the end"],
        ["Hub", "The small box in a Hybrid restaurant that keeps it working without internet"],
        ["SoftPOS", "Taking a card by tapping it on a phone or tablet (staff devices only)"],
        ["PLU", "The item code in the restaurant's own POS"],
        ["POS bridge", "The connection between our screens and the restaurant's own POS"],
        ["Release rule", "When the kitchen starts: after payment (A) or at once (B)"],
    ],
    [3.4, 13.0],
)
box(
    "Still simulated",
    "Bank, card and SMS gateways are simulated until each restaurant's bank and SMS accounts are connected; the Android app (APK) that wraps these screens is planned (docs/APK_PLAN.md); the POS bridge has been tested against a simulated POS.",
    MUTED,
)


def build() -> None:
    doc = Doc(
        str(OUT),
        pagesize=A4,
        leftMargin=2.3 * cm,
        rightMargin=2.3 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="AI Hospitality Kiosk Platform — Manual",
        author="AI Hospitality Kiosk Platform",
        subject="How the system works, setup, and how to use every screen",
    )
    doc.multiBuild(story, onFirstPage=on_first, onLaterPages=on_page)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
