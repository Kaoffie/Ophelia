"""
Event Calendar Module.

The event calendar channel is how the Events cog shows upcoming events
to users. It is configured per server, with two types of events - member
events, and recurring events.

Member events are initiated by members and approved by moderators in
an approval channel, while recurring events, which though can be set up
to be useable by everyone, is designed for use by staff and automates
events that involves sending a message from a queue to a target channel.
"""
