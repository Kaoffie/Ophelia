# Ophelia

Modules

- Reaction Roles
- Server Event Calendar
- Custom VC Rooms
- Server Boost Roles

(March 2022): This bot was written in 2020, back when slash commands weren't widespread and message/member intents weren't enforced. Discord has changed a lot since then, and a lot of the tasks this bot was created to do can now be done with built-in Discord features.

I'm still maintaining the bot to ensure that it works on newer versions of the Discord API, but there are no plans to add new features or edit existing ones because I don't have any time. Feel free to submit pull requests though.

If the opportunity arises, I might rewrite the bot, but it's been a few years since I've had that much free time and motivation to rewrite something.

---

## Reactrole

Reactrole was designed for servers that have way too many roles to make a traditional role reaction menu to look neat. It solves this problem by creating an "Other" option that DMs all selected roles to a user so that they may choose what to assign or remove there.

#### Commands
**`&reactrole`**: Reactrole configuration menu

---

## Events

The events module was designed to facilitate community events by creating a event calendar that is accessible by members (subject to staff approval). Members can initiate their own events and subscribe to other events to receive notifications when they start.

#### Commands
`&event` List all event subcommands

---

## VC Rooms

Custom VC + Text channel pairs created by users. This isn't a new concept, but all the existing bots either have limited feature sets or really annoying messages telling you to vote or pay for their premium features.

#### Commands

- `&vc list` List all rooms or request for private room access
- `&vc public` Set room to public mode
- `&vc joinmute <seconds>` Set room to joinmute mode (New users will be temporarily muted)
- `&vc private` Set room to private mode
- `&vc end` End call and delete room
- `&vc add` Add member or role to room (e.g. `&vc add John`)
- `&vc remove` Remove member or role from room (e.g. `&vc remove Moderator`)
- `&vc mute` Mute member
- `&vc unmute` Unmute member 
- `&vc name` Rename room
- `&vc size` Set room size
- `&vc bitrate` Set room bitrate
- `&vc transfer` Transfer room ownership
- `&vc setup` Set up VC room generator
- `&vc listall` List all VC room generators
- `&vc admindel` Delete a VC room generator
- `&vc filter` Add/Remove/List VC room name filters
---

## Boostroles

For tracking and updating server boost reward roles.

#### Commands

- `&boost setup <reference role> <staff role>` Setup or reconfigure boost roles
- `&boost list` List and sync all boost roles
- `&boost sync` Same command as above
- `&boost link <booster> <role> [target]` Link a role to a user's boost status
- `&boost add <booster> <target> <colour> <name>` Add a new boost role





