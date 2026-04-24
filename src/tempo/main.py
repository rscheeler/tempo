import json  # Import json module

from contextlib import asynccontextmanager
from datetime import datetime, date, timedelta
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, Request, Depends, Query, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload

from .db.models import (
    User,
    TimeEntry,
    Project,
    Task,
    Customer,
    ProjectType,
    RateType,
    BudgetUnit,
    Invoice,
    # Import Read models for serialization
    InvoiceRead,
    CustomerReadForInvoice,
    ProjectReadForTimeEntry,
    UserReadForTimeEntry,
    ProjectReadWithCustomer,
)
from .db.config import settings
from .db.database import create_db_and_tables, get_session

from .routers.users import users_router
from .routers.time_entries import time_entries_router
from .routers.customers import customers_router
from .routers.projects import projects_router, get_all_projects
from .routers.tasks import tasks_router
from .routers.invoices import invoices_router

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Context manager for application startup and shutdown events.
    Ensures database tables are created on startup.
    """
    create_db_and_tables()
    yield


# --- FastAPI App Initialization ---
app = FastAPI(
    title="Tempo Time Keeping App",
    description="A simple time keeping application built with FastAPI and SQLModel.",
    version="0.1.0",
    lifespan=lifespan,
)
# Mount static files (CSS, JS, images)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
# --- Jinja2 Templates Configuration ---
templates = Jinja2Templates(directory=BASE_DIR / "templates")
# Load global variables into Jinja2 environment from settings
templates.env.globals["companyname"] = settings.COMPANY_NAME
templates.env.globals["companyaddress"] = settings.COMPANY_ADDRESS
templates.env.globals["companyphone"] = settings.COMPANY_PHONE
templates.env.globals["billingemail"] = settings.BILLING_EMAIL
templates.env.globals["logo"] = settings.LOGO
templates.env.globals["favicon"] = settings.FAVICON


# Jinja2 custom filter for datetime formatting
def format_datetime(value, format="%Y-%m-%d"):
    """Formats a datetime object or 'now' string into a specified string format."""
    if isinstance(value, datetime) or isinstance(value, date):
        return value.strftime(format)
    elif value == "now":
        return datetime.now().strftime(format)
    return str(value)


templates.env.filters["date"] = format_datetime


# Jinja2 custom filter for currency formatting
def format_currency(value):
    """Formats a numeric value as currency with two decimal places."""
    if value is None:
        return None
    # Ensure value is a float before formatting to prevent TypeError
    try:
        return f"{float(value):.2f}"
    except (ValueError, TypeError):
        return None  # Return None if cannot convert to float


templates.env.filters["currency"] = format_currency


# NEW: Jinja2 custom filter for newline to break
def nl2br(value):
    """Converts newline characters to HTML <br> tags."""
    if value is None:
        return ""
    return value.replace("\n", "<br>")


templates.env.filters["nl2br"] = nl2br


# Custom JSON encoder for date and datetime objects
def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError("Type %s not serializable" % type(obj))


# --- HTML Endpoints ---
# Pass request.url_for to the template context for all HTML endpoints


@app.get("/", response_class=HTMLResponse, summary="Home Page")
async def read_root(request: Request):
    """Renders the main index page."""
    return templates.TemplateResponse(
        "index.html", {"request": request, "title": "Home", "url_for": request.url_for}
    )


@app.get("/users", response_class=HTMLResponse, summary="Users Management Page")
async def read_users_page(request: Request, session: Session = Depends(get_session)):
    """Renders the users management page and fetches all users."""
    users = session.exec(select(User)).all()
    return templates.TemplateResponse(
        "users.html",
        {"request": request, "users": users, "title": "Manage Users", "url_for": request.url_for},
    )


@app.get("/time_entries", response_class=HTMLResponse, summary="Time Entries Management Page")
async def read_time_entries_page(
    request: Request,
    start_date_str: Optional[str] = Query(None, alias="start_date"),
    end_date_str: Optional[str] = Query(None, alias="end_date"),
):
    """
    Renders the time entries management page.
    Passes the current week's start and end dates to the template for client-side fetching.
    """
    if start_date_str and end_date_str:
        try:
            start_of_week = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_of_week = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            today = date.today()
            start_of_week = today - timedelta(days=today.weekday())
            end_of_week = start_of_week + timedelta(days=6)
    else:
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

    # Calculate dates for previous and next weeks for navigation
    previous_week_start = start_of_week - timedelta(weeks=1)
    previous_week_end = end_of_week - timedelta(weeks=1)
    next_week_start = start_of_week + timedelta(weeks=1)
    next_week_end = end_of_week + timedelta(weeks=1)

    return templates.TemplateResponse(
        "time_entries.html",
        {
            "request": request,
            "start_of_week": start_of_week,
            "end_of_week": end_of_week,
            "previous_week_start": previous_week_start,
            "previous_week_end": previous_week_end,
            "next_week_start": next_week_start,
            "next_week_end": next_week_end,
            "title": "Weekly Time Entries",
            "url_for": request.url_for,
        },
    )


@app.get("/customers", response_class=HTMLResponse, summary="Customers Management Page")
async def read_customers_page(
    request: Request,
    session: Session = Depends(get_session),
    show_archived: bool = Query(False, description="Include archived customers in the list"),
):
    query = select(Customer)
    if not show_archived:
        query = query.where(Customer.is_archived == False)
    customers = session.exec(query).all()
    return templates.TemplateResponse(
        "customers.html",
        {
            "request": request,
            "customers": customers,
            "title": "Manage Customers",
            "url_for": request.url_for,
        },
    )


@app.get("/projects", response_class=HTMLResponse, summary="Projects Management Page")
async def read_projects_page(
    request: Request,
    session: Session = Depends(get_session),
    customer_id: Optional[int] = Query(
        None, description="Filter projects by customer ID"
    ),  # Add customer_id parameter here
    show_archived: bool = Query(False, description="Include archived projects in the list"),
):
    """Renders the projects management page and fetches all projects with charged amounts."""
    # Call the API endpoint from projects_router to get projects with calculated charged amounts
    # Pass the customer_id directly to get_all_projects
    projects = await get_all_projects(
        session=session, customer_id=customer_id, show_archived=show_archived
    )

    return templates.TemplateResponse(
        "projects.html",
        {
            "request": request,
            "projects": projects,
            "title": "Manage Projects",
            "url_for": request.url_for,
        },
    )


@app.get("/invoices", response_class=HTMLResponse, summary="Invoices Management Page")
async def read_invoices_page(request: Request):
    """Renders the invoicing management page."""
    return templates.TemplateResponse(
        "invoices.html",
        {"request": request, "title": "Manage Invoices", "url_for": request.url_for},
    )


# HTML endpoint for Invoice detail page
@app.get("/invoices/view/{invoice_id}", response_class=HTMLResponse, summary="Invoice Detail Page")
async def read_invoice_detail_page(
    request: Request, invoice_id: int, session: Session = Depends(get_session)
):
    """Renders a detailed view of a single invoice."""
    invoice = session.exec(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .options(
            selectinload(Invoice.customer),
            selectinload(Invoice.project),
            selectinload(Invoice.time_entries).selectinload(TimeEntry.project),
            selectinload(Invoice.time_entries).selectinload(TimeEntry.task),
            selectinload(Invoice.time_entries).selectinload(TimeEntry.user),
        )
    ).first()

    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    # --- Aggregation Logic (from previous step) ---
    aggregated_time_entries = {}  # Key: (project_id, task_id)

    for entry in invoice.time_entries:
        project_id = entry.project.id if entry.project else None
        task_id = entry.task.id if entry.task else None

        # Use a tuple as the key for unique project-task combinations
        item_key = (project_id, task_id)

        # Calculate rate and amount for the individual entry
        entry_rate = 0.0
        if entry.hours is not None:
            if (
                entry.project
                and entry.project.rate_type == RateType.PROJECT
                and entry.project.project_rate is not None
            ):
                entry_rate = entry.project.project_rate
            elif (
                entry.task
                and entry.project
                and entry.project.rate_type == RateType.TASK
                and entry.task.task_rate is not None
            ):
                entry_rate = entry.task.task_rate

        entry_amount = (entry.hours or 0) * entry_rate

        if item_key not in aggregated_time_entries:
            aggregated_time_entries[item_key] = {
                "project_name": entry.project.name if entry.project else "N/A",
                "task_name": entry.task.name if entry.task else "N/A",
                "quantity_hours": 0.0,
                "rate": entry_rate,  # Store the rate from the first entry for this task
                "total_amount": 0.0,
            }

        aggregated_time_entries[item_key]["quantity_hours"] += entry.hours or 0
        aggregated_time_entries[item_key]["total_amount"] += entry_amount

    invoice_items = list(aggregated_time_entries.values())
    # --- END Aggregation Logic ---

    # --- Prepare invoice data for JSON serialization, including calculated rates and totals for time entries ---
    # Convert the invoice object to a dictionary first
    invoice_data_for_json = InvoiceRead.model_validate(invoice).model_dump()

    # Create a new list for time entries to add calculated fields
    updated_time_entries = []
    for entry_dict in invoice_data_for_json["time_entries"]:
        # Get the corresponding original SQLModel TimeEntry object to access its relationships
        original_entry = next((e for e in invoice.time_entries if e.id == entry_dict["id"]), None)

        if original_entry:
            calculated_entry_rate = 0.0
            if original_entry.hours is not None:
                if (
                    original_entry.project
                    and original_entry.project.rate_type == RateType.PROJECT
                    and original_entry.project.project_rate is not None
                ):
                    calculated_entry_rate = original_entry.project.project_rate
                elif (
                    original_entry.task
                    and original_entry.project  # Need project to check rate_type
                    and original_entry.project.rate_type == RateType.TASK
                    and original_entry.task.task_rate is not None
                ):
                    calculated_entry_rate = original_entry.task.task_rate
            calculated_entry_dollars = (original_entry.hours or 0) * calculated_entry_rate

            # Add these calculated fields to the dictionary representation of the time entry
            entry_dict["entry_rate"] = calculated_entry_rate
            entry_dict["entry_dollars"] = calculated_entry_dollars

        updated_time_entries.append(entry_dict)

    invoice_data_for_json["time_entries"] = updated_time_entries
    # Use the custom json_serial function for default handling of date and datetime objects
    invoice_json_string = json.dumps(invoice_data_for_json, default=json_serial)

    # Fetch and convert customers for the dropdown
    customers_db = session.exec(select(Customer).where(Customer.is_archived == False)).all()
    # Convert list of Pydantic models to list of dictionaries, then to JSON string
    customers_for_template_dicts = [
        CustomerReadForInvoice.model_validate(c).model_dump() for c in customers_db
    ]
    customers_json_string = json.dumps(customers_for_template_dicts)

    # Fetch and convert projects for the dropdown, ensuring customer and tasks are loaded
    projects_db = session.exec(
        select(Project)
        .where(Project.is_archived == False)
        .options(selectinload(Project.customer), selectinload(Project.tasks))
    ).all()
    # Convert list of Pydantic models to list of dictionaries, then to JSON string
    projects_for_template_dicts = [
        ProjectReadWithCustomer.model_validate(p).model_dump() for p in projects_db
    ]
    projects_json_string = json.dumps(projects_for_template_dicts)

    # Fetch and convert users for the dropdown
    users_db = session.exec(select(User)).all()
    # Convert list of Pydantic models to list of dictionaries, then to JSON string
    users_for_template_dicts = [
        UserReadForTimeEntry.model_validate(u).model_dump() for u in users_db
    ]
    users_json_string = json.dumps(users_for_template_dicts)

    invoice_statuses = ["draft", "sent", "paid", "void"]  # Define allowed statuses

    return templates.TemplateResponse(
        "invoice_view.html",
        {
            "request": request,
            "invoice": invoice,  # Pass the Pydantic model for direct Jinja access
            "invoice_json_string": invoice_json_string,  # NEW: Pass JSON string for JS
            "invoice_items": invoice_items,
            "customers": customers_for_template_dicts,  # Pass dictionaries for Jinja iteration (for select options)
            "customers_json_string": customers_json_string,  # NEW: Pass JSON string for JS
            "projects": projects_for_template_dicts,  # Pass dictionaries for Jinja iteration (for select options)
            "projects_json_string": projects_json_string,  # NEW: Pass JSON string for JS
            "users": users_for_template_dicts,  # Pass dictionaries for Jinja iteration (for select options)
            "users_json_string": users_json_string,  # NEW: Pass JSON string for JS
            "invoice_statuses": invoice_statuses,
            "title": f"Invoice #{invoice.record_number}",
            "url_for": request.url_for,
        },
    )


@app.get("/reports", response_class=HTMLResponse)
def read_reports_page(request: Request):
    """
    Renders the reports page.
    """
    return templates.TemplateResponse(
        "reports.html",
        {"request": request, "title": "Reports", "url_for": request.url_for},
    )


# --- Include Routers in Main App ---
app.include_router(users_router)
app.include_router(time_entries_router)
app.include_router(customers_router)
app.include_router(projects_router)
app.include_router(tasks_router)
app.include_router(invoices_router)
