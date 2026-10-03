# How Voice Commands work

Voice Commands let you ask for music out loud. Say "Alexa, ask needle drop for music like Agnes Obel" in the kitchen, and a playlist built from your own library starts on the kitchen speaker a second or two later.

It works through an Alexa skill of your own, which you set up once. That part is not a one-click job, and [Setting up the Alexa skill](VOICE_SETUP.md) takes you through it step by step. This page explains what Voice Commands do once they're running. 24bit7 works fully without them.

---

## How it fits together

```mermaid
flowchart LR
    A["Alexa device<br/>'ask needle drop for...'"] --> B["Your Alexa skill<br/>(hosted by Amazon)"]
    B -->|"HTTPS, with your key"| C["Tailscale Funnel<br/>your-pc.your-tailnet.ts.net"]
    C --> D["24bit7<br/>on your PC"]
    D --> E["JRiver zone<br/>for that device"]
```

- The **skill** runs on Amazon. It hears the command and sends it, with a secret key and the ID of the device that heard it, to your PC's address on the internet.
- **Tailscale Funnel** gives your PC that address and passes the request through to 24bit7. Your router needs no changes.
- **24bit7** checks the key, looks up which zone that device plays to and which settings it uses, then builds or plays the music there.

## What you can say

Open the skill first ("Alexa, open needle drop"), then say the command, or say it all in one breath: "Alexa, ask needle drop for music like Agnes Obel".

| Say | You get |
|---|---|
| "songs by *artist*" | Artist's Top Tracks |
| "music like *artist*" | Similar Artists, seeded from the artist's most popular track |
| "tracks like *song*", or "tracks like *song* by *artist*" | Similar Tracks |
| "genre *anything*", such as "genre nu metal with grunge" | AI Playlist (needs an Anthropic key in 24bit7) |
| "album *name*" | Plays the album now, in track order |
| "song *title*" | Plays the song now, then stops |
| "playlist *name*" | Plays one of your JRiver playlists or smartlists now, with its settings from Settings > JRiver Playlists |
| "shuffle songs by *artist*" | Every track by the artist in your library, shuffled, opening on one of their best known songs |
| "skip", "next" or "next song" | The next track in that device's zone |
| "who is this" or "what's playing" | Alexa says the track, artist and album playing in that device's zone |
| "more like this" or "more of this" | Similar Tracks seeded from what's playing. The current track carries on and the new playlist replaces what was queued after it |

When several albums or songs share a title, Alexa asks which artist, and you answer "by *artist*".

When two playlists share a name (a "Vocal Jazz" smartlist and a "Vocal Jazz" playlist, say), Alexa asks which: "You have two called Vocal Jazz: the smartlist in Random Album, and the playlist at the top level. Say by smartlist, or by playlist." If both are the same type, she names the folders instead, and you answer "by" and the folder. To skip the question, say it up front: "playlist vocal jazz smartlist".

No command starts with "play". Alexa tends to hand anything starting with "play" to a music service instead of the skill, so the skill avoids the word.

Skip, who is this and more like this always need the skill's name: "Alexa, ask needle drop to skip". A plain "Alexa, skip" goes to the speaker itself, and a speaker playing a JRiver zone has no queue of its own, so a Sonos answers that it can't skip on this stream. If you want a shorter phrase, an Alexa Routine can do it: set a phrase such as "next song" and give it the custom action "ask needle drop to skip".

The skill name is up to you. This one is "needle drop" because Alexa kept mishearing the first choice. An Alexa Routine can shorten "open needle drop" to a phrase of your own.

## What you hear

- **"Ready."** when the skill opens and is waiting for a command.
- **A short tone** when a command is accepted. There's nothing more to say: the music follows almost at once.
- **"Please wait, request pending."** if another playlist is still being built. Yours runs as soon as that one finishes.
- **"That's *track* by *artist*, from *album*."** after "who is this". Version tags such as "Remastered" or "From the ... Soundtrack" are left out, and a compilation tagged with the series as the artist and "Artist - Title" as the name is read as the real artist and title.
- **"Nothing's playing on *zone*."** after skip, who is this or more like this when that zone is stopped, and **"Nothing to skip to."** on the last track in Playing Now.
- **A spoken explanation** when something is wrong, such as a device that hasn't been given a zone yet. The troubleshooting table in the setup guide lists each one.

## Why the music starts so quickly

Building a playlist can take anywhere from a few seconds to half a minute, depending on how many sources 24bit7 asks. With nothing playing in the zone, 24bit7 doesn't wait for the whole list: the first track it finds starts straight away, and the rest follows it into Playing Now as it's found. This is called fast start, and it's always on.

If something is already playing, it carries on, and the new playlist queues up behind it.

Albums, songs, playlists and shuffles need no building, so they replace whatever is playing at once.

## Keeping it going

With **Non-stop** ticked for a Play option (on its tab under Settings > Playlist), a playlist a voice command built doesn't end: when its last track starts, more are added. "Shuffle songs by" carries on the same way once the shuffle runs out, from the artist's most popular track. Your own JRiver playlists can keep going too, set per playlist under Settings > JRiver Playlists. Albums and songs end as normal.

## Your JRiver playlists

**Settings > JRiver Playlists** decides how each of your playlists and smartlists plays when you ask for it by voice:

- **Shuffle**, off by default, so a playlist plays in its saved order unless you tick it.
- **Non-stop**: No, Similar artists or Similar tracks, from the **Reseed from** track (last or 2nd).
- **Skip recent**: leave out tracks played in the last few days. It never empties a playlist; if everything was played recently, the whole playlist plays and the log says why.

Tick **Use the same settings for every playlist** to set them all at once, or untick it and give each playlist its own row. The table shows each playlist's folder and whether it's a smartlist, sorts by folder or name, and can show one folder at a time. It re-reads your playlists from JRiver each time you open it. A playlist with nothing changed plays exactly as JRiver has it.

## Devices and their settings

Every Alexa device that has spoken to 24bit7 appears under **Settings > Voice Commands > Devices**, the first time it's used. Give it a name and choose the JRiver zone it plays to, and from then on that device's commands play in that zone: the kitchen speaker in the kitchen, the lounge Dot in the lounge.

By default, every device uses the same settings as the Windows app, called **Windows (Main)**. A device can have settings of its own instead:

1. Under **Settings > Voice Commands > Devices**, tick **Own settings** for the device.
2. **Settings > Sources**, **Settings > Playlist** and **Settings > JRiver Playlists** now show a row of tabs: Windows (Main), then one per ticked device.
3. Each device tab starts with **Copy Windows (Main)** ticked, greyed out and following the Windows app. Untick it to change that device's settings. Each page is separate, so a device can have its own Sources while its Playlist still follows Windows (Main).

What a device can have its own copy of:

- **Sources:** which services suggest similar artists, similar tracks and top tracks, how many must agree, and the **AI Moderator** for Similar Artists and Similar Tracks, which checks each playlist for tracks that clash with the seed's mood.
- **Playlist:** for each Play option, track counts, Drift, Non-stop, skipping tracks played recently, and skipping long album closers that hide a bonus track.
- **JRiver Playlists:** how your own playlists play when asked for by voice.
- **Filters:** a device with its own settings can be named under **Applies on** in a filter (Settings > Filters), such as keeping the kitchen to a "Kitchen Favourites" playlist. A device without its own settings gets the Windows (Main) filters.

Keys, search sites, zones and the rest stay shared.

**An example.** Two speakers make it easy to try two sets of settings side by side: the same command in the kitchen and the lounge, one with the AI Moderator and Drift on, one without, and you can hear which works better. Or the kitchen device can simply suit someone else's taste, with the moderator on and anything played in the last day left out, while the lounge Dot stays on Windows (Main).

Untick **Own settings** and the device goes back to Windows (Main). Its own settings are kept, so ticking it again brings them back.

"Shuffle songs by" uses the **Skip tracks played in the last** setting from the device's Artist's Top Tracks, since a shuffle has no group of its own.

## Good to know

- Voice Commands only work while 24bit7 and JRiver are running on the PC. **Settings > Other > Windows** can start 24bit7 with Windows, hidden in the tray.
- Playlists are built one at a time, whether they come from the app or from voice.
- Every playlist a voice command builds appears in the Play tab's log, with the device's name, so you can see what it found and why.
