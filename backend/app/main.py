import os

from fastapi import FastAPI
from storage import get_storage
from fastapi.middleware.cors import CORSMiddleware

storage = get_storage()

app = FastAPI(title="Powerwave API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://powerwave.oruxa.uk",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


