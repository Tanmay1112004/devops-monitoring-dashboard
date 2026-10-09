# DevOps Monitoring Dashboard

A small FastAPI dashboard for tracking applications, deployments, and incidents. It uses SQLite for simple local and hackathon demos.

## Features

- Register applications with a name, health URL, and environment.
- Check a registered application's HTTP health and save its Healthy or Unhealthy status.
- Record deployments with a version and status.
- Create incidents and mark them resolved.
- View summary counts and recent records in the web dashboard.

A successful health check means the URL returned an HTTP status from 200 to 399. It does not verify every feature of the monitored application. The endpoint accepts only HTTP(S) URLs resolving to public IP addresses, disables redirects, and uses a five-second timeout. DNS validation and the HTTP request are separate operations, so this demo check is not a complete production SSRF defense.

## Run locally

From the project root, open PowerShell and run:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Open the dashboard at <http://127.0.0.1:8000/> and the API documentation at <http://127.0.0.1:8000/docs>.

To check an application's health, register it through the dashboard, then choose **Check health** in its row. The same operation is available as `POST /applications/{application_id}/health-check` in the API docs.

## API routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check that the dashboard API is running |
| `GET`, `POST` | `/applications` | List or register applications |
| `POST` | `/applications/{application_id}/health-check` | Check and update an application's health |
| `GET`, `POST` | `/deployments` | List or record deployments |
| `GET`, `POST` | `/incidents` | List or create incidents |
| `PATCH` | `/incidents/{incident_id}/resolve` | Resolve an incident |

## AWS Elastic Beanstalk preparation

The `backend` directory is the deployment source folder. It contains `main.py`, `requirements.txt`, `Procfile`, `.ebignore`, and the `static` assets. The Procfile starts Uvicorn on port 8000.

For a demo, the app uses a SQLite database stored beside `main.py`. SQLite data may not persist across instance replacement or redeployment, so this setup is not intended for production persistence. AWS credentials and deployment configuration are not included in this repository.
