"""Scheduler for periodic data ingestion."""
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio

from config import settings, location_config
from storage.database import get_db
from ingestion.purpleair import fetch_and_store
from ingestion.weather import fetch_and_store_weather


class DataScheduler:
    """Scheduler for periodic data updates."""

    def __init__(self):
        """Initialize scheduler."""
        self.scheduler = AsyncIOScheduler()
        self.db = get_db()

    async def update_air_quality_job(self):
        """Job to update air quality data."""
        try:
            location = location_config.get_location(settings.default_location)
            sensor_ids = location["sensors"]["purpleair"]

            await fetch_and_store(
                settings.purpleair_api_key,
                sensor_ids,
                location,
                self.db
            )

            print(f"[{datetime.now()}] Updated air quality data")

        except Exception as e:
            print(f"[{datetime.now()}] Error updating air quality: {e}")

    async def update_weather_job(self):
        """Job to update weather data."""
        try:
            location = location_config.get_location(settings.default_location)

            await fetch_and_store_weather(
                settings.openweather_api_key,
                location,
                self.db
            )

            print(f"[{datetime.now()}] Updated weather data")

        except Exception as e:
            print(f"[{datetime.now()}] Error updating weather: {e}")

    def start(self):
        """Start the scheduler."""
        # Update air quality every 10 minutes
        self.scheduler.add_job(
            self.update_air_quality_job,
            "interval",
            minutes=10,
            id="aq_update",
            replace_existing=True
        )

        # Update weather every 15 minutes
        self.scheduler.add_job(
            self.update_weather_job,
            "interval",
            minutes=15,
            id="weather_update",
            replace_existing=True
        )

        # Daily database maintenance at 2 AM
        self.scheduler.add_job(
            self.db.vacuum,
            CronTrigger(hour=2, minute=0),
            id="db_vacuum",
            replace_existing=True
        )

        self.scheduler.start()
        print("Scheduler started")

    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
        print("Scheduler stopped")
