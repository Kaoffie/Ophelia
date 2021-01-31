# pylint: skip-file

"""
English Strings.

All strings displayed to discord users will be taken from this file; all
logger messages are hardcoded and shouldn't be in here. There are a lot
of strings here that are so long that they exceed the character limit
per line according to the style guide but that's okay since it would be
really messy otherwise.

Pylint skips this file since this is more like a config file than actual
code. For PyCharm, a new scope for file:*_strings.py can be created to
exclude this file from line length warnings.
"""

"""'''''''''''
Command Errors
'''''''''''"""

# General Headers
command_error_header = "**Error:** "
command_error_logger_header = "Command error {} triggered by command: {}"
command_error_failed_to_send = "Failed to send user error message to channel {}: {}"

# General Errors
error_forbidden = "I was forbidden to execute the command."

# Command invocation exceptions
command_error_user_input_error = "User input error."
command_error_conversion_error = "Failed to convert argument."
command_error_bad_arugment = "Invalid argument."
command_error_bad_union_argument = "Invalid argument."
command_error_missing_required_arugment = "Missing required argument."
command_error_unexpected_quote_error = "Encountered unexpected quote mark inside non-quoted string."
command_error_invalid_end_of_quoted_string_error = "Invalid end of quoted string."
command_error_expected_closing_quote_error = "Did not find closing quote character."
command_error_private_message_only = "Command can only be executed in Private Message."
command_error_no_private_message = "Command cannot be used in Private Message."
command_error_invoke_error = "Command raised internal error."
command_error_too_many_arguments = "Too many arguments."
command_error_invalid_arguments = "Invalid arguments."
command_error_command_on_cooldown = "Command on cooldown. Please try again later."
command_error_not_owner = "Command can only be used by the bot owner."
command_error_message_not_found = "Could not find command message."
command_error_member_not_found = "Could not find member. Is your status set to invisible?"
command_error_user_not_found = "Could not find user. Is your status set to invisible?"
command_error_channel_not_found = "Could not find channel."
command_error_channel_not_readable = "Could not read channel."
command_error_role_not_found = "Could not find role."
command_error_emoji_not_found = "Could not find emoji."
command_error_partial_emoji_conversion_failure = "Failed to convert emoji."
command_error_bad_bool_argument = "Invalid boolean argment."
command_error_nsfw_channel_required = "Command can only be used in an NSFW channel."

# Exceptions with format params
command_error_missing_permissions = "You are missing the necessary permissions to run this command: {}."
command_error_bot_missing_permissions = "I am missing the necessary permissions to execute this command: {}."
command_error_missing_role = "You are missing the necessary roles to run this command: {}."
command_error_bot_missing_role = "I am missing the necessary roles to run this command: {}."
command_error_missing_any_roles = "You do not have any of the required roles to run this command: {}."
command_error_bot_missing_any_role = "I do not have any of the required roles to execute this command: {}."


"""'''''''''''''''
Configuration menu
'''''''''''''''"""

config_var_title = "Enter the {}."
config_var_desc = "{}"
config_var_footer = "Config step {}/{}"
config_try_again_title = "Invalid input! Please enter the {} again."
config_try_again_desc = "{} \n\nTries: {}/{}"


"""'''''''''''
Reaction Roles
'''''''''''"""

reactrole_add_role_header = "\n\n**(＋) Add Roles**\n\n{}"
reactrole_remove_role_header = "\n\n**(－) Remove Roles  **\n\n{}"
reactrole_add_role_confirm = "**Added Roles**: {}"
reactrole_remove_role_confirm = "**Removed Roles**: {}"

reactrole_dm_timeout_title = "Command timed out."
reactrole_dm_timeout_desc = "Please try again."
reactrole_cmd_exit_title = "Operation cancelled"
reactrole_cmd_exit_desc = "Exited role reaction configuration menu."
reactrole_cmd_invalid_arg_title = "Invalid Arguments"
reactrole_cmd_invalid_arg_desc = "Could not parse input."
reactrole_cmd_react_failed_title = "Failed to add reactions"
reactrole_cmd_react_failed_desc = "I failed to add the required reactions; maybe check if I have the necessary permissions to add reactions or use external emotes?"
reactrole_cmd_invalid_regex_title = "Invalid Regex"
reactrole_cmd_invalid_regex_desc = "Failed to compile regex."
reactrole_cmd_no_messages_found = "> No Messages Found"

reactrole_cmd_menu_title = "Reaction Role Config"
reactrole_cmd_menu_options = "**1** | Add Reaction Role\n**2** | Delete Reaction Roles from Message\n**3** | View Message Reaction Roles"

reactrole_cmd_add_reaction_title = "Add Reaction Roles"
reactrole_cmd_add_reaction_desc = "Enter Message ID. (Note that it might take a while for me to find the message)"
reactrole_cmd_add_type_title = "Select Reaction Type"
reactrole_cmd_add_type_desc = "Message ID: {}\nYou can either add normal reactions that assign or remove roles when a user adds or removes a reaction; you may also add reaction menus that send users DMs containing a list of roles that they can choose from.\n\n**1** | Reaction Roles\n**2** | DM Role Menu"
reactrole_cmd_add_simple_reaction_title = "Add Reaction Role"
reactrole_cmd_add_simple_reaction_desc = "You may use the following format to add multiple reactions and corresponding roles.\n\nNote that I can't use emotes from servers that I'm not in - you may external emotes later using the edit menu but they will be feature-incomplete. You may use either the emotes/emojis themselves or the emote IDs if you're using a custom emote.\n```\n<Emote 1>: <Role 1>\n<Emote 2>: <Role 2>\n...\n```"
reactrole_cmd_add_simple_confirm_title = "Added Reaction Roles"
reactrole_cmd_add_simple_confirm_desc = "**Reaction roles added:** {}\n**Invalid Inputs:** {}"
reactrole_cmd_add_dm_emote_title = "Add DM Role Menu"
reactrole_cmd_add_dm_emote_desc = "Enter an emote."
reactrole_cmd_add_dm_config_title = "Configure DM Role Menu"
reactrole_cmd_add_dm_config_desc = "Enter the parameters for the role menu in YAML format. For strings with multiple lines, surround them with quotes and use `\\n` for line breaks. \n```\ndm_msg: \ndm_regex: \ndm_roles\n  -<role_id>\n```"
reactrole_cmd_add_dm_config_confirm_title = "Added DM Role!"
reactrole_cmd_add_dm_config_confirm_desc = "Successfully added DM role with the following arguments: \n```\n{}\n```"

reactrole_cmd_delete_reaction_title = "Delete Reaction Roles from Message"
reactrole_cmd_delete_reaction_desc = "__**Retrievable Message IDs**__\nEnter a message ID to delete all associated reaction roles. To delete a single reaction role, simply remove my reaction from a message.\n\n{}\n\n__**Non-retrievable Message IDs**__\nThese messages have been configured for reaction roles, but they could not be fetched from the server, either because they were deleted or I no longer have the permissions to view them. Selecting these messages will bring you directly to the invalid message deletion dialog.\n\n{}"
reactrole_cmd_delete_message_title = "Delete Reaction Roles from Message"
reactrole_cmd_delete_message_desc = "Are you sure you want to delete all the reaction roles from {}?\nThis message contains {} reaction{}.\n\n**Y** | Yes\n**N** | No"
reactrole_cmd_delete_confirm_title = "Deleted message reaction roles"
reactrole_cmd_delete_confirm_desc = "Successfully deleted all reaction role configuration parameters for given message."

reactrole_cmd_view_reaction_title = "View Message Reaction Role Configuration"
reactrole_cmd_view_reaction_desc = "__**Retrievable Message IDs**__\nEnter a message ID to view.\n\n{}\n\n__**Non-retrievable Message IDs**__\nThese messages have been configured for reaction roles, but they could not be fetched from the server, either because they were deleted or I no longer have the permissions to view them. Selecting these messages will bring you directly to the invalid message deletion dialog.\n\n{}"
reactrole_cmd_view_yaml_title = "Viewing Message Reaction Role Configuration"
reactrole_cmd_view_yaml_desc = "Raw YAML format:```\n{}\n```"

reactrole_cmd_delete_invalid_message_title = "Delete invalid message reaction roles"
reactrole_cmd_delete_invalid_message_desc = "I cannot reach this message ({}) with {} reaction{}, but it has been recorded in the reaction roles config. Should I delete it?\n\n**Y** | Yes\n**N** | No"
reactrole_cmd_delete_invalid_confirm_title = "Deleted message reaction roles"
reactrole_cmd_delete_invalid_confirm_desc = "Successfully deleted all reaction role configuration parameters for given message."


"""'''
Events
'''"""

events_embed_text = "{}\n\n**Time:**\n%TIME%"
events_recurring_embed_text = "{}\n\n**Event Repeats**:\nEvery {} days\n\n**Time:**\n%TIME%"
events_embed_ongoing = "{}"
events_time_footer = "Your timezone"
events_ongoing_message = "{}"
events_dm_notif = "{}"
events_delete = "Upcoming event deleted (This will also occur when an event starts):"
events_approval = "Event from {} awaiting approval.\n\n**Description:**\n{}\n\n**DM Notification Message:**\n{}\n\n**Notification Time** (Minutes before event start):\n{}"
events_recurring_approval = "Recurring event from {} awaiting approval.\n\nNote that recurring events were not designed to be used by non-staff.\n\n**Description:**\n{}\n\n**Queue Channel:**\n{}\n\n**Target Channel:**\n{}\n\n**DM Notification Message:**\n{}\n\n**Notification Time** (Minutes before event start):\n{}\n\n**Repetition Interval (Days):**\n{}\n\n**Event Time:**"

events_approval_error_title = "Failed to approve event"
events_approval_error_desc = "Ophelia failed to approve {}. Maybe I don't have the permissions to post embeds in {}?"

events_approval_dm_error_title = "Failed to send approval DM"
events_approval_dm_error_desc = "Ophelia has approved {} but couldn't DM the event organizer, {}."
events_rejection_dm_error_title = "Failed to send rejection DM"
events_rejection_dm_error_desc = "Ophelia has rejected {} but couldn't DM the event organizer, {}."

events_recurring_error_title = "Failed to post new message for recurring event"
events_recurring_error_desc = "Event: {}"

events_title = "Events Module"
events_desc = "**Subcommands**\n\n> `add` Add event\n> `edit` Edit event\n> `delete` Delete event\n\n**Admin Subcommands**\n\n> `addr` Add recurring event\n> `listall` List all events\n> `forcedel` Force delete an event\n> `save` Save events to database"

events_edit_title = "Event Edit"
events_edit_desc = "**Title**\n{} → {}\n\n**Time**\n{} → {}\n\n**Old Description**\n{}\n\n**New Description**\n{}"
events_no_change = "No Change"
events_edit_approval_dm_error_title = "Failed to send edit approval DM"
events_edit_approval_dm_error_desc = "Ophelia has approved an edit to {} but couldn't DM the event organizer, {}."
events_edit_rejection_dm_error_title = "Failed to send edit rejection DM"
events_edit_rejection_dm_error_desc = "Ophelia has rejected an edit to {} but couldn't DM the event organizer, {}."

events_save_title = "Saved event log."
events_save_desc = "The events and event log configurations have been saved to the backup database."

events_subscribe = "\u23f0 Subscribed to event notifications for {}!"
events_unsubscribe = "\u274c Unsubscribed from event notifications for {}!"

events_vars = "Variable placeholders:\n```\n%NAME%         Organizer display name\n%TITLE%        Title of event\n%DESC%         Description of event\n%PING%         Organizer ping\n%DM_MSG%       DM Message\n```"
events_notif_vars = "Variable placeholders:\n```\n%NAME%         Organizer display name\n%TITLE%        Title of event\n%DESC%         Description of event\n%PING%         Organizer ping\n%DM_MSG%       DM Message\n%NOTIF_NAME%   Notification target name\n```"

events_cmd_exit_title = "Exited events menu"
events_cmd_exit_desc = "Command exited manually or timed out."
events_no_guild_title = "Invalid guild"
events_no_guild_desc = "The events module has not been set up for this server!"
events_not_staff_title = "Insufficient permissions!"
events_not_staff_desc = "You do not have the staff role required to use this command."
events_guild_event_invalid_title = "Invalid Guild Configuration"
events_guild_event_invalid_desc = "Failed to set up guild configuration with given settings."
events_no_events_title = "Could not find any events"
events_no_events_desc = "Could not find any events initiated by you in the list of events!\n\nNote that while all events (including those pending approval) can be deleted, only upcoming events can be edited."

events_setup_title = "Events Setup Menu"
events_setup_desc = "This menu will take you through the event calendar setup process. \n\nIf this is not the first time running this command in this server, your events will be carried over from your previous settings and all event calendar embeds will be resent.\n\nTo reconfigure the event module settings, simply type the setup command again.\n\nDO NOT run this command if there is an ongoing event."
events_setup_staff_role = "Role required for users to approve/reject new events and event edits."
events_setup_approval_channel = "Channel where all events pending approval are sent to."
events_setup_calendar_channel = "Channel where all events are posted to after being approved."
events_setup_accept_template = f"Event acceptance DM sent to event organizer. For instance, 'Your event has been accepted!' \n\n{events_vars}"
events_setup_reject_template = f"Event rejection DM sent to event orgnizer. \n\n{events_vars}"
events_setup_accept_edit_template = f"Event edit acceptance DM sent to event organizer. \n\n{events_vars}"
events_setup_reject_edit_template = f"Event edit rejection DM sent to event organizer. \n\n{events_vars}"
events_setup_dm_template = f"Event DM notification template sent to everyone who subscribed to the event. \n\n{events_notif_vars}"
events_setup_organizer_dm_template = f"DM notification sent to organizer before their event starts. \n\n{events_vars}"
events_setup_ongoing_template = f"Ongoing event announcement template, posted to the calendar channel when an event is about to start. \n\n{events_vars}"
events_setup_event_timeout = "How long it takes for an ongoing event to end (in **seconds**) if the organizer doesn't end the event themselves."
events_setup_success_title = "Successfully set up events module!"
events_setup_success_desc = "You may now use the events module on this server to organize and manage the event calendar."

events_add_title = "Submit an event!"
events_add_desc = "This menu will take you through the event submission process."
events_add_event_title = "Name of the event."
events_add_event_desc = "Event description: What is your event about? Where will it be held? Are there any entry requirements? How many people are you expecting?"
events_add_event_image = "Add an event banner or image **__URL__** if you have one; make sure it starts with **__http__** or **__https__**! If you don't have a banner, just type 'None'."
events_add_event_dm_msg = "Notifications are sent out to event subscribers before the event starts. What do you want to include in the notification message?"
events_add_event_start_time = "Enter the **__UNIX Timestamp__** of your event time. \n\nConvert here: https://kaoffie.github.io/timestamp/"
events_add_event_notif_min_before = "How many minutes before the event do you want to notify everyone who subscribed to your event? (Maximum: 120 Minutes)"
events_add_fail_title = "Failed to submit event."
events_add_fail_desc = "Perhaps something was configured wrongly?"
events_add_success = "**Your event has been sent for staff approval!**\nI'll inform you when your event is approved or rejected."
events_add_approved = "**Event approved!**"
events_add_rejected = "**Event rejected!**"

events_add_recurring_title = "Submit a recurring event!"
events_add_recurring_desc = "This menu will take you through the recurring event submission process."
events_add_recurring_queue_channel = "Channel to extract content from. \n\nEvery predefined interval, the bot will extract the content from the oldest message in this channel and post it in the target channel."
events_add_recurring_target_channel = "Recurring event target post channel."
events_add_recurring_post_template = "Post template. Use the `%CONTENT%` flag to represent the content extracted from the queue channel."
events_add_recurring_post_embed = "Post embed, expressed as a dictionary (JSON format). Use the `%CONTENT%` flag to represent the content extracted from the queue channel. Type `None` if you don't want to include an embed."
events_add_recurring_repeat_interval = "How often should the event repeat (in days)?"

events_add_edit_title = "Edit an event!"
events_add_edit_desc = "Select an event to edit.\n\n{}"
events_edit_menu_title = "Edit an event!"
events_edit_menu_desc = "This menu will bring you through all the event edit options."
events_add_edit_new_title = "New event title, or 'None' if you'd like to keep the old title."
events_add_edit_new_desc = "New event description, or 'None' if you'd like to keep the old description."
events_add_edit_new_image = "New image URL (stating with http or https), or 'None' if you'd like to keep the old image."
events_add_edit_new_start_time = "Enter the new event time **__UNIX Timestamp__**, or '0' if you'd like to keep the old time.\n\nConvert here: https://kaoffie.github.io/timestamp/"
events_edit_success = "Successfully submitted event edit. Details:"
events_edit_approved = "**Edit Approved!**"
events_edit_rejected = "**Edit Rejected!**"

events_delete_title = "Delete an event!"
events_delete_desc = "Select an event to delete.\n\n{}"
events_delete_confirm_title = "Event deleted."
events_delete_confirm_desc = "Your event has been deleted from the event calendar."

events_listall_title = "Events list"
events_listall_desc = "**Approval List**\n{}\n\n**Upcoming List**\n{}\n\n**Ongoing List**\n{}"

events_forcedelete_no_args_title = "Insufficient arguments."
events_forcedelete_no_args_desc = "Enter the event ID! You can find a list using the `event listall` command."
events_forcedelete_not_int_title = "Invalid event ID"
events_forcedelete_not_int_desc = "That is not a valid event ID."
events_forcedelete_title = "Force deleted."
events_forcedelete_desc = "Please check `event listall` if the event you tried to delete has been properly deleted. Use `event save` to save all event configurations."


"""'''''''
Voicerooms
'''''''"""

voicerooms_room_format = "{}'s Room"
voicerooms_topic_format = "Owner: {}"
voicerooms_commands_title = "Voice Room Commands"
voicerooms_commands_desc = "`%PREFIX%vc public` Make room public\n`%PREFIX%vc private` Make room private\n`%PREFIX%vc end` End call and delete room\n\n`%PREFIX%vc add` Add member or role to room (e.g. `%PREFIX%vc add John`)\n`%PREFIX%vc remove` Remove member or role from room (e.g. `%PREFIX%vc remove Moderator`)\n\n`%PREFIX%vc name` Rename room\n`%PREFIX%vc size` Set room size\n`%PREFIX%vc bitrate` Set room bitrate\n`%PREFIX%vc transfer` Transfer room ownership"
voicerooms_welcome_message = "{}\n**Voice Room Commands**\n\n> `%PREFIX%vc public` Make room public\n> `%PREFIX%vc private` Make room private\n> `%PREFIX%vc end` End call and delete room\n> \n> `%PREFIX%vc add` Add member or role to room (e.g. `%PREFIX%vc add John`)\n> `%PREFIX%vc remove` Remove member or role from room (e.g. `%PREFIX%vc remove Moderator`)\n> \n> `%PREFIX%vc name` Rename room\n> `%PREFIX%vc size` Set room size\n> `%PREFIX%vc bitrate` Set room bitrate\n> `%PREFIX%vc transfer` Transfer room ownership"
voicerooms_timeout_title = "Timed out!"
voicerooms_timeout_desc = "You took too long to give a response."

voicerooms_generator_title = "Create Room Generator"
voicerooms_generator_desc = "Before configuring the generator, ensure that there is a **Sample Text Channel** and **Sample Voice Channel** that I can copy the default permissions from. In the sample channels, any permissions you assign to **yourself** will be assigned to the owner of any custom channels."
voicerooms_generator_voice_category = "Category ID that new voice channels are created in."
voicerooms_generator_text_category = "Category ID that new text channels are created in."
voicerooms_generator_generator_channel = "Voice channel ID of generator channel."
voicerooms_generator_sample_voice_channel = "Voice channel (ID) to copy permissions from; permissions assigned to **you** will be assigned to future channel owners.\n\nNote that the permissions will only be copied once; after this configuration, you can delete the sample channel."
voicerooms_generator_sample_text_channel = "Text channel (ID) to copy permissions from; permissions assigned to **you** will be assigned to future channel owners.\n\nNote that the permissions will only be copied once; after this configuration, you can delete the sample channel."
voicerooms_generator_log_channel = "Log channel for all text channel messages."
voicerooms_generator_success_title = "Created new generator."
voicerooms_generator_success_desc = "You may now create temporary voice channels by joining {}."

voicerooms_log_header = "__**#{channel}:** {name} ({id})__"
voicerooms_log_tail = "{}"
voicerooms_log_attachments = "**Attachments: ** {}"

voicerooms_error_not_channel_id_title = "Could not parse channel ID"
voicerooms_error_not_channel_id_desc = "Argument was not in the format of a channel ID."
voicerooms_error_invalid_channel_title = "Invalid Channel"
voicerooms_error_invalid_channel_desc = "Could not find generator with the given ID!"

voicerooms_list_item = "{} | {}"
voicerooms_list_none = "Invalid Channel"
voicerooms_list_title = "Server Generators"
voicerooms_listall_title = "All Generators"
voicerooms_delete_success_title = "Deleted Generator"
voicerooms_delete_success_desc = "Generator successfully deleted."

voicerooms_no_room_title = "No rooms found."
voicerooms_no_room_desc = "You are not the owner of any voice room!"

voicerooms_public_title = "Set room to Public."
voicerooms_public_desc = "Everyone can now join your room."
voicerooms_private_title = "Set room to Private."
voicerooms_private_desc = "Use `%PREFIX%vc add` and `%PREFIX%vc remove` to add or remove users or roles to your private room."
voicerooms_ratelimited_title = "Slow down!"
voicerooms_ratelimited_desc = "Discord doesn't let me change the name of a channel or update the VC room owner more than 2 times every 10 minutes. Please try again later!"
voicerooms_name_invalid_title = "Invalid name"
voicerooms_name_invalid_desc = "Pick a different room name!"
voicerooms_name_title = "Room name updated"
voicerooms_name_desc = "New name: {}"
voicerooms_add_title = "Added to room:"
voicerooms_add_desc = "{} successfully added. Note that this only works in private rooms! Use `%PREFIX%vc private` to switch to private mode."
voicerooms_remove_title = "Removed from room:"
voicerooms_remove_desc = "{} successfully removed. Note that this only works in private rooms! Use `%PREFIX%vc private` to switch to private mode."
voicerooms_size_invalid_title = "Invalid size!"
voicerooms_size_invalid_desc = "Room size has to be from 1 to 99 users; set room size to 0 to remove the user limit."
voicerooms_size_title = "Room size updated"
voicerooms_size_desc = "Set room size to 0 to remove the user limit."
voicerooms_bitrate_invalid_title = "Invalid bitrate!"
voicerooms_bitrate_invalid_desc = "Bitrate should be between 8 and 96 (384 for boosted servers)"
voicerooms_bitrate_title = "Bitrate updated"
voicerooms_bitrate_desc = "Bitrate updated to {} kbps"
voicerooms_transfer_bot_title = "Invalid member"
voicerooms_transfer_bot_desc = "You cannot transfer a room to a bot!"
voicerooms_transfer_bad_old_owner = "Member does not own a room!"
voicerooms_transfer_bad_owner_title = "Member not in channel"
voicerooms_transfer_bad_owner_desc = "You can only transfer ownership of this room to users who are connected to the room."
voicerooms_transfer_already_owner_title = "Member is an owner of another voice channel"
voicerooms_transfer_already_owner_desc = "This member is already the owner of another room!"
voicerooms_transfer_title = "Room transfered"
voicerooms_transfer_desc = "New owner: {}"

voicerooms_filter_list_title = "Room Name Filters"
voicerooms_filter_list_desc = "Use `%PREFIX%vc filter <regex>` to add or remove a filter. Rooms names that match these filters will be rejected.\n\n{}"
voicerooms_filter_regex_error_title = "Regex failed to compile"
voicerooms_filter_regex_error_desc = "Failed to add regex filter."
voicerooms_filter_added_title = "Added regex filter"
voicerooms_filter_added_desc = "New room name regex filter: `{}`"
voicerooms_filter_deleted_title = "Removed regex filter"
voicerooms_filter_deleted_desc = "Removed room name regex filter: `{}`"


"""'''''''
Boostroles
'''''''"""

boostroles_wait_title = "Syncing Boost Roles"
boostroles_wait_desc = "This will take a while..."
boostroles_list_full_item = "・{status} {role} from {booster} given to {target}"
boostroles_list_item = "・{status} {role} for {booster}"
boostroles_status_true = "\u2705"
boostroles_status_false = "\u274c"

boostroles_title = "Boostroles Subcommands"
boostroles_desc = "`%PREFIX%boost setup <reference role> <staff role>` Setup or reconfigure boost roles\n`%PREFIX%boost list` List and sync all boost roles\n`%PREFIX%boost link <booster> <role> [target]` Link a role to a user's boost status\n`%PREFIX%boost add <booster> <target> <colour> <name>` Add a new boost role"

boostroles_no_booster_role_title = "Could not find any booster roles!"
boostroles_no_booster_role_desc = "I couldn't find the server booster role (The pink one)."
boostroles_setup_success_title = "Successfully set up boost roles!"
boostroles_setup_success_desc = "Check out a list of subcommands using `%PREFIX%boost`."
boostroles_update_success_title = "Succesfully updated boost role settings!"
boostroles_update_success_desc = "Check out a list of subcommands using `%PREFIX%boost`."

boostroles_add_error_title = "Failed to add role."
boostroles_add_error_desc = "Please try again! (Also check if I've left any residue roles in the role list)"
boostroles_add_success_title = "Successfully added role!"
boostroles_add_success_desc = "Added role: {}"

boostroles_link_success_title = "Linked boost roles"
boostroles_link_success_desc = "Use the `%PREFIX%boost list` command to view and sync all boost roles."
boostroles_list_title = "Server boost roles"
boostroles_list_desc = "{}"
