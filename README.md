# SkillX AI — Student Skill Exchange Platform

Professional Flask + Supabase PostgreSQL + Vercel project. UI uses a light green and white design system and includes AI-style productivity pages that work without an external AI API.

## Stack
- Python / Flask
- PostgreSQL on Supabase
- psycopg 3
- Jinja2 HTML templates
- Responsive CSS
- Vercel Python runtime

## Local setup
1. Install Python 3.11+.
2. Create and activate a virtual environment.
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and set `DATABASE_URL` to your Supabase PostgreSQL connection string.
5. Run `python app.py`.
6. Open `http://127.0.0.1:5000`.

The application creates the PostgreSQL tables and demo data on first startup. For a clean manual setup, run `schema.sql` in the Supabase SQL Editor and then start the app.

## Demo accounts
- Admin: `admin@skillx.edu` / `Admin@1234`
- Student: `sarah@skillx.edu` / `password123`

Change these credentials before public production use.

## Supabase
Use the Supabase Connect panel to obtain the PostgreSQL connection string. For Vercel/serverless deployments, prefer the pooler connection Supabase provides for serverless workloads. Never commit `DATABASE_URL`, database passwords, or other secrets.

## Vercel
1. Push the project to GitHub.
2. Import the repository into Vercel.
3. Add `SECRET_KEY` and `DATABASE_URL` under Project Settings → Environment Variables.
4. Deploy.

## AI pages
- `/ai` — AI workspace
- `/ai/chat` — AI coach
- `/ai/roadmap` — career roadmap generator
- `/ai/resume` — resume content builder
- `/ai/analyzer` — skill gap analyzer
- `/ai/interview` — interview practice
- `/ai/quiz` — quiz generator

The AI pages use deterministic, offline-safe generation so the project remains runnable without an API key. An external model provider can be added later behind the same routes.
