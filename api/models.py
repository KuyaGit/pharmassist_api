from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, Table, Float, Date, select, DateTime, ARRAY
from sqlalchemy.orm import relationship, column_property
from .database import Base, engine
from datetime import date, datetime, timezone
from enum import Enum
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional
from sqlalchemy.orm import object_session


class UserRole(str, Enum):
    ADMIN = 'admin'
    PHARMACIST = 'pharmacist'
    WHOLESALER = 'wholesaler'

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    initial_password = Column(String)  # Store initial password temporarily
    has_changed_password = Column(Boolean, default=False)
    role = Column(String)
    branch_id = Column(Integer, ForeignKey('branches.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    branch = relationship("Branch", back_populates="users")
    profile = relationship("Profile", back_populates="user", uselist=False)

class BranchType(str, Enum):
    RETAIL = 'retail'
    WHOLESALE = 'wholesale'

class Branch(Base):
    __tablename__ = "branches"

    id = Column(Integer, primary_key=True, index=True)
    branch_name = Column(String)
    location = Column(String)
    is_active = Column(Boolean, default=True)
    branch_type = Column(String, default=BranchType.RETAIL)
    branch_products = relationship("BranchProduct", back_populates="branch")
    users = relationship("User", back_populates="branch")
    clients = relationship("Client", back_populates="branch")
    invreports = relationship("InvReport", back_populates="branch")
    analytics = relationship("AnalyticsTimeSeries", back_populates="branch")
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    cost = Column(Float, nullable=False)
    srp = Column(Float, nullable=False)
    retail_low_stock_threshold = Column(Integer, nullable=False, default=50)
    wholesale_low_stock_threshold = Column(Integer, nullable=False, default=50)
    is_retail_available = Column(Boolean, nullable=False, default=True)
    is_wholesale_available = Column(Boolean, nullable=False, default=False)
    image_url = Column(String, nullable=True)
    branch_products = relationship("BranchProduct", back_populates="product")
    inv_report_items = relationship("InvReportItem", back_populates="product")
    analytics = relationship("AnalyticsTimeSeries", back_populates="product")
    price_history = relationship("PriceHistory", back_populates="product")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class BranchProduct(Base):
    __tablename__ = "branch_products"

    product_id = Column(Integer, ForeignKey('products.id'), primary_key=True)
    branch_id = Column(Integer, ForeignKey('branches.id'), primary_key=True)
    quantity = Column(Integer)
    is_available = Column(Boolean, default=False)
    low_stock_since = Column(DateTime, nullable=True)
    
    product = relationship("Product", back_populates="branch_products")
    branch = relationship("Branch", back_populates="branch_products")
    batches = relationship(
        "ProductBatch",
        primaryjoin="and_(BranchProduct.product_id==foreign(ProductBatch.product_id), "
                   "BranchProduct.branch_id==foreign(ProductBatch.branch_id))",
        backref="branch_product"
    )

    @property
    def peso_value(self):
        return self.quantity * self.product.cost

    @property
    def current_expiration_date(self):
        if not self.batches:
            return None
        active_batches = [b for b in self.batches if b.is_active]
        if not active_batches:
            return None
        return min(b.expiration_date for b in active_batches)

    @property
    def active_quantity(self):
        return sum(
            batch.quantity for batch in self.batches 
            if batch.is_active
        )

    @property
    def is_low_stock(self):
        if not self.product or not self.is_available:
            return False
        
        threshold = (
            self.product.wholesale_low_stock_threshold 
            if self.branch.branch_type == BranchType.WHOLESALE 
            else self.product.retail_low_stock_threshold
        )
        is_low = self.active_quantity <= threshold
        
        # Get the session
        session = object_session(self)
        if session is not None:
            # Update low_stock_since when status changes
            if is_low and not self.low_stock_since:
                self.low_stock_since = datetime.now()
                session.add(self)
                session.commit()
            elif not is_low and self.low_stock_since:
                self.low_stock_since = None
                session.add(self)
                session.commit()
            
        return is_low

    @property
    def days_in_low_stock(self):
        if not self.low_stock_since:
            return 0
        # Use local time for both
        now = datetime.now()
        delta = now - self.low_stock_since
        return max(0, delta.days)  # Ensure we don't return negative days

class InvReport(Base):
    __tablename__ = "invreports"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey('branches.id'))
    created_at = Column(DateTime, default=datetime.now)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    viewed_by = Column(Integer, nullable=True)
    is_viewed = Column(Boolean, default=False, nullable=False)
    items_count = Column(Integer, default=0)
    products_with_delivery = Column(Integer, default=0)
    products_with_transfer = Column(Integer, default=0)
    products_with_pullout = Column(Integer, default=0)
    products_with_offtake = Column(Integer, default=0)
    total_offtake_value = Column(Float, default=0)
    items = relationship("InvReportItem", back_populates="invreport")
    branch = relationship("Branch", back_populates="invreports")

class InvReportItem(Base):
    __tablename__ = "invreport_items"

    id = Column(Integer, primary_key=True, index=True)
    invreport_id = Column(Integer, ForeignKey('invreports.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    beginning = Column(Integer)
    selling_area = Column(Integer)
    offtake = Column(Integer)
    current_cost = Column(Float)
    current_srp = Column(Float)
    
    invreport = relationship("InvReport", back_populates="items")
    product = relationship("Product", back_populates="inv_report_items")
    batches = relationship("InvReportBatch", back_populates="invreport_item")

    @property
    def peso_value(self):
        return self.selling_area * self.current_cost

    @property
    def delivery_batches(self):
        return [b for b in self.batches if b.batch_type == 'delivery']

    @property
    def transfer_batches(self):
        return [b for b in self.batches if b.batch_type == 'transfer']

    @property
    def pull_out_batches(self):
        return [b for b in self.batches if b.batch_type == 'pull_out']

    @property
    def pull_out(self):
        session = Session.object_session(self)
        return session.query(func.sum(InvReportBatch.quantity))\
            .filter(
                InvReportBatch.invreport_item_id == self.id,
                InvReportBatch.batch_type == 'pull_out'
            ).scalar() or 0

    @property
    def deliver(self):
        session = Session.object_session(self)
        return session.query(func.sum(InvReportBatch.quantity))\
            .filter(
                InvReportBatch.invreport_item_id == self.id,
                InvReportBatch.batch_type == 'delivery'
            ).scalar() or 0

    @property
    def transfer(self):
        session = Session.object_session(self)
        return session.query(func.sum(InvReportBatch.quantity))\
            .filter(
                InvReportBatch.invreport_item_id == self.id,
                InvReportBatch.batch_type == 'transfer'
            ).scalar() or 0

class ExpenseScope(str, Enum):
    BRANCH = "branch"           
    MAIN_OFFICE = "main_office" 
    COMPANY_WIDE = "company_wide"   

class ExpenseType(str, Enum):
    UTILITIES = "utilities"
    SUPPLIES = "supplies"
    MAINTENANCE = "maintenance"
    SALARY = "salary"
    RENT = "rent"
    MARKETING = "marketing"
    INVENTORY = "inventory"
    TRANSPORTATION = "transportation"
    OTHERS = "others"

class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    date_created = Column(Date, default=date.today)
    scope = Column(String, nullable=False, default=ExpenseScope.BRANCH)
    branch_id = Column(Integer, ForeignKey('branches.id'), nullable=True)
    created_by_id = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    branch = relationship("Branch", backref="expenses")
    created_by = relationship("User", backref="created_expenses")

    @classmethod
    def get_branch_expenses(cls, db: Session, branch_id: int, start_date: date = None, end_date: date = None):
        """Get only branch-specific expenses"""
        query = db.query(cls).filter(
            cls.scope == ExpenseScope.BRANCH,
            cls.branch_id == branch_id
        )
        if start_date:
            query = query.filter(cls.date_created >= start_date)
        if end_date:
            query = query.filter(cls.date_created <= end_date)
        return query.all()

    @classmethod
    def get_company_wide_expenses(cls, db: Session, start_date: date = None, end_date: date = None):
        """Get company-wide expenses"""
        query = db.query(cls).filter(cls.scope == ExpenseScope.COMPANY_WIDE)
        if start_date:
            query = query.filter(cls.date_created >= start_date)
        if end_date:
            query = query.filter(cls.date_created <= end_date)
        return query.all()

    @classmethod
    def get_main_office_expenses(cls, db: Session, start_date: date = None, end_date: date = None):
        """Get main office expenses"""
        query = db.query(cls).filter(cls.scope == ExpenseScope.MAIN_OFFICE)
        if start_date:
            query = query.filter(cls.date_created >= start_date)
        if end_date:
            query = query.filter(cls.date_created <= end_date)
        return query.all()

    @classmethod
    def get_expenses_by_type(cls, db: Session, scope: str = None, branch_id: int = None, 
                           start_date: date = None, end_date: date = None):
        """Get expense breakdown by type with optional filters"""
        query = db.query(
            cls.type,
            func.sum(cls.amount).label('total_amount')
        )
        
        if scope:
            query = query.filter(cls.scope == scope)
        if branch_id and scope == ExpenseScope.BRANCH:
            query = query.filter(cls.branch_id == branch_id)
            
        if start_date:
            query = query.filter(cls.date_created >= start_date)
        if end_date:
            query = query.filter(cls.date_created <= end_date)
            
        return query.group_by(cls.type).all()

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    contact_person = Column(String)
    phone = Column(String)
    email = Column(String)
    address = Column(String)
    is_active = Column(Boolean, default=True)
    notes = Column(String)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class ProductBatch(Base):
    __tablename__ = "product_batches"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey('branches.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    quantity = Column(Integer, nullable=False)
    expiration_date = Column(Date, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    @property
    def days_until_expiry(self):
        return (self.expiration_date - date.today()).days

    @property
    def expiry_status(self):
        days = self.days_until_expiry
        if days <= 0:
            return "expired"
        elif days <= 30:
            return "critical"
        elif days <= 90:
            return "warning"
        return "good"

class InvReportBatch(Base):
    __tablename__ = "invreport_batches"

    id = Column(Integer, primary_key=True, index=True)
    invreport_item_id = Column(Integer, ForeignKey('invreport_items.id'))
    quantity = Column(Integer, nullable=False)
    expiration_date = Column(Date, nullable=False)
    batch_type = Column(String)  # 'delivery', 'transfer', or 'pull_out'
    created_at = Column(DateTime, default=datetime.now)
    
    invreport_item = relationship("InvReportItem", back_populates="batches")

class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String)
    phone_number = Column(String, nullable=True)
    license_number = Column(String, nullable=True)  # For pharmacists
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    user = relationship("User", back_populates="profile")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    class Config:
        orm_mode = True

class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    tin_number = Column(String, nullable=True)
    markup_percentage = Column(Float, default=0.0)
    payment_terms = Column(Integer, default=0)
    credit_limit = Column(Float, default=0.0)
    current_balance = Column(Float, default=0.0)
    address = Column(String)
    contact_person = Column(String)
    contact_number = Column(String)
    email = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    branch_id = Column(Integer, ForeignKey('branches.id'))
    branch = relationship("Branch", back_populates="clients")

    @property
    def available_credit(self):
        return self.credit_limit - self.current_balance

    @property
    def is_credit_available(self):
        return self.available_credit > 0

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey('clients.id'))
    branch_id = Column(Integer, ForeignKey('branches.id'))
    total_amount = Column(Float, default=0.0)
    amount_paid = Column(Float, default=0.0)
    payment_status = Column(String)  # 'pending', 'partial', 'paid'
    transaction_date = Column(DateTime, default=datetime.now)
    transaction_terms = Column(Integer)
    transaction_markup = Column(Float)
    due_date = Column(Date)
    reference_number = Column(String, unique=True)
    void_reason = Column(String, nullable=True)
    is_void = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    client = relationship("Client", backref="transactions")
    branch = relationship("Branch", backref="transactions")
    items = relationship("TransactionItem", back_populates="transaction", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="transaction")

    @classmethod
    def generate_reference(cls, db: Session, branch_id: int) -> str:
        today = date.today()
        date_part = today.strftime("%Y%m%d")
        latest = db.query(cls).filter(
            cls.branch_id == branch_id,
            cls.reference_number.like(f"WS-{branch_id}-{date_part}-%")
        ).order_by(cls.reference_number.desc()).first()
        
        if latest:
            last_sequence = int(latest.reference_number.split('-')[-1])
            new_sequence = str(last_sequence + 1).zfill(4)
        else:
            new_sequence = "0001"
        return f"WS-{branch_id}-{date_part}-{new_sequence}"

    @property
    def balance(self):
        return round(self.total_amount - self.amount_paid, 2)

    @property
    def is_overdue(self):
        return date.today() > self.due_date and self.payment_status != 'paid'

class TransactionItem(Base):
    __tablename__ = "transaction_items"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey('transactions.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    quantity = Column(Integer, nullable=False)
    base_price = Column(Float, nullable=False)
    markup_price = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    
    transaction = relationship("Transaction", back_populates="items")
    product = relationship("Product")

    def calculate_prices(self, markup_percentage: float):
        self.markup_price = round(self.base_price * (1 + markup_percentage), 2)
        self.total_amount = round(self.markup_price * self.quantity, 2)

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey('transactions.id'), nullable=False)
    client_id = Column(Integer, ForeignKey('clients.id'), nullable=False)
    amount = Column(Float, nullable=False)
    payment_date = Column(Date, nullable=False)
    recorded_by_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    is_void = Column(Boolean, default=False)
    void_reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    transaction = relationship("Transaction", back_populates="payments")
    client = relationship("Client")
    recorded_by = relationship("User")

class AnalyticsTimeSeries(Base):
    __tablename__ = "analytics_timeseries"

    id = Column(Integer, primary_key=True, index=True)
    metric_name = Column(String, nullable=False)  # e.g., 'revenue', 'expenses', 'profit'
    value = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.now)
    branch_id = Column(Integer, ForeignKey('branches.id'), nullable=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=True)

    # Relationships
    branch = relationship("Branch", back_populates="analytics")
    product = relationship("Product", back_populates="analytics")

    @classmethod
    def record_metric(cls, db: Session, metric_name: str, value: float, 
                     branch_id: Optional[int] = None, product_id: Optional[int] = None):
        """Record a new metric data point"""
        metric = cls(
            metric_name=metric_name,
            value=value,
            branch_id=branch_id,
            product_id=product_id
        )
        db.add(metric)
        db.commit()
        return metric

class PriceHistory(Base):
    __tablename__ = 'price_history'
    
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'))
    date = Column(DateTime, default=func.now())
    cost = Column(Float, nullable=False)
    srp = Column(Float, nullable=False)
    
    product = relationship("Product", back_populates="price_history")

class AppVersion(Base):
    __tablename__ = "app_versions"

    id = Column(Integer, primary_key=True, index=True)
    version_name = Column(String, nullable=False)  # e.g., "1.0.0"
    version_code = Column(Integer, nullable=False)  # e.g., 1
    apk_file_path = Column(String, nullable=False)
    release_notes = Column(String, nullable=True)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    created_by_id = Column(Integer, ForeignKey('users.id'))
    
    created_by = relationship("User", backref="app_versions")

# Create the tables if they don't exist
User.metadata.create_all(bind=engine)