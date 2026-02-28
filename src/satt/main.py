"""FastAPI application entry point for Salt All The Things."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from satt.routes.health import router as health_router

app = FastAPI(title="Salt All The Things API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://saltallthethings.com", "https://salt.shadowedvaca.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
