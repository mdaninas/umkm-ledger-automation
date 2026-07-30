import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import get_settings
from app.database import Database
from app.models import ActorType, Customer, Invoice, InvoiceStatus
from app.seed import DEMO_BUSINESS_ID, seed_demo

DEMO_CUSTOMERS = (
    (
        uuid.UUID("bd817175-701d-470f-9195-334cc78ed09a"),
        "Warung Senja",
        "finance@warungsenja.demo",
        "+62 812 **** 4410",
    ),
    (
        uuid.UUID("5b21803e-7fb8-4a88-bf97-206aa924994d"),
        "Studio Pagi",
        "accounting@studiopagi.demo",
        "+62 811 **** 1275",
    ),
    (
        uuid.UUID("80dd5bcd-6a30-45c8-8dd8-b02a86f2a975"),
        "Rumah Rasa",
        "admin@rumahrasa.demo",
        "+62 813 **** 8951",
    ),
)

DEMO_INVOICES = (
    {
        "id": uuid.UUID("19e8270f-fda8-4828-b49c-4b94ad85eec9"),
        "customer_id": DEMO_CUSTOMERS[0][0],
        "invoice_number": "INV-2026-0730-001",
        "issue_date": date(2026, 7, 1),
        "due_date": date(2026, 7, 30),
        "subtotal": Decimal("2227272.73"),
        "tax": Decimal("222727.27"),
        "total": Decimal("2450000.00"),
        "status": InvoiceStatus.OUTSTANDING,
        "paid_at": None,
    },
    {
        "id": uuid.UUID("bc92edc5-1d97-4b22-b272-15cf5c2ef2e7"),
        "customer_id": DEMO_CUSTOMERS[1][0],
        "invoice_number": "INV-2026-0804-002",
        "issue_date": date(2026, 7, 18),
        "due_date": date(2026, 8, 4),
        "subtotal": Decimal("1227272.73"),
        "tax": Decimal("122727.27"),
        "total": Decimal("1350000.00"),
        "status": InvoiceStatus.OUTSTANDING,
        "paid_at": None,
    },
    {
        "id": uuid.UUID("da37766d-53a4-473b-a963-57bf3cdecb97"),
        "customer_id": DEMO_CUSTOMERS[2][0],
        "invoice_number": "INV-2026-0715-003",
        "issue_date": date(2026, 6, 20),
        "due_date": date(2026, 7, 15),
        "subtotal": Decimal("878378.38"),
        "tax": Decimal("96621.62"),
        "total": Decimal("975000.00"),
        "status": InvoiceStatus.PAID,
        "paid_at": datetime(2026, 7, 16, 3, 15, tzinfo=UTC),
    },
)


def seed_invoice_demo(session: Session) -> list[Invoice]:
    invoices: list[Invoice] = []
    for customer_id, name, email, phone_masked in DEMO_CUSTOMERS:
        customer = session.scalar(
            select(Customer).where(
                Customer.business_id == DEMO_BUSINESS_ID,
                Customer.email == email,
            )
        )
        if customer is None:
            customer = Customer(
                id=customer_id,
                business_id=DEMO_BUSINESS_ID,
                name=name,
                email=email,
                phone_masked=phone_masked,
            )
            session.add(customer)
            session.flush()

    for values in DEMO_INVOICES:
        invoice = session.scalar(
            select(Invoice).where(
                Invoice.business_id == DEMO_BUSINESS_ID,
                Invoice.invoice_number == values["invoice_number"],
            )
        )
        if invoice is None:
            invoice = Invoice(
                **values,
                business_id=DEMO_BUSINESS_ID,
                currency="IDR",
            )
            session.add(invoice)
            record_audit_event(
                session,
                business_id=DEMO_BUSINESS_ID,
                actor_type=ActorType.SYSTEM,
                actor_id=None,
                action="invoice.demo_seeded",
                entity_type="invoice",
                entity_id=invoice.id,
                correlation_id="seed-invoice-collection-demo",
                metadata={
                    "invoice_number": invoice.invoice_number,
                    "synthetic_data": True,
                },
            )
        invoices.append(invoice)
    session.commit()
    return invoices


def main() -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    try:
        with database.session_factory() as session:
            seed_demo(session, settings)
            invoices = seed_invoice_demo(session)
            print(
                "Invoice demo siap: "
                + ", ".join(invoice.invoice_number for invoice in invoices)
            )
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
