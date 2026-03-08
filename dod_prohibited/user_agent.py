import requests
from pathlib import Path
import json
import random


class RandomUserAgent:
    """Class to get a random user agent string from a devices.json file."""
    
    ua_str: str
    """Random user agent string."""
    random_ua_key: str
    """Key of the random user agent."""
    random_ua_details: dict
    """Details of the random user agent."""
    user_agents: dict
    """Dictionary of user agents loaded from devices.json."""
    force_new: bool = False
    """Flag to force generation of a new user agent string."""

    def __init__(self, force_new: bool = False) -> None:
        """UserAgent generator.

        Args:
            force_new (bool, optional): Whether to always force a new ua selection. Defaults to False.
        """
        session = requests.Session()
        devices_json_path = Path('devices.json').expanduser()
        if not devices_json_path.exists():
            user_agents_response = session.get('https://raw.githubusercontent.com/selwin/python-user-agents/refs/heads/master/user_agents/devices.json')
            with devices_json_path.open('w') as f:
                f.write(user_agents_response.text)
            self.user_agents = user_agents_response.json()
        else:
            self.user_agents = json.load(devices_json_path.open())
        self.force_new = force_new
        self.ua_str = None
    
    def get_random_ua(self, force_new: bool = False) -> str:
        """Get a random user agent string.

        Args:
            force_new (bool, optional): If True, forces generation of a new user agent string. Defaults to False.

        Returns:
            str: Random user agent string.
        """
        self.force_new = force_new
        return self.__str__()
    
    def __str__(self) -> str:
        """Get a random user agent string.

        Returns:
            str: A random user agent string.
        """
        if self.ua_str and not self.force_new:
            return self.ua_str
        else:
            self.random_ua_key = random.choice(list(self.user_agents.keys()))
            self.random_ua_details = self.user_agents[self.random_ua_key]
            self.ua_str = self.random_ua_details['ua_string']
            return self.ua_str
