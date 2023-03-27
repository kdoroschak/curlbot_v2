import logging
import sqlite3
from dataclasses import dataclass
from typing import List, Optional

from praw.reddit import Submission, Subreddit

from curlbot_v2._submission_helpers import get_new_subreddit_posts

from ._action import BotAction, BotActionFactory, BotActionParams

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoutineCheckerParams(BotActionParams):
    flair_to_check: List[str]
    remind_after_mins: int
    remove_after_mins: int
    report_after_mins: int
    keywords: List[str]
    min_routine_chars: int = 0
    sidestepping_phrases: List[str] = ["don't have a routine", "no routine", "dont have a routine"]
    max_posts: int = 100


class RoutineChecker(BotAction):
    _params: RoutineCheckerParams
    _subreddit: Subreddit
    _db_name: str
    _db_table_name: str
    _db: sqlite3.Cursor

    def __init__(
        self,
        params: RoutineCheckerParams,
        subreddit: Subreddit,
        db_name: str,
        db_table_name: str = "post_hstory",
    ) -> None:
        self._params = params
        self._subreddit = subreddit
        self._db_name = db_name
        self._db_table_name = db_table_name

    def __post_init__(self):
        db = self._set_up_db(self._db_name, self._db_table_name)
        self._db = db

    def run(self) -> None:
        logger.debug("Running (nothing for now, but I was called.)")
        print("called")

        posts = get_new_subreddit_posts(self._subreddit, self._params.max_posts)

        # Get posts
        # For each post...
        #   Check for the post in the database
        #     Can be in a few different states: doesn't need a routine, watching for routine before time cutoff, has routine
        pass

    def _set_up_db(self, db_name: str, db_table_name: str) -> sqlite3.Cursor:
        logger.debug("Setting up database connections.")
        db_conn = sqlite3.connect(db_name)
        db = db_conn.cursor()
        try:
            logger.debug(f"Creating new table in {db_name}, {db_table_name}.")
            db.execute(
                f"""CREATE TABLE {db_table_name}
                    (id text, url text, created_utc int, needs_routine int, has_routine int,
                    sent_reminder_utc int, removed_utc int, reported_utc int)"""
            )
        except sqlite3.OperationalError as e:
            # We don't want to overwrite the db every time we start the bot
            if "already exists" in str(e):
                self.logger.info("Database already exists, no need to initialize.")
            else:
                self.logger.warning(f"Unknown OperationalError: {e}")
                raise
        return db

    def _post_has_routine(self, post: Submission) -> bool:
        pass

    def _text_has_keywords(self, text: str) -> bool:
        for k in self._params.keywords:
            if k in text:
                return True
        return False

    def _text_fulfills_min_length(self, text: str) -> bool:
        return len(text) >= self._params.min_routine_chars

    def _text_has_sidesteppers(self, text: str) -> bool:
        pass


class RoutineCheckerFactory(BotActionFactory):
    _params: RoutineCheckerParams

    def __init__(self, params: RoutineCheckerParams):
        self._params = params

    def get_instance(self, subreddit: Subreddit) -> RoutineChecker:
        db_name = "posts.db"
        db_table_name = "post_history"
        return RoutineChecker(self._params, subreddit, db_name, db_table_name)
