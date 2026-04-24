"""
Data models for the Tempo database. The intent is to be able to organize artifacts (the thing containing a unique number).
"""

from datetime import datetime
from datetime import date as dtdate
from enum import Enum
from typing import List, Optional

from sqlmodel import (
    SQLModel,
    Field,
    Relationship,
    Column,
    Enum as SQLEnum,
)
from pydantic import ConfigDict  # Import ConfigDict for Pydantic V2 configuration


# ============================================================
# Database Models
# ============================================================


class ProjectType(str, Enum):
    TIME_AND_MATERIAL = "time_and_material"
    FIXED_FEE = "fixed_fee"
    NON_BILLABLE = "non_billable"


class RateType(str, Enum):
    PROJECT = "project"
    TASK = "task"


class BudgetUnit(str, Enum):
    DOLLARS = "dollars"
    HOURS = "hours"


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)

    time_entries: List["TimeEntry"] = Relationship(back_populates="user")

    # Crucial for Pydantic V2 serialization when User objects are returned directly or nested
    model_config = ConfigDict(from_attributes=True)


class UserCreate(SQLModel):
    name: str
    email: str
    password: str
    is_active: Optional[bool] = True
    is_superuser: Optional[bool] = False


class UserUpdate(SQLModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None


class Customer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    is_archived: bool = Field(default=False)

    projects: List["Project"] = Relationship(back_populates="customer")
    invoices: List["Invoice"] = Relationship(back_populates="customer")

    # Crucial for Pydantic V2 serialization
    model_config = ConfigDict(from_attributes=True)


class CustomerUpdate(SQLModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    is_archived: Optional[bool] = None


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    customer_id: int = Field(foreign_key="customer.id")
    project_type: Optional[ProjectType] = Field(sa_column=Column(SQLEnum(ProjectType)))
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    budget: Optional[float] = None
    budget_unit: Optional[BudgetUnit] = Field(sa_column=Column(SQLEnum(BudgetUnit)))
    rate_type: Optional[RateType] = Field(default=RateType.PROJECT)
    project_rate: Optional[float] = None
    description: Optional[str] = None
    is_archived: bool = Field(default=False)

    customer: Optional[Customer] = Relationship(back_populates="projects")
    tasks: List["Task"] = Relationship(back_populates="project")
    time_entries: List["TimeEntry"] = Relationship(back_populates="project")
    invoices: List["Invoice"] = Relationship(back_populates="project")

    # Crucial for Pydantic V2 serialization
    model_config = ConfigDict(from_attributes=True)


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    project_id: int = Field(foreign_key="project.id")
    task_rate: Optional[float] = None  # Rate if RateType is TASK

    project: Optional[Project] = Relationship(back_populates="tasks")
    time_entries: List["TimeEntry"] = Relationship(back_populates="task")

    # Crucial for Pydantic V2 serialization
    model_config = ConfigDict(from_attributes=True)


class TaskCreate(SQLModel):
    name: str
    task_rate: Optional[float] = None


class ProjectCreate(SQLModel):
    name: str
    customer_id: int
    project_type: Optional[ProjectType] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    budget: Optional[float] = None
    budget_unit: Optional[BudgetUnit] = None
    rate_type: Optional[RateType] = RateType.PROJECT
    project_rate: Optional[float] = None
    description: Optional[str] = None
    is_archived: bool = False
    tasks: List[TaskCreate] = []


class TaskUpdate(SQLModel):
    id: Optional[int] = None
    name: Optional[str] = None
    task_rate: Optional[float] = None


class ProjectUpdate(SQLModel):
    name: Optional[str] = None
    customer_id: Optional[int] = None
    project_type: Optional[ProjectType] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    budget: Optional[float] = None
    budget_unit: Optional[BudgetUnit] = None
    rate_type: Optional[RateType] = None
    project_rate: Optional[float] = None
    description: Optional[str] = None
    is_archived: Optional[bool] = None
    tasks: Optional[List[TaskUpdate]] = None


class ProjectReadWithTasks(SQLModel):
    id: int
    name: str
    customer_id: int
    project_type: Optional[ProjectType] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    budget: Optional[float] = None
    budget_unit: Optional[BudgetUnit] = None
    rate_type: Optional[RateType] = None
    project_rate: Optional[float] = None
    description: Optional[str] = None
    is_archived: bool

    tasks: List[Task] = []

    model_config = ConfigDict(from_attributes=True)


class ProjectUpdateRequest(SQLModel):
    project_data: ProjectUpdate
    tasks_json: Optional[str] = None


class TimeEntryInvoiceLink(SQLModel, table=True):
    invoice_id: Optional[int] = Field(default=None, foreign_key="invoice.id", primary_key=True)
    time_entry_id: Optional[int] = Field(default=None, foreign_key="timeentry.id", primary_key=True)


class TimeEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id")
    task_id: int = Field(foreign_key="task.id")
    user_id: int = Field(foreign_key="user.id")
    date: dtdate = Field(default=dtdate.today())
    hours: Optional[float] = None
    notes: Optional[str] = None

    project: Optional[Project] = Relationship(back_populates="time_entries")
    task: Optional[Task] = Relationship(back_populates="time_entries")
    user: Optional["User"] = Relationship(back_populates="time_entries")
    invoices: List["Invoice"] = Relationship(back_populates="time_entries", link_model=TimeEntryInvoiceLink)

    # Crucial for Pydantic V2 serialization
    model_config = ConfigDict(from_attributes=True)


class TimeEntryCreate(SQLModel):
    date: dtdate
    project_id: int
    task_id: int
    hours: float
    notes: Optional[str] = None
    user_id: int


class TimeEntryUpdate(SQLModel):
    date: Optional[dtdate] = None
    project_id: Optional[int] = None
    task_id: Optional[int] = None
    hours: Optional[float] = None
    notes: Optional[str] = None
    user_id: Optional[int] = None


class Invoice(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    record_number: str = Field(unique=True, index=True)
    customer_id: int = Field(foreign_key="customer.id")
    project_id: Optional[int] = Field(default=None, foreign_key="project.id")
    invoice_date: dtdate
    due_date: dtdate
    total_amount: float
    status: str = Field(default="draft")
    notes: Optional[str] = None
    po_number: Optional[str] = None
    time_entries: List["TimeEntry"] = Relationship(back_populates="invoices", link_model=TimeEntryInvoiceLink)
    customer: Optional[Customer] = Relationship(back_populates="invoices")
    project: Optional[Project] = Relationship(back_populates="invoices")

    # Crucial for Pydantic V2 serialization
    model_config = ConfigDict(from_attributes=True)


# New Pydantic models for Invoice creation and update
class InvoiceCreate(SQLModel):
    record_number: Optional[str] = None  # Made optional for auto-generation
    customer_id: int
    invoice_date: dtdate
    due_date: dtdate
    project_id: Optional[int] = None
    notes: Optional[str] = None
    po_number: Optional[str] = None
    time_entry_ids: List[int] = []


class InvoiceUpdate(SQLModel):
    record_number: Optional[str] = None
    customer_id: Optional[int] = None
    invoice_date: Optional[dtdate] = None
    due_date: Optional[dtdate] = None
    total_amount: Optional[float] = None  # Will be recalculated on backend
    status: Optional[str] = None
    notes: Optional[str] = None
    po_number: Optional[str] = None
    time_entry_ids: Optional[List[int]] = None  # NEW: Allow updating linked time entries


# --- Read Models for API Responses (to ensure nested data is included) ---
# These are essential for FastAPI to correctly serialize nested relationships
# when returning data from API endpoints.


class ProjectReadForTimeEntry(SQLModel):
    id: int
    name: str
    rate_type: Optional[RateType]
    project_rate: Optional[float]
    model_config = ConfigDict(from_attributes=True)


class TaskReadForTimeEntry(SQLModel):
    id: int
    name: str
    task_rate: Optional[float]
    model_config = ConfigDict(from_attributes=True)


class UserReadForTimeEntry(SQLModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


# Explicitly defined: Read model for TimeEntry that includes its Project, Task, User but NOT Invoices,
# typically used when a time entry is nested within an invoice.
class TimeEntryReadForInvoice(SQLModel):
    id: int
    date: dtdate
    hours: Optional[float]
    notes: Optional[str]
    project_id: int
    task_id: int
    user_id: int

    project: Optional[ProjectReadForTimeEntry]
    task: Optional[TaskReadForTimeEntry]
    user: Optional[UserReadForTimeEntry]

    model_config = ConfigDict(from_attributes=True)


# NEW: Read model for TimeEntry that includes its Invoice relationships
class InvoiceReadForTimeEntry(SQLModel):
    id: int
    record_number: str
    model_config = ConfigDict(from_attributes=True)


class TimeEntryReadWithRelations(SQLModel):
    id: int
    date: dtdate
    hours: Optional[float]
    notes: Optional[str]
    project_id: int
    task_id: int
    user_id: int

    project: Optional[ProjectReadForTimeEntry]
    task: Optional[TaskReadForTimeEntry]
    user: Optional[UserReadForTimeEntry]
    invoices: List[InvoiceReadForTimeEntry] = []  # Include invoices to check status

    model_config = ConfigDict(from_attributes=True)


class CustomerReadForInvoice(SQLModel):
    id: int
    name: str
    # NEW: Add contact information fields
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# NEW: ProjectReadWithCustomer to include customer details for dropdowns
class ProjectReadWithCustomer(SQLModel):
    id: int
    name: str
    customer_id: int
    customer: Optional[CustomerReadForInvoice]  # Include customer for display
    project_type: Optional[ProjectType]
    rate_type: Optional[RateType]
    project_rate: Optional[float]
    tasks: List[Task] = []  # Include tasks for finding task rate if needed
    model_config = ConfigDict(from_attributes=True)


class InvoiceRead(SQLModel):
    id: int
    record_number: str
    customer_id: int
    project_id: Optional[int]
    invoice_date: dtdate
    due_date: dtdate
    total_amount: float
    status: str
    notes: Optional[str]
    po_number: Optional[str]

    customer: Optional[CustomerReadForInvoice]
    project: Optional[ProjectReadForTimeEntry]  # Can reuse ProjectReadForTimeEntry
    time_entries: List[TimeEntryReadForInvoice]  # This uses TimeEntryReadForInvoice

    model_config = ConfigDict(from_attributes=True)


# NEW: Models for grouped time entries response (for time_entries.html)
class GroupedTimeEntry(SQLModel):
    id: int
    date: dtdate
    hours: float
    notes: Optional[str]
    user_name: str
    project_name: str
    task_name: str
    entry_rate_type: Optional[RateType]
    entry_rate: Optional[float]
    entry_dollars: float
    project_id: int
    invoices: List[InvoiceReadForTimeEntry] = []  # Crucial for lock icon
    model_config = ConfigDict(from_attributes=True)


class GroupedTask(SQLModel):
    name: str
    total_hours: float
    total_dollars: float
    entries: List[GroupedTimeEntry]
    model_config = ConfigDict(from_attributes=True)


class GroupedProject(SQLModel):
    name: str
    total_hours: float
    total_dollars: float
    tasks: List[GroupedTask]
    model_config = ConfigDict(from_attributes=True)


class GroupedCustomer(SQLModel):
    name: str
    total_hours: float
    total_dollars: float
    projects: List[GroupedProject]
    model_config = ConfigDict(from_attributes=True)


class GroupedTimeEntriesResponse(SQLModel):
    grand_total_hours: float
    grand_total_dollars: float
    grouped_time_entries: List[GroupedCustomer]
    model_config = ConfigDict(from_attributes=True)
