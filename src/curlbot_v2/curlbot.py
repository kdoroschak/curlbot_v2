import logging
import time
from logging.handlers import RotatingFileHandler
from typing import List

import schedule

from curlbot_v2.actions import (
    BotAction,
    BotActionFactory,
    RoutineCheckerFactory,
    RoutineCheckerParams,
)

logger = logging.getLogger()


class CurlBot:
    _praw_ini_site_name: str
    _subreddit: str
    _bot_actions: List[BotAction]

    def __init__(self, praw_ini_site_name: str, subreddit: str) -> None:
        self._praw_ini_site_name = praw_ini_site_name
        self._subreddit = subreddit

    def __post_init__(self) -> None:
        # Set up the database
        # Connect to reddit
        pass

    def add_bot_action(self, action_factory: BotActionFactory, frequency_mins: int) -> None:
        action = action_factory.get_instance(self._subreddit)
        action.schedule_action(frequency_mins)


if __name__ == "__main__":
    handler = RotatingFileHandler("logs/bot-activity.log", maxBytes=1000000, backupCount=1000)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
    )
    handler.setFormatter(formatter)
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    schedule.clear()

    curlbot = CurlBot(praw_ini_site_name="cbot", subreddit="curlyhair")

    # TODO replace with method to go get these params from somewhere else (wiki)
    routine_checker_params = RoutineCheckerParams(
        flair_to_check=["help"], remind_after_mins=30, remove_after_mins=60, report_after_mins=60
    )
    routine_checker = RoutineCheckerFactory(routine_checker_params)

    curlbot.add_bot_action(routine_checker, 0.2)
    logger.info("Starting schedule.")
    while True:
        logger.debug("Schedule sleeping.")
        time.sleep(10)  # 10 sec
        schedule.run_pending()
