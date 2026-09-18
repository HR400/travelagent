"""Test suite for production configuration and logging modules."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from config import Config, ConfigurationError, get_config, reset_config


class TestConfig(unittest.TestCase):
    """Test configuration management."""

    def setUp(self):
        """Reset configuration before each test."""
        reset_config()
        # Clear environment variables
        for key in ["OPENAI_API_KEY", "GROQ_API_KEY", "TAVILY_API_KEY"]:
            if key in os.environ:
                del os.environ[key]

    def tearDown(self):
        """Clean up after each test."""
        reset_config()

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test_key",
        "TAVILY_API_KEY": "tavily_key",
    })
    def test_config_from_env(self):
        """Test loading configuration from environment variables."""
        config = Config.from_env()
        self.assertEqual(config.openai_api_key, "test_key")
        self.assertEqual(config.tavily_api_key, "tavily_key")
        self.assertEqual(config.hard_cap, 800.0)
        self.assertEqual(config.max_steps, 15)

    @patch.dict(os.environ, {
        "GROQ_API_KEY": "groq_key",
        "TAVILY_API_KEY": "tavily_key",
        "HARD_CAP": "1000.0",
        "MAX_STEPS": "20",
    })
    def test_config_custom_values(self):
        """Test custom configuration values."""
        config = Config.from_env()
        self.assertEqual(config.groq_api_key, "groq_key")
        self.assertEqual(config.hard_cap, 1000.0)
        self.assertEqual(config.max_steps, 20)

    @patch.dict(os.environ, {}, clear=True)
    def test_config_missing_api_key(self):
        """Test validation fails without API keys."""
        with self.assertRaises(ConfigurationError):
            Config.from_env()

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test_key",
    })
    def test_config_missing_tavily_key(self):
        """Test validation fails without Tavily key."""
        with self.assertRaises(ConfigurationError):
            Config.from_env()

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test_key",
        "TAVILY_API_KEY": "tavily_key",
        "TEMPERATURE": "3.0",  # Invalid: > 2
    })
    def test_config_invalid_temperature(self):
        """Test validation fails with invalid temperature."""
        with self.assertRaises(ConfigurationError):
            Config.from_env()

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test_key",
        "TAVILY_API_KEY": "tavily_key",
        "MAX_STEPS": "150",  # Invalid: > 100
    })
    def test_config_invalid_max_steps(self):
        """Test validation fails with invalid max_steps."""
        with self.assertRaises(ConfigurationError):
            Config.from_env()

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test_key",
        "TAVILY_API_KEY": "tavily_key",
    })
    def test_has_api_credentials(self):
        """Test API credentials check."""
        config = Config.from_env()
        self.assertTrue(config.has_api_credentials())

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test_key",
        "TAVILY_API_KEY": "tavily_key",
    })
    def test_to_dict_excludes_sensitive(self):
        """Test that to_dict excludes sensitive data."""
        config = Config.from_env()
        config_dict = config.to_dict()
        
        # Should not contain actual keys
        self.assertNotIn("openai_api_key", config_dict)
        self.assertNotIn("tavily_api_key", config_dict)
        
        # Should contain boolean flags
        self.assertIn("has_openai_key", config_dict)
        self.assertTrue(config_dict["has_openai_key"])


class TestGlobalConfig(unittest.TestCase):
    """Test global configuration singleton."""

    def setUp(self):
        reset_config()

    def tearDown(self):
        reset_config()

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test_key",
        "TAVILY_API_KEY": "tavily_key",
    })
    def test_get_config_singleton(self):
        """Test that get_config returns singleton instance."""
        config1 = get_config()
        config2 = get_config()
        self.assertIs(config1, config2)

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test_key",
        "TAVILY_API_KEY": "tavily_key",
    })
    def test_reset_config(self):
        """Test that reset_config clears singleton."""
        config1 = get_config()
        reset_config()
        config2 = get_config()
        self.assertIsNot(config1, config2)


if __name__ == "__main__":
    unittest.main()
