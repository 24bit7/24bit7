"""
Multiroom (experimental, stage one, 9 Nov 2026): the Speakers follow the Sonos.

The Sonos leads: JRiver plays to it as usual. The follower reads the Sonos's millisecond position over its local
websocket, fetches the same track from JRiver's Multiroom DLNA server with plain HTTP range reads, and hands each
sample to the Speakers' DAC at the moment the Sonos plays it. The design is mockups/multiroom_design.html; the plan
for this stage is mockups/multiroom_stage1_plan.md.
"""
