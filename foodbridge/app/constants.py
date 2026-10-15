"""Single source of truth for roles, choices and status values."""

DONOR, RECIPIENT, ADMIN = "donor", "recipient", "admin"
ROLES = (DONOR, RECIPIENT, ADMIN)
# Admin is intentionally absent: admins are provisioned with `flask create-admin`.
SELF_REGISTER_ROLES = [
    (DONOR, "Donate surplus food"),
    (RECIPIENT, "Receive food for people in need"),
]

ORG_TYPES = [
    "Restaurant", "Hotel", "College canteen", "Hostel / mess", "Event organizer",
    "Caterer / bakery", "NGO", "Shelter / care home", "Community kitchen", "Other",
]
CATEGORIES = [
    "Cooked meals", "Bakery items", "Fruits & vegetables", "Packaged food",
    "Dairy", "Beverages", "Grains & staples", "Other",
]
UNITS = ["kg", "servings", "packets", "pieces", "liters", "boxes"]
MAX_QUANTITY = 100000

# Donation (listing) statuses
D_AVAILABLE, D_REQUESTED, D_APPROVED = "available", "requested", "approved"
D_COLLECTED, D_COMPLETED = "collected", "completed"
D_CANCELLED, D_EXPIRED = "cancelled", "expired"
DONATION_STATUSES = (
    D_AVAILABLE, D_REQUESTED, D_APPROVED, D_COLLECTED, D_COMPLETED, D_CANCELLED, D_EXPIRED,
)
DONATION_CANCELLABLE = (D_AVAILABLE, D_REQUESTED, D_APPROVED)

# Request statuses
R_PENDING, R_APPROVED, R_REJECTED = "pending", "approved", "rejected"
R_COLLECTED, R_COMPLETED = "collected", "completed"
R_CANCELLED, R_EXPIRED = "cancelled", "expired"
REQUEST_STATUSES = (
    R_PENDING, R_APPROVED, R_REJECTED, R_COLLECTED, R_COMPLETED, R_CANCELLED, R_EXPIRED,
)
ACTIVE_REQUEST_STATUSES = (R_PENDING, R_APPROVED, R_COLLECTED)
# Statuses at which pickup address / phone may be shown to the recipient
CONTACT_VISIBLE_STATUSES = (R_APPROVED, R_COLLECTED, R_COMPLETED)

# Report / issue
REPORT_CATEGORIES = [
    ("unsafe_food", "Food safety concern"),
    ("no_show", "Donor or recipient did not show up"),
    ("misleading", "Misleading listing"),
    ("abuse", "Abusive or inappropriate behaviour"),
    ("technical", "Technical problem"),
    ("other", "Other"),
]
REPORT_OPEN, REPORT_RESOLVED, REPORT_DISMISSED = "open", "resolved", "dismissed"
REPORT_STATUSES = (REPORT_OPEN, REPORT_RESOLVED, REPORT_DISMISSED)

STATUS_LABELS = {
    "available": "Available", "requested": "Requested", "approved": "Approved",
    "collected": "Collected", "completed": "Completed", "cancelled": "Cancelled",
    "expired": "Expired", "pending": "Pending review", "rejected": "Rejected",
    "open": "Open", "resolved": "Resolved", "dismissed": "Dismissed",
}
