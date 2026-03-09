import json
from typing import List, Optional
from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload

from db.models import (
    Project,
    ProjectCreate,
    ProjectUpdate,
    Task,
    TaskCreate,
    TaskUpdate,
    ProjectType,
    RateType,
    BudgetUnit,
    ProjectReadWithTasks,
    TimeEntry,
    Invoice,
)
from db.database import get_session

projects_router = APIRouter(
    prefix="/api/projects",
    tags=["projects"],
    responses={404: {"description": "Project not found"}},
)


@projects_router.post("/", response_model=Project, status_code=status.HTTP_201_CREATED, summary="Create a new Project")
async def create_project(project_create: ProjectCreate, session: Session = Depends(get_session)):
    """Creates a new project in the database, including its associated tasks."""
    tasks_data = project_create.tasks
    project = Project.model_validate(project_create.model_dump(exclude={"tasks"}, exclude_unset=True))

    session.add(project)
    session.commit()
    session.refresh(project)

    for task_data in tasks_data:
        task = Task(project_id=project.id, **task_data.model_dump(exclude_unset=True))
        session.add(task)

    session.commit()
    session.refresh(project)

    # Re-fetch the project with tasks to ensure the response includes them
    project_with_tasks = session.exec(
        select(Project).options(selectinload(Project.tasks)).where(Project.id == project.id)
    ).first()
    return project_with_tasks


@projects_router.get("/", response_model=List[ProjectReadWithTasks], summary="Get all Projects")
async def get_all_projects(
    session: Session = Depends(get_session),
    customer_id: Optional[int] = Query(None, description="Filter projects by customer ID"),
    show_archived: bool = Query(False, description="Include archived projects in the list"),
):
    """Retrieves a list of all projects, optionally filtered by customer and archive status,
    and calculates the total charged amount and total hours for each.
    """
    query = select(Project).options(
        selectinload(Project.tasks),  # Load tasks for project
        selectinload(Project.time_entries).selectinload(TimeEntry.task),  # Load time entries and their associated tasks
        selectinload(Project.customer),  # Load customer
    )

    if customer_id is not None:
        query = query.where(Project.customer_id == customer_id)

    if not show_archived:
        query = query.where(Project.is_archived == False)

    projects = session.exec(query).all()

    # Calculate total charged amount and total hours for each project
    projects_with_charged_amount = []
    for project in projects:
        total_charged_amount = 0.0
        total_hours_spent = 0.0  # NEW: Initialize total hours
        for time_entry in project.time_entries:
            if time_entry.hours is not None:
                # Add hours to total_hours_spent regardless of rate type
                total_hours_spent += time_entry.hours

                # Existing logic for total_charged_amount
                rate = 0.0
                if project.rate_type == RateType.PROJECT and project.project_rate is not None:
                    rate = project.project_rate
                elif project.rate_type == RateType.TASK and time_entry.task and time_entry.task.task_rate is not None:
                    rate = time_entry.task.task_rate
                total_charged_amount += time_entry.hours * rate

        # Convert to a dictionary while ensuring tasks are included
        project_dict = project.model_dump()
        project_dict["total_charged_amount"] = total_charged_amount
        project_dict["total_hours_spent"] = total_hours_spent  # NEW: Add total_hours_spent

        # Explicitly add tasks to the dictionary, ensuring they are also dumped to dictionary format
        if project.tasks:
            project_dict["tasks"] = [task.model_dump() for task in project.tasks]
        else:
            project_dict["tasks"] = []
        # Add customer
        if project.customer:
            project_dict["customer"] = project.customer

        projects_with_charged_amount.append(project_dict)

    return projects_with_charged_amount


@projects_router.get("/{project_id}", response_model=ProjectReadWithTasks, summary="Get Project by ID")
async def get_project_by_id(project_id: int, session: Session = Depends(get_session)):
    """Retrieves a single project by their ID."""
    project = session.exec(
        select(Project)
        .options(selectinload(Project.tasks), selectinload(Project.time_entries).selectinload(TimeEntry.task))
        .where(Project.id == project_id)
    ).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Calculate total charged amount and total hours for a single project
    total_charged_amount = 0.0
    total_hours_spent = 0.0  # NEW: Initialize total hours
    for time_entry in project.time_entries:
        if time_entry.hours is not None:
            total_hours_spent += time_entry.hours  # NEW: Add hours to total_hours_spent
            rate = 0.0
            if project.rate_type == RateType.PROJECT and project.project_rate is not None:
                rate = project.project_rate
            elif project.rate_type == RateType.TASK and time_entry.task and time_entry.task.task_rate is not None:
                rate = time_entry.task.task_rate
            total_charged_amount += time_entry.hours * rate

    # Convert to a dictionary while ensuring tasks are included
    project_dict = project.model_dump()
    project_dict["total_charged_amount"] = total_charged_amount
    project_dict["total_hours_spent"] = total_hours_spent  # NEW: Add total_hours_spent

    # Explicitly add tasks to the dictionary, ensuring they are also dumped to dictionary format
    if project.tasks:
        project_dict["tasks"] = [task.model_dump() for task in project.tasks]
    else:
        project_dict["tasks"] = []

    return project_dict


@projects_router.put("/{project_id}", response_model=Project, summary="Update a Project")
async def update_project(project_id: int, project_update: ProjectUpdate, session: Session = Depends(get_session)):
    """Updates an existing project's information, including its associated tasks."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    tasks_to_update_or_create = project_update.tasks if project_update.tasks is not None else []

    # Update project fields, excluding tasks from the direct model_dump to avoid overwriting relationships
    project_data = project_update.model_dump(exclude_unset=True, exclude={"tasks"})
    for key, value in project_data.items():
        setattr(project, key, value)

    # Get current tasks associated with the project
    current_db_tasks = {task.id: task for task in project.tasks if task.id is not None}
    incoming_task_ids = {task_data.id for task_data in tasks_to_update_or_create if task_data.id is not None}

    # Identify tasks to delete (those in DB but not in incoming payload)
    tasks_to_delete = []
    for task_id, task in current_db_tasks.items():
        if task_id not in incoming_task_ids:
            # Check for associated time entries before marking for deletion
            associated_time_entry = session.exec(select(TimeEntry).where(TimeEntry.task_id == task_id)).first()
            if associated_time_entry:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot remove task '{task.name}': Associated time entries exist.",
                )
            tasks_to_delete.append(task)

    for task_to_delete in tasks_to_delete:
        session.delete(task_to_delete)

    # Add or update tasks from the incoming payload
    for task_data in tasks_to_update_or_create:
        if task_data.id is not None:  # Existing task
            if task_data.id in current_db_tasks:
                task_to_update = current_db_tasks[task_data.id]
                for key, value in task_data.model_dump(exclude_unset=True).items():
                    setattr(task_to_update, key, value)
                session.add(task_to_update)
            else:
                # This case should ideally not happen if incoming_task_ids is correct,
                # but if an ID is provided that doesn't exist for this project, treat as new.
                new_task = Task(project_id=project.id, **task_data.model_dump(exclude={"id"}, exclude_unset=True))
                session.add(new_task)
        else:  # New task
            new_task = Task(project_id=project.id, **task_data.model_dump(exclude_unset=True))
            session.add(new_task)

    session.add(project)
    session.commit()
    session.refresh(project)

    # Re-fetch the project with tasks to ensure the response includes them after update
    project_with_tasks = session.exec(
        select(Project).options(selectinload(Project.tasks)).where(Project.id == project.id)
    ).first()
    return project_with_tasks


@projects_router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a Project")
async def delete_project(project_id: int, session: Session = Depends(get_session)):
    """Deletes a project from the database, preventing deletion if dependent records exist."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Check for associated time entries
    associated_time_entry = session.exec(select(TimeEntry).where(TimeEntry.project_id == project_id)).first()
    if associated_time_entry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete project: Associated time entries exist."
        )

    # Check for associated invoices (if invoices can be directly linked to projects)
    associated_invoice = session.exec(select(Invoice).where(Invoice.project_id == project_id)).first()
    if associated_invoice:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete project: Associated invoices exist."
        )

    # If no dependencies, proceed with deletion
    session.delete(project)
    session.commit()
    return {"ok": True}
