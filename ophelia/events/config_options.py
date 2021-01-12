"""
Events configuration options module.

Contains configuration steps for setting up the events module in a
server, as well as the steps for adding and editing an event.
"""
import copy
from typing import List

from ophelia.output import ConfigItem, disp_str
from ophelia.utils.discord_utils import (
    extract_role_config,
    extract_text_config, get_channel_id
)
from ophelia.utils.text_utils import (
    bounded_intify, intify, nonify, nonify_link,
    optional_time_bounded_intify, stringify, time_bounded_intify
)

NOTIFY_MAX_MINUTES = 120

"""''''''''''''''''''
BASE_ADD_CONFIG_ITEMS
''''''''''''''''''"""
# Shared event config options

BASE_ADD_CONFIG_ITEMS: List[ConfigItem] = []
for item in ["title", "desc", "dm_msg"]:
    BASE_ADD_CONFIG_ITEMS.append(ConfigItem(
        item,
        disp_str(f"events_add_event_{item}"),
        stringify
    ))

BASE_ADD_CONFIG_ITEMS.append(ConfigItem(
    "image",
    disp_str("events_add_event_image"),
    nonify_link
))


# Recurring event base options

BASE_RECURRING_CONFIG_ITEMS = copy.copy(BASE_ADD_CONFIG_ITEMS)
for item in ["queue_channel", "target_channel"]:
    BASE_RECURRING_CONFIG_ITEMS.append(ConfigItem(
        item,
        disp_str(f"events_add_recurring_{item}"),
        get_channel_id
    ))

BASE_RECURRING_CONFIG_ITEMS += [
    ConfigItem(
        "post_template",
        disp_str("events_add_recurring_post_template"),
        stringify
    ),
    ConfigItem(
        "post_embed",
        disp_str("events_add_recurring_post_embed"),
        nonify
    ),
    ConfigItem(
        "repeat_interval",
        disp_str("events_add_recurring_repeat_interval"),
        bounded_intify(minimum=1)
    )
]


# Guild event calendar setup config options

SETUP_CONFIG_ITEMS = [
    ConfigItem(
        "staff_role",
        disp_str("events_setup_staff_role"),
        extract_role_config
    )
]

# Channels
for channel in ["approval_channel", "calendar_channel"]:
    SETUP_CONFIG_ITEMS.append(ConfigItem(
        channel,
        disp_str(f"events_setup_{channel}"),
        extract_text_config
    ))

# Templates
for template in [
    "accept_template",
    "reject_template",
    "accept_edit_template",
    "reject_edit_template",
    "dm_template",
    "organizer_dm_template",
    "ongoing_template"
]:
    SETUP_CONFIG_ITEMS.append(ConfigItem(
        template,
        disp_str(f"events_setup_{template}"),
        stringify
    ))

# Skipping event and edit lists, configuring timeout:
SETUP_CONFIG_ITEMS.append(ConfigItem(
    "event_timeout",
    disp_str("events_setup_event_timeout"),
    intify
))


# Event edit base config items

BASE_EDIT_CONFIG_ITEMS: List[ConfigItem] = []
for item in ["new_title", "new_desc", "new_image"]:
    BASE_EDIT_CONFIG_ITEMS.append(ConfigItem(
        item,
        disp_str(f"events_add_edit_{item}"),
        nonify
    ))


async def add_event_time_params(
        copy_from: List[ConfigItem]
) -> List[ConfigItem]:
    """
    Get a list of event add config items.

    The reason why this is done separately is because everytime
    someone submits a new event, we have to readjust the minimum
    time.

    :param copy_from: Base config items to copy from
    :return: List of config items for adding a member event
    """
    add_items = copy.copy(copy_from)

    add_items += [
        ConfigItem(
            "start_time",
            disp_str("events_add_event_start_time"),
            time_bounded_intify
        ),
        ConfigItem(
            "notif_min_before",
            disp_str("events_add_event_notif_min_before"),
            bounded_intify(
                minimum=0,
                maximum=NOTIFY_MAX_MINUTES
            )
        )
    ]

    return add_items


async def add_edit_time_params(
        copy_from: List[ConfigItem]
) -> List[ConfigItem]:
    """
    Get a list of event edit config items.

    All we're doing here is adding the final config item with an
    updated minimum time.

    :param copy_from: Base config items to copy from
    :return: List of config items for submitting an event edit
    """
    edit_items = copy.copy(copy_from)
    edit_items.append(
        ConfigItem(
            "new_start_time",
            disp_str("events_add_edit_new_start_time"),
            optional_time_bounded_intify
        )
    )

    return edit_items
