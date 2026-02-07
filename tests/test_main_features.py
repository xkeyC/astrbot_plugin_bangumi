import asyncio
import os
import sys
from unittest.mock import MagicMock, AsyncMock, patch, call

import pytest

# Setup paths to include 'src' and project root as a package
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
parent_of_project_root = os.path.dirname(project_root)

if parent_of_project_root not in sys.path:
    sys.path.insert(0, parent_of_project_root)

# Mock 'astrbot' dependency
# This needs to happen BEFORE any imports that might pull in real astrbot modules
sys.modules["astrbot"] = MagicMock()

# Explicitly mock each part of the import path for nested modules
mock_astrbot_api = MagicMock()
sys.modules["astrbot.api"] = mock_astrbot_api

mock_astrbot_api_all = MagicMock()
sys.modules["astrbot.api.all"] = mock_astrbot_api_all
mock_astrbot_api_all.AstrBotConfig = MagicMock() # Mock AstrBotConfig class

mock_astrbot_api_message_components = MagicMock()
sys.modules["astrbot.api.message_components"] = mock_astrbot_api_message_components
# Mock the Comp object that is imported as `Comp` in main.py
mock_astrbot_api_message_components.Comp = MagicMock() 

mock_astrbot_api_event = MagicMock()
sys.modules["astrbot.api.event"] = mock_astrbot_api_event
mock_astrbot_api_event.AstrMessageEvent = MagicMock() # Mock AstrMessageEvent
mock_astrbot_api_event.filter = MagicMock() # Mock filter

mock_astrbot_api_star = MagicMock()
sys.modules["astrbot.api.star"] = mock_astrbot_api_star

# Define a simple mock for the Star base class
# This ensures methods like initialize are not automatically turned into MagicMocks
class MockStarBase:
    def __init__(self, context): # Only accept context as per super().__init__(context) call in main.py
        self.context = context

    async def initialize(self):
        # Mock initialize of the base class
        pass

    def terminate(self):
        # Mock terminate of the base class
        pass

mock_astrbot_api_star.Context = MagicMock() # Mock Context
mock_astrbot_api_star.Star = MockStarBase # Use our custom mock base class
# Mock the register decorator to simply return the decorated class/function
mock_astrbot_api_star.register = MagicMock(side_effect=lambda *args, **kwargs: lambda cls: cls)


# Explicitly mock get_astrbot_data_path as part of sys.modules setup
mock_astrbot_utils_path = MagicMock()
sys.modules["astrbot.core.utils.astrbot_path"] = mock_astrbot_utils_path
mock_astrbot_utils_path.get_astrbot_data_path.return_value = "/tmp/test_data_path"


# Import the class to test AFTER mocks are established
from astrbot_plugin_bangumi.main import BangumiPlugin
from astrbot_plugin_bangumi.src.services.storage import BangumiSubject


@pytest.fixture
def plugin():
    """Fixture to create a BangumiPlugin instance with mocked dependencies."""
    with (
        patch("astrbot_plugin_bangumi.main.ConfigManager") as MockConfigManager,
        patch("astrbot_plugin_bangumi.main.SchedulerManager") as MockSchedulerManager,
        patch("astrbot_plugin_bangumi.main.StorageManager") as MockStorageManager,
        patch("astrbot_plugin_bangumi.main.BangumiService") as MockBangumiService,
    ):
        mock_config_manager_instance = MockConfigManager.return_value
        mock_scheduler_manager_instance = MockSchedulerManager.return_value
        mock_storage_manager_instance = MockStorageManager.return_value
        
        # Ensure the BangumiService instance's methods are AsyncMocks
        mock_bangumi_service_instance = MockBangumiService.return_value
        mock_bangumi_service_instance.get_subject_episodes = AsyncMock()
        
        mock_context = MagicMock()
        mock_config = MagicMock()

        # Instantiate the plugin. Its constructor will use the patched classes.
        plugin_instance = BangumiPlugin(context=mock_context, config=mock_config)
        
        # Now, set the return values for the mocks that were already created by the plugin's __init__
        plugin_instance.config_manager = mock_config_manager_instance
        plugin_instance.scheduler_manager = mock_scheduler_manager_instance
        plugin_instance.storage = mock_storage_manager_instance
        plugin_instance.service = mock_bangumi_service_instance
        
        # Mock the context's send_group_message method
        plugin_instance.context.send_group_message = AsyncMock()

        yield plugin_instance

@pytest.mark.asyncio
async def test_scheduled_message_task(plugin: BangumiPlugin):
    """
    Test a hypothetical scheduled task that sends a message 10 times to a specific group.
    This test verifies the message sending mechanism when a task runs repeatedly.
    """
    target_group_id = "921162109"
    test_message = "This is a scheduled test message."

    # Define a simple task that sends a message
    async def hypothetical_scheduled_message_task():
        await plugin.context.send_group_message(group_id=target_group_id, message=test_message)

    # Simulate the task running 10 times
    for _ in range(10):
        await hypothetical_scheduled_message_task()

    # Assert that send_group_message was called 10 times with the correct arguments
    assert plugin.context.send_group_message.call_count == 10
    plugin.context.send_group_message.assert_has_calls([
        call(group_id=target_group_id, message=test_message)
    ] * 10)
    
    # Verify that the update_episodes task was scheduled during initialize
    mock_process = MagicMock()
    mock_process.returncode = 0  # Simulate successful command
    mock_process.communicate = AsyncMock(return_value=(b'', b'')) # Simulate empty stdout/stderr
    
    with patch("os.path.exists", return_value=False), \
         patch("builtins.open", MagicMock()), \
         patch("asyncio.create_subprocess_shell", return_value=mock_process): # Mock subprocess calls
            await plugin.initialize()
    plugin.scheduler_manager.add_job.assert_called_with(func=plugin.update_episodes, trigger="cron", minute=0)


@pytest.mark.asyncio
async def test_update_episodes_and_notify(plugin: BangumiPlugin):
    """
    Test the update_episodes function, simulating an update and checking for notifications.
    """
    # Mock data for subjects to be monitored
    mock_subject_1 = MagicMock(spec=BangumiSubject)
    mock_subject_1.subject_id = "123"
    mock_subject_1.name = "Test Anime 1"
    mock_subject_1.current_episode = 1
    
    mock_subject_2 = MagicMock(spec=BangumiSubject)
    mock_subject_2.subject_id = "456"
    mock_subject_2.name = "Test Anime 2"
    mock_subject_2.current_episode = 5

    plugin.storage.get_monitored_subjects.return_value = [mock_subject_1, mock_subject_2]
    
    # Mock get_subject_subscribers to return subscribed groups for mock_subject_1
    plugin.storage.get_subject_subscribers.side_effect = lambda subject_id: (
        ["921162109", "group_A"] if subject_id == "123" else []
    )

    # Mock episode data from BangumiService with dictionaries as return values
    plugin.service.get_subject_episodes.side_effect = [
        # Data for mock_subject_1: New episode 2 available
        {
            "data": [
                {"ep": 1, "airdate": "2023-01-01", "comment": 10},
                {"ep": 2, "airdate": "2023-01-08", "comment": 5} # New episode
            ]
        },
        # Data for mock_subject_2: No new episode, current is 5, latest is 5
        {
            "data": [
                {"ep": 1, "airdate": "2023-01-01", "comment": 10},
                {"ep": 2, "airdate": "2023-01-08", "comment": 5},
                {"ep": 3, "airdate": "2023-01-15", "comment": 8},
                {"ep": 4, "airdate": "2023-01-22", "comment": 12},
                {"ep": 5, "airdate": "2023-01-29", "comment": 20}
            ]
        }
    ]

    # Run the update_episodes task
    await plugin.update_episodes()

    # Assertions for mock_subject_1 (should be updated and notified)
    plugin.storage.update_subject.assert_any_call(
        subject_id=mock_subject_1.subject_id,
        current_episode=2
    )

    # Assert notifications for mock_subject_1
    expected_message_1 = f"《{mock_subject_1.name}》更新啦！当前最新集数：2"
    plugin.context.send_group_message.assert_any_call(
        group_id="921162109",
        message=expected_message_1
    )
    plugin.context.send_group_message.assert_any_call(
        group_id="group_A",
        message=expected_message_1
    )

    # Assertions for mock_subject_2 (should NOT be updated or notified)
    # Verify total calls to update_subject
    # It should only be called once for subject_1
    assert plugin.storage.update_subject.call_count == 1
    
    # Verify total calls to send_group_message
    # It should be called for group 921162109 and group_A for subject_1
    assert plugin.context.send_group_message.call_count == 2