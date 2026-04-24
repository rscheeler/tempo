from typing import List, Optional, Dict, Any
from datetime import date, datetime
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from sqlalchemy import func

from ..db.models import (
    Invoice,
    InvoiceCreate,
    InvoiceUpdate,
    TimeEntry,
    Customer,
    Project,
    Task,
    TimeEntryInvoiceLink,
    RateType,
    InvoiceRead,
    TimeEntryReadForInvoice,
    ProjectReadForTimeEntry,
    TaskReadForTimeEntry,
    UserReadForTimeEntry,
    CustomerReadForInvoice,
)
from ..db.database import get_session
from ..db.utils import generate_record_number

# Ensure the APIRouter is correctly defined with a prefix and tags
invoices_router = APIRouter(
    prefix="/api/invoices",
    tags=["invoices"],
    responses={404: {"description": "Invoice not found"}},
)


@invoices_router.get("/unbilled_entries", summary="Get Unbilled Time Entries for a Customer")
async def get_unbilled_time_entries_for_customer(
    customer_id: int = Query(..., description="ID of the customer"),
    session: Session = Depends(get_session),
) -> List[Dict[str, Any]]:
    """
    Retrieves time entries for a specific customer that have not yet been linked to an invoice.
    Includes project, task, and user details, along with calculated dollar values.
    """
    # Subquery to find time_entry_ids that are already linked to an invoice
    subquery_invoiced_ids = (
        select(TimeEntryInvoiceLink.time_entry_id)
        .where(TimeEntryInvoiceLink.time_entry_id == TimeEntry.id)
        .correlate(TimeEntry)  # Correlate with the outer query's TimeEntry
        .exists()
    )

    # Main query to select unbilled time entries for the given customer
    unbilled_entries_query = (
        select(TimeEntry)
        .options(
            selectinload(TimeEntry.project).selectinload(Project.customer),
            selectinload(TimeEntry.user),
            selectinload(TimeEntry.task),
        )
        .join(TimeEntry.project)  # Ensure project is joined to filter by customer_id
        .where(
            Project.customer_id == customer_id,
            ~subquery_invoiced_ids,  # Filter out entries that are already invoiced
        )
        .order_by(TimeEntry.date, TimeEntry.id)  # Order for consistent display
    )

    unbilled_entries = session.exec(unbilled_entries_query).all()

    result = []
    for entry in unbilled_entries:
        entry_dollars = 0.0
        entry_rate = None
        entry_rate_type = None

        if entry.hours is not None:
            if (
                entry.project
                and entry.project.rate_type == RateType.PROJECT
                and entry.project.project_rate is not None
            ):
                entry_dollars = entry.hours * entry.project.project_rate
                entry_rate = entry.project.project_rate
                entry_rate_type = RateType.PROJECT.value
            elif (
                entry.task
                and entry.project.rate_type == RateType.TASK
                and entry.task.task_rate is not None
            ):
                entry_dollars = entry.hours * entry.task.task_rate
                entry_rate = entry.task.task_rate
                entry_rate_type = RateType.TASK.value

        result.append(
            {
                "id": entry.id,
                "date": entry.date.strftime("%Y-%m-%d"),
                "hours": entry.hours,
                "notes": entry.notes,
                "user_id": entry.user_id,
                "user_name": getattr(entry.user, "name", "N/A") if entry.user else "N/A",
                "project_id": entry.project_id,
                "project_name": entry.project.name if entry.project else "N/A",
                "task_id": entry.task_id,
                "task_name": entry.task.name if entry.task else "N/A",
                "entry_dollars": entry_dollars,
                "entry_rate": entry_rate,
                "entry_rate_type": entry_rate_type,
                "customer_id": entry.project.customer_id
                if entry.project and entry.project.customer
                else None,
                "customer_name": entry.project.customer.name
                if entry.project and entry.project.customer
                else "N/A",
            }
        )
    return result


@invoices_router.get("/for-quickbooks")
def get_invoices_for_quickbooks(session: Session = Depends(get_session)) -> List[Dict[str, Any]]:
    """
    Fetches all invoices and formats the data for a QuickBooks CSV export.
    This endpoint is designed to provide the frontend with all the necessary
    data in a structured way to generate the report. It now provides a line
    item for each individual time entry, consistent with the application's UI.
    """
    invoices = session.exec(
        select(Invoice)
        .options(selectinload(Invoice.customer))
        .options(selectinload(Invoice.project))
        .options(selectinload(Invoice.time_entries).selectinload(TimeEntry.user))
        .options(selectinload(Invoice.time_entries).selectinload(TimeEntry.project))
        .options(selectinload(Invoice.time_entries).selectinload(TimeEntry.task))
    ).all()

    quickbooks_invoices = []
    for invoice in invoices:
        # Group time entries by project and then by task, aggregating hours and dollars
        grouped_by_project = defaultdict(
            lambda: defaultdict(lambda: {"hours": 0.0, "dollars": 0.0, "rate": None})
        )

        for item in invoice.time_entries:
            project_name = item.project.name if item.project else "Unassigned Project"
            task_name = item.task.name if item.task else "Unassigned Task"

            # Calculate entry rate and dollars
            entry_dollars = 0.0
            entry_rate = None
            if item.hours is not None and item.project:
                if (
                    item.project.rate_type == RateType.PROJECT
                    and item.project.project_rate is not None
                ):
                    entry_dollars = item.hours * item.project.project_rate
                    entry_rate = item.project.project_rate
                elif (
                    item.task
                    and item.project.rate_type == RateType.TASK
                    and item.task.task_rate is not None
                ):
                    entry_dollars = item.hours * item.task.task_rate
                    entry_rate = item.task.task_rate

            grouped_by_project[project_name][task_name]["hours"] += (
                item.hours if item.hours else 0.0
            )
            grouped_by_project[project_name][task_name]["dollars"] += entry_dollars
            grouped_by_project[project_name][task_name]["rate"] = (
                entry_rate  # Assuming rate is consistent per task
            )

        line_items = []
        for project_name, tasks in grouped_by_project.items():
            for task_name, data in tasks.items():
                line_item = {
                    "item": project_name,
                    "description": task_name,
                    "quantity": data["hours"],
                    "rate": data["rate"],
                    "itemAmount": data["dollars"],
                }
                line_items.append(line_item)

        # Safely access attributes on the invoice
        quickbooks_invoice = {
            "invoiceNo": invoice.record_number,
            "invoiceDate": invoice.invoice_date.isoformat(),
            "dueDate": invoice.due_date.isoformat(),
            "customer": invoice.customer.name if invoice.customer else "N/A",
            "memo": "Invoice for services rendered",
            "lineItems": line_items,
        }
        quickbooks_invoices.append(quickbooks_invoice)

    return quickbooks_invoices


@invoices_router.post(
    "/", response_model=Invoice, status_code=status.HTTP_201_CREATED, summary="Create a new Invoice"
)
async def create_invoice(
    invoice_create: InvoiceCreate, session: Session = Depends(get_session)
) -> Invoice:
    """
    Creates a new invoice and links specified time entries to it.
    Calculates the total_amount based on the linked time entries.
    Automatically generates the record_number if not provided.
    """
    if not invoice_create.time_entry_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one time entry ID must be provided to create an invoice.",
        )

    # Fetch the time entries to be invoiced to calculate total_amount
    selected_time_entries_query = (
        select(TimeEntry)
        .options(selectinload(TimeEntry.project), selectinload(TimeEntry.task))
        .where(TimeEntry.id.in_(invoice_create.time_entry_ids))
    )
    selected_time_entries = session.exec(selected_time_entries_query).all()

    if not selected_time_entries:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No valid time entries found for the provided IDs.",
        )

    calculated_total_amount = 0.0
    for entry in selected_time_entries:
        entry_dollars = 0.0
        if entry.hours is not None:
            if (
                entry.project
                and entry.project.rate_type == RateType.PROJECT
                and entry.project.project_rate is not None
            ):
                entry_dollars = entry.hours * entry.project.project_rate
            elif (
                entry.task
                and entry.project.rate_type == RateType.TASK
                and entry.task.task_rate is not None
            ):
                entry_dollars = entry.hours * entry.task.task_rate
        calculated_total_amount += entry_dollars

    # Generate record_number if not provided
    if not invoice_create.record_number:
        generated_record_number = generate_record_number(session, invoice_create.invoice_date)
    else:
        generated_record_number = invoice_create.record_number

    # Create the Invoice object
    db_invoice = Invoice(
        record_number=generated_record_number,
        customer_id=invoice_create.customer_id,
        project_id=invoice_create.project_id,  # Can be None
        invoice_date=invoice_create.invoice_date,
        due_date=invoice_create.due_date,
        total_amount=calculated_total_amount,  # Use calculated amount
        status="draft",  # Default status to draft
        notes=invoice_create.notes,
        po_number=invoice_create.po_number,
    )

    session.add(db_invoice)
    session.flush()  # Flush to get the db_invoice.id before committing

    # Link time entries to the new invoice
    for entry in selected_time_entries:
        link = TimeEntryInvoiceLink(invoice_id=db_invoice.id, time_entry_id=entry.id)
        session.add(link)

    session.commit()
    session.refresh(db_invoice)

    # Load relationships for the response model for the return value
    db_invoice = session.exec(
        select(Invoice)
        .options(
            selectinload(Invoice.customer),
            selectinload(Invoice.project),
            selectinload(Invoice.time_entries).selectinload(TimeEntry.project),
            selectinload(Invoice.time_entries).selectinload(TimeEntry.task),
            selectinload(Invoice.time_entries).selectinload(TimeEntry.user),
        )
        .where(Invoice.id == db_invoice.id)
    ).first()

    return db_invoice


@invoices_router.get("/", response_model=List[InvoiceRead], summary="Get all Invoices")
async def get_all_invoices(session: Session = Depends(get_session)) -> List[InvoiceRead]:
    """Retrieves a list of all invoices."""
    invoices = session.exec(
        select(Invoice).options(
            selectinload(Invoice.customer),
            selectinload(Invoice.project),
            selectinload(Invoice.time_entries).selectinload(
                TimeEntry.project
            ),  # Load project for each time entry
            selectinload(Invoice.time_entries).selectinload(
                TimeEntry.task
            ),  # Load task for each time entry
            selectinload(Invoice.time_entries).selectinload(
                TimeEntry.user
            ),  # Load user for each time entry
        )
    ).all()
    return invoices


@invoices_router.get("/{invoice_id}", response_model=InvoiceRead, summary="Get Invoice by ID")
async def get_invoice_by_id(
    invoice_id: int, session: Session = Depends(get_session)
) -> InvoiceRead:
    """Retrieves a single invoice by its ID."""
    invoice = session.exec(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .options(
            selectinload(Invoice.customer),
            selectinload(Invoice.project),
            selectinload(Invoice.time_entries).selectinload(
                TimeEntry.project
            ),  # Load project for each time entry
            selectinload(Invoice.time_entries).selectinload(
                TimeEntry.task
            ),  # Load task for each time entry
            selectinload(Invoice.time_entries).selectinload(
                TimeEntry.user
            ),  # Load user for each time entry
        )
    ).first()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice


@invoices_router.put(
    "/{invoice_id}", response_model=Invoice, summary="Update an Invoice", name="update_invoice"
)
async def update_invoice(
    invoice_id: int, invoice_update: InvoiceUpdate, session: Session = Depends(get_session)
) -> Invoice:
    """
    Updates an existing invoice's information and its linked time entries.
    Recalculates total_amount based on the new set of linked time entries.
    Allows status changes, with special handling for 'void' status.
    """
    invoice = session.exec(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .options(selectinload(Invoice.time_entries))  # Eager load current time entries
    ).first()

    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    update_data = invoice_update.model_dump(exclude_unset=True)

    # Special handling for status updates
    new_status = update_data.get("status")
    current_status = invoice.status

    # If the status is being changed to 'void'
    if new_status == "void" and current_status != "void":
        # Delete all associated TimeEntryInvoiceLink entries to free up time entries
        links_to_delete = session.exec(
            select(TimeEntryInvoiceLink).where(TimeEntryInvoiceLink.invoice_id == invoice_id)
        ).all()
        for link in links_to_delete:
            session.delete(link)
        # Set total_amount to 0 for voided invoices
        invoice.total_amount = 0.0
        setattr(invoice, "status", new_status)  # Update status to void
        session.add(invoice)  # Add updated invoice to session
        session.commit()  # Commit status and unlinking changes
        session.refresh(invoice)  # Refresh to get the latest state

        # Re-load relationships for the response model for the return value
        db_invoice = session.exec(
            select(Invoice)
            .options(
                selectinload(Invoice.customer),
                selectinload(Invoice.project),
                selectinload(Invoice.time_entries).selectinload(TimeEntry.project),
                selectinload(Invoice.time_entries).selectinload(TimeEntry.task),
                selectinload(Invoice.time_entries).selectinload(TimeEntry.user),
            )
            .where(Invoice.id == invoice_id)
        ).first()
        return db_invoice  # Return early for void action

    # If status is not 'draft' and the update is not *just* a status change to 'void'
    # (i.e., attempting to change other fields or status to non-void/non-draft)
    if current_status != "draft":
        # Allow only status change to 'sent' or 'paid' if not already 'void'
        if (
            new_status
            and new_status != current_status
            and new_status in ["sent", "paid"]
            and current_status != "void"
        ):
            setattr(invoice, "status", new_status)
            session.add(invoice)
            session.commit()
            session.refresh(invoice)
            # Re-load relationships for the response model for the return value
            db_invoice = session.exec(
                select(Invoice)
                .options(
                    selectinload(Invoice.customer),
                    selectinload(Invoice.project),
                    selectinload(Invoice.time_entries).selectinload(TimeEntry.project),
                    selectinload(Invoice.time_entries).selectinload(TimeEntry.task),
                    selectinload(Invoice.time_entries).selectinload(TimeEntry.user),
                )
                .where(Invoice.id == invoice_id)
            ).first()
            return db_invoice
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invoice cannot be updated. Current status is '{current_status}'. Only 'draft' invoices can be fully edited, or status can be changed to 'sent'/'paid'.",
            )

    # If we reach here, the invoice is in 'draft' status, so allow full editing
    # Remove time_entry_ids from update_data to handle separately
    new_time_entry_ids = update_data.pop("time_entry_ids", None)

    for key, value in update_data.items():
        setattr(invoice, key, value)

    # --- Handle time_entry_ids update (only for draft invoices) ---
    if new_time_entry_ids is not None:  # Only proceed if time_entry_ids were provided in the update
        current_linked_ids = {te.id for te in invoice.time_entries}
        new_linked_ids = set(new_time_entry_ids)

        # Find entries to unlink
        entries_to_unlink_ids = current_linked_ids - new_linked_ids
        for entry_id in entries_to_unlink_ids:
            link_to_delete = session.exec(
                select(TimeEntryInvoiceLink).where(
                    TimeEntryInvoiceLink.invoice_id == invoice_id,
                    TimeEntryInvoiceLink.time_entry_id == entry_id,
                )
            ).first()
            if link_to_delete:
                session.delete(link_to_delete)

        # Find entries to link
        entries_to_link_ids = new_linked_ids - current_linked_ids
        for entry_id in entries_to_link_ids:
            link_to_add = TimeEntryInvoiceLink(invoice_id=invoice_id, time_entry_id=entry_id)
            session.add(link_to_add)

        # Recalculate total_amount based on the new set of linked time entries
        # Fetch the *final* set of linked time entries after linking/unlinking
        final_linked_entries_query = (
            select(TimeEntry)
            .options(selectinload(TimeEntry.project), selectinload(TimeEntry.task))
            .join(TimeEntryInvoiceLink)
            .where(TimeEntryInvoiceLink.invoice_id == invoice_id)
        )
        final_linked_entries = session.exec(final_linked_entries_query).all()

        calculated_total_amount = 0.0
        for entry in final_linked_entries:
            entry_dollars = 0.0
            if entry.hours is not None:
                if (
                    entry.project
                    and entry.project.rate_type == RateType.PROJECT
                    and entry.project.project_rate is not None
                ):
                    entry_dollars = entry.hours * entry.project.project_rate
                elif (
                    entry.task
                    and entry.project.rate_type == RateType.TASK
                    and entry.task.task_rate is not None
                ):
                    entry_dollars = entry.hours * entry.task.task_rate
            calculated_total_amount += entry_dollars

        invoice.total_amount = calculated_total_amount  # Update the invoice's total amount

    session.add(invoice)
    session.commit()
    session.refresh(invoice)

    # Re-load relationships for the response model for the return value
    # This ensures the returned Invoice object has the updated time_entries list
    db_invoice = session.exec(
        select(Invoice)
        .options(
            selectinload(Invoice.customer),
            selectinload(Invoice.project),
            selectinload(Invoice.time_entries).selectinload(TimeEntry.project),
            selectinload(Invoice.time_entries).selectinload(TimeEntry.task),
            selectinload(Invoice.time_entries).selectinload(TimeEntry.user),
        )
        .where(Invoice.id == invoice_id)
    ).first()

    return db_invoice


@invoices_router.delete(
    "/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an Invoice"
)
async def delete_invoice(invoice_id: int, session: Session = Depends(get_session)):
    """
    Deletes an invoice from the database and unlinks its time entries.
    Only allows deletion if the invoice status is 'draft'.
    """
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    # Check invoice status before allowing deletion
    if invoice.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invoice cannot be deleted. Current status is '{invoice.status}'. Only 'draft' invoices can be deleted.",
        )

    # Delete all associated TimeEntryInvoiceLink entries first
    links = session.exec(
        select(TimeEntryInvoiceLink).where(TimeEntryInvoiceLink.invoice_id == invoice_id)
    ).all()
    for link in links:
        session.delete(link)

    session.delete(invoice)
    session.commit()
    return {
        "message": "Invoice deleted successfully."
    }  # Return a message since 204 No Content typically has no body
