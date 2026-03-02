"""FastAPI application entry point for Salt All The Things."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from satt.routes.ai import router as ai_router
from satt.routes.auth import router as auth_router
from satt.routes.data import router as data_router
from satt.routes.health import router as health_router
from satt.routes.public import router as public_router
from satt.routes.users import router as users_router

app = FastAPI(title="Salt All The Things API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://saltallthethings.com", "https://salt.shadowedvaca.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(data_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(public_router, prefix="/public")
