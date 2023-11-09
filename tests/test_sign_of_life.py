import datetime
import logging
from unittest.mock import MagicMock, patch

import praw
import pytest
from pytest import LogCaptureFixture, MonkeyPatch

from curlbot_v2 import __version__
from curlbot_v2.actions import SignOfLife
from curlbot_v2.actions._routine_checker import PostState, RoutineCheckerParams, RoutineErrors

logger = logging.getLogger(__name__)


def test_version():
    assert __version__ == "0.1.0"

class TestSignOfLife:
    @pytest.fixture
    def mock_reddit(self):
        return MagicMock()

    @pytest.fixture
    def mock_subreddit(self):
        subreddit = MagicMock()
        subreddit.display_name = "CurlyBot"
        subreddit.contributor = {"display_name": "CurlyBot"}
        return subreddit
    
    @pytest.fixture
    def mock_subreddit_nonself(self):
        subreddit = MagicMock()
        subreddit.display_name = "not_self"
        subreddit.contributor = {"display_name": "CurlyBot"}
        return subreddit

    @pytest.fixture
    def test_sign_of_life_send_sign_of_life(self,  mock_subreddit: MagicMock):
        # Initialize SignOfLife with the mock subreddit
        action = SignOfLife(mock_subreddit, None)

        # Run the send_sign_of_life method
        action._send_sign_of_life()

        # Check if the description has been updated with the expected message
        assert "Bot's last sign of life:" in mock_subreddit.mod.update.call_args[1]['description']

    @pytest.fixture
    def test_sign_of_life_subreddit_is_not_self(self,  mock_subreddit_nonself: MagicMock):
        # Initialize SignOfLife with the mock subreddit
        with pytest.raises(ValueError):
            SignOfLife(mock_subreddit_nonself, None)
