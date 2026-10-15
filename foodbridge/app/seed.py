"""Sample data. Everything created here is flagged is_sample=True and labelled 'Sample' in the UI."""
import os
from datetime import timedelta

from sqlalchemy import delete, select

from . import constants as C
from .extensions import db
from .models import Donation, DonationRequest, Report, User
from .utils import now_local

DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo@1234")
DEMO_DOMAIN = "demo.foodbridge.test"

DONORS = [
    ("Asha Verma", "Green Leaf Restaurant (Sample)", "Restaurant", "Lucknow", "12 Sample Street", "+91 90000 00001"),
    ("Rohit Singh", "Campus Canteen (Sample)", "College canteen", "Varanasi", "Block A, Sample College", "+91 90000 00002"),
    ("Meera Nair", "Sunrise Hotel (Sample)", "Hotel", "Kanpur", "5 Demo Road", "+91 90000 00003"),
]
RECIPIENTS = [
    ("Imran Khan", "Sample Hope Foundation", "NGO", "Lucknow", "Demo Lane 7", "+91 90000 00011"),
    ("Priya Sharma", "Sample Helping Hands Trust", "NGO", "Varanasi", "Demo Colony 3", "+91 90000 00012"),
    ("Anil Gupta", "Sample Shelter Home", "Shelter / care home", "Kanpur", "Demo Nagar 9", "+91 90000 00013"),
]


def reset_sample_data():
    sample_ids = select(User.id).where(User.is_sample.is_(True))
    db.session.execute(delete(Report).where(Report.reporter_id.in_(sample_ids)))
    for req in db.session.execute(
        select(DonationRequest).where(DonationRequest.recipient_id.in_(sample_ids))
    ).scalars().all():
        donation = req.donation
        if not donation.is_sample and donation.status in (C.D_REQUESTED, C.D_APPROVED, C.D_COLLECTED):
            donation.status = C.D_AVAILABLE
        db.session.delete(req)
    db.session.flush()
    for donation in db.session.execute(select(Donation).where(Donation.is_sample.is_(True))).scalars().all():
        db.session.delete(donation)
    db.session.flush()
    for user in db.session.execute(select(User).where(User.is_sample.is_(True))).scalars().all():
        db.session.delete(user)
    db.session.commit()


def _user(role, spec, idx):
    name, org, org_type, city, address, phone = spec
    prefix = "donor" if role == C.DONOR else "recipient"
    user = User(name=name, email=f"{prefix}{idx}@{DEMO_DOMAIN}", role=role, organization=org,
                org_type=org_type, city=city, address=address, phone=phone, is_sample=True)
    user.set_password(DEMO_PASSWORD)
    return user


def _donation(donor, food, category, qty, unit, status, now, *, prepared_ago, deadline_in, desc, notes):
    return Donation(
        donor_id=donor.id, food_name=food, category=category, quantity=qty, unit=unit,
        description=f"[SAMPLE] {desc}", handling_notes=notes,
        prepared_at=now - timedelta(hours=prepared_ago),
        pickup_deadline=now + timedelta(hours=deadline_in),
        pickup_location=f"{donor.address}, {donor.city}", city=donor.city,
        contact_phone=donor.phone, status=status, is_sample=True,
        created_at=now - timedelta(hours=max(prepared_ago - 1, 0)),
    )


def seed_demo(reset=False):
    existing = db.session.execute(select(User.id).where(User.is_sample.is_(True))).first()
    if existing and not reset:
        raise RuntimeError("Sample data already exists. Run with --reset to recreate it.")
    if reset:
        reset_sample_data()

    now = now_local()
    donors = [_user(C.DONOR, s, i + 1) for i, s in enumerate(DONORS)]
    recipients = [_user(C.RECIPIENT, s, i + 1) for i, s in enumerate(RECIPIENTS)]
    db.session.add_all(donors + recipients)
    db.session.flush()

    created = []

    def add(donor, *args, **kw):
        d = _donation(donor, *args, now=now, **kw)
        db.session.add(d)
        db.session.flush()
        created.append(d)
        return d

    def add_request(donation, recipient, status, **stamps):
        r = DonationRequest(donation_id=donation.id, recipient_id=recipient.id, status=status,
                            note="[SAMPLE] We can collect with our own vehicle.",
                            created_at=now - timedelta(hours=1), **stamps)
        db.session.add(r)
        return r

    # --- open listings
    add(donors[0], "Vegetable biryani", "Cooked meals", 25, "servings", C.D_AVAILABLE,
        prepared_ago=1, deadline_in=3, desc="Freshly cooked, vegetarian.", notes="Keep covered; consume within 4 hours.")
    add(donors[1], "Whole wheat bread loaves", "Bakery items", 40, "pieces", C.D_AVAILABLE,
        prepared_ago=5, deadline_in=10, desc="Baked this morning, sealed in bags.", notes="Store at room temperature.")
    add(donors[2], "Packaged fruit juice", "Beverages", 12, "boxes", C.D_AVAILABLE,
        prepared_ago=24, deadline_in=48, desc="Sealed cartons, event surplus.", notes="Check printed expiry date.")
    add(donors[0], "Seasonal vegetables", "Fruits & vegetables", 18.5, "kg", C.D_AVAILABLE,
        prepared_ago=6, deadline_in=30, desc="Mixed vegetables, unsold stock.", notes="Wash before use.")
    add(donors[1], "Dal and rice combo", "Cooked meals", 60, "servings", C.D_AVAILABLE,
        prepared_ago=1, deadline_in=5, desc="Hostel mess surplus.", notes="Keep hot or refrigerate promptly.")
    # --- in-progress listings
    pending = add(donors[2], "Paneer curry", "Cooked meals", 15, "servings", C.D_REQUESTED,
                  prepared_ago=2, deadline_in=4, desc="Wedding event surplus.", notes="Consume within 3 hours.")
    add_request(pending, recipients[0], C.R_PENDING)
    approved = add(donors[0], "Packed lunch boxes", "Packaged food", 30, "packets", C.D_APPROVED,
                   prepared_ago=3, deadline_in=6, desc="Corporate lunch surplus.", notes="Sealed boxes.")
    add_request(approved, recipients[1], C.R_APPROVED, approved_at=now - timedelta(minutes=30))
    collected = add(donors[1], "Milk packets", "Dairy", 20, "packets", C.D_COLLECTED,
                    prepared_ago=8, deadline_in=8, desc="Sealed pasteurised milk.", notes="Refrigerate.")
    add_request(collected, recipients[2], C.R_COLLECTED, approved_at=now - timedelta(minutes=50),
                collected_at=now - timedelta(minutes=10))
    # --- expired & cancelled
    add(donors[2], "Leftover sandwiches", "Packaged food", 22, "pieces", C.D_EXPIRED,
        prepared_ago=14, deadline_in=-5, desc="Not collected in time.", notes="")
    add(donors[0], "Fruit platter", "Fruits & vegetables", 6, "kg", C.D_CANCELLED,
        prepared_ago=4, deadline_in=6, desc="Donor cancelled (sample).", notes="")
    # --- completed history for the impact dashboard (spread over 5 months)
    history = [
        (4, "Rice and curry", "Cooked meals", 40, "servings", 0, 0),
        (11, "Bread and buns", "Bakery items", 30, "pieces", 1, 1),
        (24, "Mixed fruit", "Fruits & vegetables", 12, "kg", 2, 2),
        (38, "Lunch packets", "Packaged food", 50, "packets", 0, 1),
        (55, "Roti and sabzi", "Cooked meals", 80, "servings", 1, 0),
        (72, "Rice sacks", "Grains & staples", 25, "kg", 2, 2),
        (95, "Juice cartons", "Beverages", 18, "boxes", 0, 0),
        (118, "Biryani", "Cooked meals", 55, "servings", 1, 1),
        (140, "Cake slices", "Bakery items", 35, "pieces", 2, 2),
    ]
    for days_ago, food, cat, qty, unit, di, ri in history:
        t = now - timedelta(days=days_ago)
        d = Donation(
            donor_id=donors[di].id, food_name=food, category=cat, quantity=qty, unit=unit,
            description="[SAMPLE] Historical completed donation.", handling_notes=None,
            prepared_at=t - timedelta(hours=6), pickup_deadline=t + timedelta(hours=1),
            pickup_location=f"{donors[di].address}, {donors[di].city}", city=donors[di].city,
            contact_phone=donors[di].phone, status=C.D_COMPLETED, is_sample=True,
            created_at=t - timedelta(hours=5),
        )
        db.session.add(d)
        db.session.flush()
        created.append(d)
        db.session.add(DonationRequest(
            donation_id=d.id, recipient_id=recipients[ri].id, status=C.R_COMPLETED,
            created_at=t - timedelta(hours=4), approved_at=t - timedelta(hours=3),
            collected_at=t - timedelta(minutes=30), completed_at=t,
        ))
    db.session.commit()
    return {
        "users": len(donors) + len(recipients), "donations": len(created),
        "emails": [u.email for u in donors + recipients],
    }
