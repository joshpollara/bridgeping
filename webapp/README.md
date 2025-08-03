# Bridge Ping Web App

A FastAPI web application with user authentication using SQLite and Bootstrap.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python main.py
```

The app will be available at http://localhost:8000

## Features

- User registration with email and password
- Secure password hashing with bcrypt
- JWT-based session management via secure cookies
- Bootstrap 5 UI
- Protected dashboard page
- SQLite database for user storage

## Routes

- `/` - Home page
- `/register` - User registration
- `/login` - User login
- `/logout` - Clear session
- `/dashboard` - Protected page (requires authentication)