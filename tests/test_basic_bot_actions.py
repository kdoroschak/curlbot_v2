import unittest
from unittest.mock import MagicMock

import praw
import pytest
import requests
from prawcore.exceptions import NotFound

from curlbot_v2.actions import BotAction


# Mock the praw.Reddit instance
class MockReddit:
    def __init__(self):
        self.subreddit = MagicMock()


class DummyBotAction(BotAction):
    def __init__(
        self,
        reddit: praw.reddit.Reddit,
        subreddit_name: str,
    ) -> None:
        self._reddit = reddit
        self._subreddit = reddit.subreddit(subreddit_name)

    def run() -> None:
        pass


class TestRedditBotConfig(unittest.TestCase):
    def setUp(self):
        self.mock_reddit = MockReddit()

    def test_successful_config_parsing(self):
        # Simulate a valid YAML config in the wiki content
        yaml_content = """
        bot_name: MyBot
        api_key: your_api_key
        settings:
          option1: true
          option2: false
        """
        self.mock_reddit.subreddit().wiki.__getitem__().content_md = yaml_content

        bot_action = DummyBotAction(self.mock_reddit, "subreddit_name")
        config = bot_action._get_config_from_wiki("wiki_page_name")

        self.assertEqual(config["bot_name"], "MyBot")
        self.assertEqual(config["api_key"], "your_api_key")
        self.assertEqual(config["settings"]["option1"], True)
        self.assertEqual(config["settings"]["option2"], False)

    def test_missing_wiki_page(self):
        # Simulate a missing wiki page
        response = requests.Response()
        response.status_code = 404
        self.mock_reddit.subreddit().wiki.__getitem__.side_effect = NotFound(response)

        with pytest.raises(NotFound):
            bot_action = DummyBotAction(self.mock_reddit, "subreddit_name")
            config = bot_action._get_config_from_wiki("wiki_page_name")

    def test_invalid_yaml_content(self):
        # Simulate invalid YAML content in the wiki
        invalid_yaml_content = "invalid_yaml"
        self.mock_reddit.subreddit().wiki.__getitem__().content_md = invalid_yaml_content

        bot_action = DummyBotAction(self.mock_reddit, "subreddit_name")
        config = bot_action._get_config_from_wiki("wiki_page_name")

        self.assertEqual(config, invalid_yaml_content)


if __name__ == "__main__":
    unittest.main()
