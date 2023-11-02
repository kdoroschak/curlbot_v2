import logging
import sqlite3
import time
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Tuple, Type

import praw
import schedule

from curlbot_v2.actions import BotAction, RoutineChecker

logger = logging.getLogger()


class CurlBot:
    _praw_ini_site_name: str
    _jobs: Dict[str, schedule.Job]
    _reddit: praw.Reddit
    _db: sqlite3.Cursor

    def __init__(self, praw_ini_site_name: str, database_name: str) -> None:
        """Initialize curlbot to set up reddit using the specified ini file and database name.

        Args:
            praw_ini_site_name (str): required praw ini file
            database_name (str): filename for the database
        """
        self._praw_ini_site_name = praw_ini_site_name
        self._reddit = praw.Reddit(site_name=praw_ini_site_name)
        self._db = self._initialize_database(database_name)
        self._jobs = {}

    def _initialize_database(self, db_name: str) -> sqlite3.Cursor:
        db_conn = sqlite3.connect(db_name)
        db = db_conn.cursor()
        return db

    def get_subreddit(self, subreddit_name: str) -> praw.reddit.Subreddit:
        return self._reddit.subreddit(subreddit_name)

    def add_bot_action(
        self, job_name: str, action_type: Type[BotAction], subreddit_name: str, frequency_mins: int
    ) -> None:
        """Add this job to the queue of things the bot should do.

        Args:
            job_name (str): Name of the job, so if you want to remove it later, etc. you can
                retrieve it by name.
            action_type (Type[BotAction]): The action the bot will be doing
            subreddit_name (str): Name of the subreddit
            frequency_mins (int): How often the bot should kick off this job. Note that this is
                different from any parameters for the job itself. This ONLY makes the bot run this
                task every `frequency_mins` minutes.
        """
        subreddit = self.get_subreddit(subreddit_name)
        action = action_type(subreddit, self._db)
        job = schedule.every(frequency_mins).minutes.do(action.run)
        self._jobs[job_name] = job

    def remove_bot_action(self, job_name: str) -> None:
        if job_name in self._jobs:
            job = self._jobs.get(job_name)
            schedule.cancel_job(job)


class CustomModuleFilter(logging.Filter):
    def __init__(self, module_name):
        self.module_name = module_name

    def filter(self, record):
        return f"/src/{self.module_name}" in record.pathname


if __name__ == "__main__":
    handler = RotatingFileHandler("logs/bot-activity.log", maxBytes=1000000, backupCount=1000)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(filename)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
    )
    handler.setFormatter(formatter)
    handler.addFilter(CustomModuleFilter("curlbot_v2"))
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    schedule.clear()

    # Switch database name for testing
    curlbot = CurlBot(praw_ini_site_name="cbot", database_name="curlybot.sqlite3")

    # Dummy subreddit for testing
    # curlbot.add_bot_action(
    #     job_name="routine_checker",
    #     action_type=RoutineChecker,
    #     subreddit_name="curlbot_test",
    #     frequency_mins=0.5,
    # )

    # Real subreddit
    curlbot.add_bot_action(
        job_name="routine_checker",
        action_type=RoutineChecker,
        subreddit_name="curlyhair",
        frequency_mins=3,
    )
    # curlbot.remove_bot_action("routine_checker")

    logger.info("Starting schedule.")
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
        logger.debug("Schedule sleeping.")
        time.sleep(10)
