# pylint: skip-file
"""
This is the settings file.

Rename this file to "settings.py" before configuring.

========================================================================
Log levels:

5  | Trace    | All debug messages, including every step in every
              | function, used to test program logic and to pinpoint
              | the exact locations where things go wrong.

10 | Debug    | Important debug messages showing results of certain
              | computations without necessarily showing intermediate
              | steps.

20 | Info     | All information that might be necessary for the user
              | to monitor what the bot is doing.

30 | Warning  | Errors or things that go wrong that are not the result
              | of incorrect configuration or code; these do not affect
              | the bot's functionality.

40 | Error    | Errors that occur due to incorrect configuration or user
              | input that may impact the execution of a specific
              | command; these do not affect the bot's functionality.

50 | Critical | Unexpected errors that either impact an entire cog or
              | feature or the functionality of the entire bot.

60 | Nothing  | No messages at all.


For example, setting the log level to 40 would mean receiving both error
and critical logs. The master log is a Discord channel dedicated for bot
logs (without accessing the console).
"""

# Command prefix
command_prefix = "&"

# Bot Description (Shown in help)
bot_description = "Ophelia: Automoderator bot written by Kaoffie using Pycord"

# Discord bot token
bot_token = ""

# Bot owner user IDs (Set of ints)
bot_owners = {}

# Master log channel ID (Leave as 0 for no logs)
master_log_channel = 0

# Log level
master_log_level = 30
console_log_level = 20

# Embed colours
embed_color_normal = 0xa0e0f0
embed_color_warning = 0xe3ed1c
embed_color_success = 0x2ded43
embed_color_error = 0xff2b4b
embed_color_unimportant = 0xbaccdb
embed_color_important = 0x2d70ed

# File paths
file_events_db = "./resources/events/event_db.yml"
file_reactrole_config = "./resources/reactrole/reactrole.yml"
file_voicerooms_config = "./resources/voicerooms/voicerooms.yml"
file_voicerooms_filter_config = "./resources/voicerooms/filters.yml"
file_boostroles_config = "./resources/boostroles/boostroles.yml"

# Config timeouts
short_timeout = 15.0
long_timeout = 180.0
max_tries = 3

# Timers
config_save_interval_minutes = 60.0
events_check_interval_minutes = 5.0

# New member threshold in seconds (Default is 1 day, used for caching)
new_member_threshold = 86400

# Max cache size
max_cache_size = 300

# Voicerooms
voiceroom_buffer_size = 5
voiceroom_empty_timeout = 5.0
voiceroom_mute_button_timeout = 900.0
voiceroom_max_mute_time = 300

# Substring spam limits
substring_hard_limit = 4000
substring_stop_limit = 2000
substring_min_len = 3
substring_max_len = 1000
