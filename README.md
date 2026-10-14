# NovaWorks AI Project Manager

Stack: HTML/CSS/JavaScript, Flask, MySQL, Gemini API.

Admin pastes a meeting transcript, Gemini extracts projects and tasks, and the app saves them in MySQL with role-based access (admin / manager / agent).

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env            # then fill in GEMINI_API_KEY and DB_PASSWORD
mysql -u root -p < schema.sql   # creates database and tables
python seed.py                  # creates the 10 demo users (safe to re-run)
python app.py                   # open http://127.0.0.1:5000
```

## Environment variables
SECRET_KEY, GEMINI_API_KEY, GEMINI_MODEL, DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

## Demo accounts (password for all: `Demo123!`)
admin@novaworks.example, ayesha@ / bilal@ / hina@ (managers), ali@ / hamza@ / sara@ / usman@ / zain@ / maryam@ (agents), all `@novaworks.example`.

## Test steps
1. Log in as admin, paste the supplied transcript, click Create from Transcript: 3 projects, 12 tasks.
2. Log in as ayesha: only UrbanCart. Log in as ali: only his 3 tasks. Log in as hamza: 2 tasks across 2 projects.
3. Click "Clear all projects" as admin, change the transcript (e.g. QuickServe integration to 12 hours, 23 October) and create again.

## Features
Login/logout, admin transcript conversion, validation with readable errors, all-or-nothing save, project cards and detail, My Tasks, team directory, backend access checks.

## Known limitations
No editing of projects/tasks, no signup or password reset (not required), demo credentials only.

## Deployment
Not deployed. For extra marks: host the MySQL database (e.g. Aiven free MySQL), set the env variables on a host such as Render, and run with gunicorn app:app.
