"""
Voicerooms Configuration module.

Contains the options required to set up a voiceroom generator.
"""


from typing import List

from ophelia.output import ConfigItem, disp_str
from ophelia.utils.discord_utils import (
    extract_category_config, extract_text_config,
    extract_voice_config
)


VOICEROOMS_GENERATOR_CONFIG: List[ConfigItem] = []
for category in ["voice_category", "text_category"]:
    VOICEROOMS_GENERATOR_CONFIG.append(ConfigItem(
        category,
        disp_str(f"voicerooms_generator_{category}"),
        extract_category_config
    ))

for voice_channel in ["generator_channel", "sample_voice_channel"]:
    VOICEROOMS_GENERATOR_CONFIG.append(ConfigItem(
        voice_channel,
        disp_str(f"voicerooms_generator_{voice_channel}"),
        extract_voice_config
    ))

for text_channel in ["sample_text_channel", "log_channel"]:
    VOICEROOMS_GENERATOR_CONFIG.append(ConfigItem(
        text_channel,
        disp_str(f"voicerooms_generator_{text_channel}"),
        extract_text_config
    ))
