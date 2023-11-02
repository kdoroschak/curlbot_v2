import logging
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict

import yaml  # type:ignore[import]
from praw.reddit import Subreddit  # type:ignore[import]
from prawcore.exceptions import NotFound  # type:ignore[import]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BotActionParams(ABC):
    pass


class BotAction(ABC):
    _db: sqlite3.Cursor
    _subreddit: Subreddit

    @abstractmethod
    def __init__(
        self,
        subreddit: Subreddit,
        db: sqlite3.Cursor,
    ):
        pass

    @abstractmethod
    def run(self) -> None:
        pass

    def _get_config_from_wiki(self, wiki_page_name: str) -> Dict[str, Any]:
        try:
            wiki_page = self._subreddit.wiki[wiki_page_name]
            content = wiki_page.content_md
            try:
                config = yaml.safe_load(content)
                logger.debug(f"CONFIGURATION LOADED (not yet parsed):\n{config}")
                return config

            except yaml.YAMLError:
                logger.error(
                    f"Failed to parse YAML content from the wiki page '{wiki_page_name}='."
                )
                raise

        except NotFound:
            logger.error(
                f"The wiki page '{wiki_page_name}' was not found in the subreddit '{self._subreddit.display_name}'."
            )
            raise
