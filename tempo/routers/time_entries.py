from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload

from db.models import (
    TimeEntry,
    TimeEntryCreate,
    TimeEntryUpdate,
    Project,
    User,
    Task,
    Customer,
    ProjectType,
    RateType,
    Invoice,  # Ensure Invoice is imported
    TimeEntryReadWithRelations,  # Use the new Read model for time entries with relations
    GroupedTimeEntriesResponse,
    GroupedCustomer,
    GroupedProject,
    GroupedTask,
    GroupedTimeEntry,  # Grouped response models
)
from db.database import get_session  # Import get_session from db.database.py

time_entries_router = APIRouter(
    prefix="/api/time_entries",
    tags=["time_entries"],
    responses={404: {"description": "Time Entry not found"}},
)


# IMPORTANT: Define the more specific "/grouped" route BEFORE the general "/{time_entry_id}" route
@time_entries_router.get(
    "/grouped", response_model=GroupedTimeEntriesResponse, summary="Get Grouped Time Entries for a Week"
)
async def get_grouped_time_entries(
    session: Session = Depends(get_session),
    start_date: date = Query(..., description="Start date of the week (YYYY-MM-DD)", format="date"),
    end_date: date = Query(..., description="End date of the week (YYYY-MM-DD)", format="date"),
) -> GroupedTimeEntriesResponse:  # Changed return type to GroupedTimeEntriesResponse
    """
    Retrieves time entries for a specified week,
    grouped by customer, then project, then task, with calculated hours and dollar totals.
    Includes invoice status for each time entry.
    """
    print(f"API received request for grouped time entries: start_date={start_date}, end_date={end_date}")  # Debug print

    start_of_week = start_date
    end_of_week = end_date

    # Eagerly load Project, User, Task, Customer (within Project), and INVOICES relationships
    time_entries_query = session.exec(
        select(TimeEntry)
        .options(
            selectinload(TimeEntry.project).selectinload(Project.customer),
            selectinload(TimeEntry.user),
            selectinload(TimeEntry.task),
            selectinload(TimeEntry.invoices),  # Eager load invoices for status check
        )
        .where(TimeEntry.date >= start_of_week, TimeEntry.date <= end_of_week)
        .order_by(TimeEntry.date)
    )
    time_entries = time_entries_query.all()

    grouped_data = (
        {}
    )  # {customer_id: {customer_name, total_hours, total_dollars, projects: {project_id: {project_name, ...}}}}
    grand_total_hours = 0.0
    grand_total_dollars = 0.0

    for entry in time_entries:
        customer = entry.project.customer
        project = entry.project
        task = entry.task
        user = entry.user

        # Calculate dollar value for the entry
        entry_dollars = 0.0
        entry_rate = None
        entry_rate_type = None

        if entry.hours is not None:
            if entry.project and entry.project.rate_type == RateType.PROJECT and entry.project.project_rate is not None:
                entry_dollars = entry.hours * entry.project.project_rate
                entry_rate = entry.project.project_rate
                entry_rate_type = project.rate_type.value  # Use .value for enum
            elif entry.task and entry.project.rate_type == RateType.TASK and entry.task.task_rate is not None:
                entry_dollars = entry.hours * entry.task.task_rate
                entry_rate = entry.task.task_rate
                entry_rate_type = project.rate_type.value  # Use .value for enum

        # Initialize customer group
        if customer.id not in grouped_data:  # Use customer.id for unique keys
            grouped_data[customer.id] = {
                "name": customer.name,
                "total_hours": 0.0,
                "total_dollars": 0.0,
                "projects": {},
            }

        grouped_data[customer.id]["total_hours"] += entry.hours or 0.0
        grouped_data[customer.id]["total_dollars"] += entry_dollars

        # Initialize project group
        if project.id not in grouped_data[customer.id]["projects"]:  # Use project.id for unique keys
            grouped_data[customer.id]["projects"][project.id] = {
                "name": project.name,
                "total_hours": 0.0,
                "total_dollars": 0.0,
                "tasks": {},
            }

        grouped_data[customer.id]["projects"][project.id]["total_hours"] += entry.hours or 0.0
        grouped_data[customer.id]["projects"][project.id]["total_dollars"] += entry_dollars

        # Initialize task group
        if task.id not in grouped_data[customer.id]["projects"][project.id]["tasks"]:  # Use task.id for unique keys
            grouped_data[customer.id]["projects"][project.id]["tasks"][task.id] = {
                "name": task.name,
                "total_hours": 0.0,
                "total_dollars": 0.0,
                "entries": [],
            }

        grouped_data[customer.id]["projects"][project.id]["tasks"][task.id]["total_hours"] += entry.hours or 0.0
        grouped_data[customer.id]["projects"][project.id]["tasks"][task.id]["total_dollars"] += entry_dollars

        # Add entry details and update totals
        # Create a dictionary that matches GroupedTimeEntry model
        grouped_entry = {
            "id": entry.id,
            "date": entry.date,  # Keep as date object for Pydantic, it will be formatted by frontend
            "hours": entry.hours or 0.0,
            "notes": entry.notes,
            "user_name": user.name if user else "N/A",
            "project_name": project.name if project else "N/A",
            "task_name": task.name if task else "N/A",
            "entry_rate_type": entry_rate_type,
            "entry_rate": entry_rate,
            "entry_dollars": entry_dollars,
            "project_id": project.id,
            "invoices": [
                {"id": inv.id, "record_number": inv.record_number} for inv in entry.invoices
            ],  # Include invoice info
        }

        grouped_data[customer.id]["projects"][project.id]["tasks"][task.id]["entries"].append(grouped_entry)

        grand_total_hours += entry.hours or 0.0
        grand_total_dollars += entry_dollars

    # Convert the nested dictionary structure to the desired list of Pydantic models
    final_grouped_list = []
    for customer_id, customer_data in grouped_data.items():
        customer_projects_list = []
        for project_id, project_data in customer_data["projects"].items():
            project_tasks_list = []
            for task_id, task_data in project_data["tasks"].items():
                project_tasks_list.append(GroupedTask(**task_data))
            project_data["tasks"] = project_tasks_list
            customer_projects_list.append(GroupedProject(**project_data))
        customer_data["projects"] = customer_projects_list
        final_grouped_list.append(GroupedCustomer(**customer_data))

    return GroupedTimeEntriesResponse(
        grand_total_hours=grand_total_hours,
        grand_total_dollars=grand_total_dollars,
        grouped_time_entries=final_grouped_list,
    )


@time_entries_router.post(
    "/", response_model=TimeEntry, status_code=status.HTTP_201_CREATED, summary="Create a new Time Entry"
)
async def create_time_entry(time_entry: TimeEntryCreate, session: Session = Depends(get_session)):
    """Creates a new time entry in the database."""
    db_time_entry = TimeEntry.model_validate(time_entry)
    session.add(db_time_entry)
    session.commit()
    session.refresh(db_time_entry)
    return db_time_entry


@time_entries_router.get("/", response_model=List[TimeEntryReadWithRelations], summary="Get all Time Entries")
async def get_all_time_entries(session: Session = Depends(get_session)):
    """
    Retrieves a list of all time entries with related Project, User, Task, and Invoice data.
    """
    time_entries = session.exec(
        select(TimeEntry)
        .options(selectinload(TimeEntry.project))
        .options(selectinload(TimeEntry.task))
        .options(selectinload(TimeEntry.user))
        .options(selectinload(TimeEntry.invoices))  # Eager load invoices
    ).all()
    return time_entries


@time_entries_router.get("/{time_entry_id}", response_model=TimeEntryReadWithRelations, summary="Get Time Entry by ID")
async def get_time_entry_by_id(time_entry_id: int, session: Session = Depends(get_session)):
    """
    Retrieves a single time entry by its ID with related Project, User, Task, and Invoice data.
    """
    time_entry = session.exec(
        select(TimeEntry)
        .where(TimeEntry.id == time_entry_id)
        .options(selectinload(TimeEntry.project))
        .options(selectinload(TimeEntry.task))
        .options(selectinload(TimeEntry.user))
        .options(selectinload(TimeEntry.invoices))  # Eager load invoices
    ).first()
    if not time_entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time Entry not found")
    return time_entry


@time_entries_router.put("/{time_entry_id}", response_model=TimeEntry, summary="Update a Time Entry")
async def update_time_entry(
    time_entry_id: int, time_entry_update: TimeEntryUpdate, session: Session = Depends(get_session)
):
    """
    Updates an existing time entry's information.
    Prevents update if the time entry is associated with an invoice.
    """
    time_entry = session.exec(
        select(TimeEntry)
        .where(TimeEntry.id == time_entry_id)
        .options(selectinload(TimeEntry.invoices))  # Load invoices to check status
    ).first()

    if not time_entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time Entry not found")

    if time_entry.invoices:  # Check if the time entry has any associated invoices
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update time entry: It is associated with an invoice.",
        )

    time_entry_data = time_entry_update.model_dump(exclude_unset=True)
    for key, value in time_entry_data.items():
        setattr(time_entry, key, value)

    session.add(time_entry)
    session.commit()
    session.refresh(time_entry)
    return time_entry


@time_entries_router.delete("/{time_entry_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a Time Entry")
async def delete_time_entry(time_entry_id: int, session: Session = Depends(get_session)):
    """
    Deletes a time entry from the database.
    Prevents deletion if the time entry is associated with an invoice.
    """
    time_entry = session.exec(
        select(TimeEntry)
        .where(TimeEntry.id == time_entry_id)
        .options(selectinload(TimeEntry.invoices))  # Load invoices to check status
    ).first()

    if not time_entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time Entry not found")

    if time_entry.invoices:  # Check if the time entry has any associated invoices
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete time entry: It is associated with an invoice.",
        )

    session.delete(time_entry)
    session.commit()
    return {"ok": True}
