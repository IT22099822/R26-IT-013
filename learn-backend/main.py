import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from routers import auth, onboarding, content, events, quiz, profile, admin, coach
from scheduler import scheduler

# Without this, Python's default log level (WARNING) silently
# swallows every logger.info() call across the app — including the
# new [QGEN] debug logging in question_generator.py. This has been
# true the whole time; nothing was previously misconfigured "broken,"
# INFO-level visibility just never existed until now.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(title="LEARN Platform API", version="1.6", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://learn-english-sliit.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,        prefix="/auth",        tags=["Auth"])
app.include_router(onboarding.router,  prefix="/onboarding",  tags=["Onboarding"])
app.include_router(content.router,     prefix="/content",     tags=["Content"])
app.include_router(events.router,      prefix="/events",      tags=["Events"])
app.include_router(quiz.router,        prefix="/quiz",        tags=["Quiz"])
app.include_router(profile.router,     prefix="/profile",     tags=["Profile"])
app.include_router(admin.router,       prefix="/admin",       tags=["Admin"])
app.include_router(coach.router,       prefix="/coach",       tags=["Coach"])

@app.get("/health")
async def health():
    return {"status": "ok"}