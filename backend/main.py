from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)


# ---------- Database configuration ----------

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATABASE_URL = f"sqlite:///{BASE_DIR / 'monitoring.db'}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- Database models ----------

class Application(Base):
    __tablename__ = "applications"

    id = mapped_column(Integer, primary_key=True, index=True)
    name = mapped_column(String(100), nullable=False)
    url = mapped_column(String(500), nullable=False)
    environment = mapped_column(String(50), default="Development")
    status = mapped_column(String(30), default="Unknown")
    created_at = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    deployments = relationship(
        "Deployment", back_populates="application"
    )
    incidents = relationship(
        "Incident", back_populates="application"
    )


class Deployment(Base):
    __tablename__ = "deployments"

    id = mapped_column(Integer, primary_key=True, index=True)
    application_id = mapped_column(
        ForeignKey("applications.id"), nullable=False
    )
    version = mapped_column(String(50), nullable=False)
    status = mapped_column(String(30), default="Pending")
    deployed_at = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    application = relationship(
        "Application", back_populates="deployments"
    )


class Incident(Base):
    __tablename__ = "incidents"

    id = mapped_column(Integer, primary_key=True, index=True)
    application_id = mapped_column(
        ForeignKey("applications.id"), nullable=False
    )
    title = mapped_column(String(200), nullable=False)
    severity = mapped_column(String(20), default="Medium")
    status = mapped_column(String(30), default="Open")
    created_at = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    application = relationship(
        "Application", back_populates="incidents"
    )


# ---------- API schemas ----------

class ApplicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=500)
    environment: str = "Development"


class DeploymentCreate(BaseModel):
    application_id: int
    version: str = Field(min_length=1, max_length=50)
    status: str = "Successful"


class IncidentCreate(BaseModel):
    application_id: int
    title: str = Field(min_length=1, max_length=200)
    severity: str = "Medium"


# ---------- Start application ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="DevOps Monitoring Dashboard",
    description="Application health, deployment and incident tracking",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------- General endpoints ----------

@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------- Application endpoints ----------

@app.post("/applications", status_code=201)
def create_application(
    data: ApplicationCreate,
    db: Session = Depends(get_db),
):
    application = Application(
        name=data.name,
        url=data.url,
        environment=data.environment,
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    return {
        "id": application.id,
        "name": application.name,
        "url": application.url,
        "environment": application.environment,
        "status": application.status,
        "created_at": application.created_at,
    }


@app.get("/applications")
def list_applications(db: Session = Depends(get_db)):
    applications = db.query(Application).order_by(
        Application.id.desc()
    ).all()

    return [
        {
            "id": item.id,
            "name": item.name,
            "url": item.url,
            "environment": item.environment,
            "status": item.status,
            "created_at": item.created_at,
        }
        for item in applications
    ]


# ---------- Application health checks ----------
def validate_public_url(url: str) -> None:
    """Reject invalid URLs and hostnames that resolve to non-public IPs."""
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Enter a valid public HTTP or HTTPS URL.")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="URLs containing credentials are not allowed.")

    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
        resolved_ips = [ipaddress.ip_address(item[4][0]) for item in addresses]
    except (socket.gaierror, ValueError, OSError):
        raise HTTPException(status_code=400, detail="The application hostname could not be resolved.")

    if not resolved_ips or any(not address.is_global for address in resolved_ips):
        raise HTTPException(status_code=400, detail="Private or non-public IP addresses are not allowed.")


@app.post("/applications/{application_id}/health-check")
def check_application_health(
    application_id: int,
    db: Session = Depends(get_db),
):
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")

    try:
        validate_public_url(application.url)
        with httpx.Client(timeout=5.0, follow_redirects=False, trust_env=False) as client:
            response = client.get(application.url)

        status_code = response.status_code
        is_healthy = 200 <= status_code < 400
        application.status = "Healthy" if is_healthy else "Unhealthy"
        db.commit()
        db.refresh(application)
        return {
            "application_id": application.id,
            "application": application.name,
            "url": application.url,
            "health": application.status,
            "http_status_code": status_code,
            "message": (
                "Application is reachable."
                if is_healthy
                else "Application returned an unsuccessful HTTP status."
            ),
        }
    except httpx.TimeoutException:
        application.status = "Unhealthy"
        db.commit()
        return {
            "application_id": application.id,
            "application": application.name,
            "url": application.url,
            "health": "Unhealthy",
            "message": "Health check timed out after 5 seconds.",
        }
    except httpx.RequestError:
        application.status = "Unhealthy"
        db.commit()
        return {
            "application_id": application.id,
            "application": application.name,
            "url": application.url,
            "health": "Unhealthy",
            "message": "Could not connect to the application.",
        }


# ---------- Deployment endpoints ----------
@app.post("/deployments", status_code=201)
def create_deployment(
    data: DeploymentCreate,
    db: Session = Depends(get_db),
):
    application = db.get(Application, data.application_id)

    if application is None:
        raise HTTPException(404, "Application not found")

    deployment = Deployment(
        application_id=data.application_id,
        version=data.version,
        status=data.status,
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    return {
        "id": deployment.id,
        "application_id": deployment.application_id,
        "version": deployment.version,
        "status": deployment.status,
    }


@app.get("/deployments")
def list_deployments(db: Session = Depends(get_db)):
    deployments = db.query(Deployment).order_by(
        Deployment.id.desc()
    ).all()

    return [
        {
            "id": item.id,
            "application_id": item.application_id,
            "version": item.version,
            "status": item.status,
            "deployed_at": item.deployed_at,
        }
        for item in deployments
    ]


# ---------- Incident endpoints ----------

@app.post("/incidents", status_code=201)
def create_incident(
    data: IncidentCreate,
    db: Session = Depends(get_db),
):
    application = db.get(Application, data.application_id)

    if application is None:
        raise HTTPException(404, "Application not found")

    incident = Incident(
        application_id=data.application_id,
        title=data.title,
        severity=data.severity,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    return {
        "id": incident.id,
        "application_id": incident.application_id,
        "title": incident.title,
        "severity": incident.severity,
        "status": incident.status,
    }


@app.get("/incidents")
def list_incidents(db: Session = Depends(get_db)):
    incidents = db.query(Incident).order_by(
        Incident.id.desc()
    ).all()

    return [
        {
            "id": item.id,
            "application_id": item.application_id,
            "title": item.title,
            "severity": item.severity,
            "status": item.status,
            "created_at": item.created_at,
        }
        for item in incidents
    ]


@app.patch("/incidents/{incident_id}/resolve")
def resolve_incident(
    incident_id: int,
    db: Session = Depends(get_db),
):
    incident = db.get(Incident, incident_id)

    if incident is None:
        raise HTTPException(404, "Incident not found")

    incident.status = "Resolved"
    db.commit()

    return {
        "id": incident.id,
        "status": incident.status,
        "message": "Incident resolved successfully",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
