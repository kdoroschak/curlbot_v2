import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Union

import schedule
from praw.reddit import Subreddit

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BotActionParams(ABC):
    pass


class BotAction(ABC):
    @abstractmethod
    def run(self) -> None:
        pass

    def schedule_action(self, frequency_mins: Union[int, float]) -> None:
        schedule.every(frequency_mins).minutes.do(self.run)


class BotActionFactory(ABC):
    @abstractmethod
    def get_instance(self, subreddit: Subreddit) -> BotAction:
        pass
