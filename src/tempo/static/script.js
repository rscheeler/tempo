
const dayView = document.getElementById('day-view');
const weekView = document.getElementById('week-view');
const toggleDayButton = document.getElementById('toggle-day');
const toggleWeekButton = document.getElementById('toggle-week');
const todayLink = document.getElementById('today-link');
const weekLink = document.getElementById('week-link');

toggleDayButton.addEventListener('click', () => {
    dayView.style.display = 'block';
    weekView.style.display = 'none';
    toggleDayButton.classList.add('active');
    toggleWeekButton.classList.remove('active');
    todayLink.classList.add('active');
    weekLink.classList.remove('active');
    document.title = 'My Time Tracker - Today';
});

toggleWeekButton.addEventListener('click', () => {
    dayView.style.display = 'none';
    weekView.style.display = 'block';
    toggleDayButton.classList.remove('active');
    toggleWeekButton.classList.add('active');
    todayLink.classList.remove('active');
    weekLink.classList.add('active');
    document.title = 'My Time Tracker - Week';
    // In a real application, you would likely fetch week data here via AJAX
});

const stopTimerButtons = document.querySelectorAll('.stop-timer-btn');
stopTimerButtons.forEach(button => {
    button.addEventListener('click', function () {
        const entryId = this.dataset.entryId;
        stopTimer(entryId);
    });
});

const editEntryButtons = document.querySelectorAll('.edit-entry-btn');
editEntryButtons.forEach(button => {
    button.addEventListener('click', function () {
        const entryId = this.dataset.entryId;
        editEntry(entryId);
    });
});

const deleteEntryButtons = document.querySelectorAll('.delete-entry-btn');
deleteEntryButtons.forEach(button => {
    button.addEventListener('click', function () {
        const entryId = this.dataset.entryId;
        deleteEntry(entryId);
    });
});

function stopTimer(entryId) {
    fetch(`/stop_timer/${entryId}`, {
        method: 'POST'
    }).then(response => {
        if (response.ok) {
            window.location.reload(); // Simple reload for now
        } else {
            alert('Failed to stop timer.');
        }
    });
}

function editEntry(entryId) {
    // For simplicity, let's redirect to an edit page (you might want a modal)
    window.location.href = `/edit/${entryId}`; // You'll need to create this route/page
}

function deleteEntry(entryId) {
    if (confirm('Are you sure you want to delete this entry?')) {
        fetch(`/delete_entry/${entryId}`, {
            method: 'POST'
        }).then(response => {
            if (response.ok) {
                window.location.reload(); // Simple reload for now
            } else {
                alert('Failed to delete entry.');
            }
        });
    }
}
