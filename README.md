# MoodLinker: IU International University of Applied Sciences Tracker App Portfolio Project

![MoodLinker](./img/MoodLinker.png)

## Description

**MoodLinker** is an emotion-driven habit tracker built with Django, Bootstrap 5, and AI-Powered analytics. It helps users develop and maintain **five key daily habits** while logging their mood and refections. The app correlates with habit completion, offering insights, streak tracking, and emotion-aware reminders.

Think of it as a **blend of therapy**, **habit-building**, and **smart analytics** in a sleek, engaging interface.

## Features

- **Habit Tracking** — Track up to **five daily habits** with completion states.
- **Mood Logging** — Record mood scores (1-5) with reflections and emojis.
- **Analytics Dashboard** — View mood-habit correlations with **Chart.js** graphs.
- **Smart Notifications** — Celery + Redis handle reminders when motivation dips.
- **Calendar Integration** — Export reminders to your calendar with ICS feeds.
- **AI Suggestion** — NLP-powered insights (spaCy + VADER) provide tips like _"Your motivation dips on Sundays—plan lightr habits."_
- **Authentication** — Secure user registration, login, and personalized profiles.
- **Timezone Aware** — Reminders and notifications respect user's local timezone.

![Dashboard](./img/Dashboard.png)

## Tech Stack

- **Backend:** Django 5+, Django REST Framework
- **Frontend:** Bootstrap 5. Chart.js, Vanilla JavaScript, CSS
- **Database:** MySQL (default, can use SQLite for testing)
- **Task Queue:** Celery + Redis
- **AI/NLP:** spaCy, NLTK, VADER sentiment analysis
- **Testing:** pytest, pytest-django

![Analytics](./img/Analytics.png)

## Installation

Follow these steps to set up MoodLinker locally.

### 1. Clone the Repository

```bash
git clone https://github.com/CyrilCele/moodlinker.git
```

### 2. Set Up Python Environment

Using **Pipenv** (recommended):

```bash
pip install pipenv
pipenv install --dev
pipenv shell
```

Or with **requirements.txt**:

```bash
python -m venv venv
source venv/bin/activate    # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Database

Update your `settings.py` for MySQL (or fallback to SQLite).
Applying migrations:

```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. Create Superuser

```bash
python manage.py createsuperuser
```

### 5. Run Redis (for background tasks)

Make sure Redis is installed and running:

```bash
redis-server
```

### 6. Start Celery Worker

```bash
celery -A moodlinker worker -l info
celery -A moodlnker beat -l info    # for scheduled tasks
```

### 7. Run Django Server

```bash
python manage.py runserver
```

Now visit: http://127.0.0.1:8000

## Usage

1. **Register/Login** to create your profile.
2. **Add up to 5 habits** (daily/weekly/monthly).
3. **Log your mood** daily with a reflection.
4. **Mark habits as complete** each day.
5. **View analytics** for correlations and streaks.
6. **Enable reminders** to get notified when motivation drops.
7. **Export calendar** reminders via ICS feed.

## Testing

Run unit and integration tests with

```bash
pytest
```

![pytest](./img/pytest.png)

## Project Structure

![Project Structure](./img/Project-Structure.png)

## Author

Nkululeko Cyril Cele
