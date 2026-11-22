# Telegram requests

| Command | Action |
| --- | --- |
| `/start` | Open the main menu, including artist and album requests |
| `/movie` | Search for a movie |
| `/series` | Search for a series |
| `/music` | Search for an artist |
| `/requests` | View requests. Admins can also approve or reject them. |
| `/status` | Check the connected services |
| `/help` | Show instructions |
| `/cancel` | Cancel the current search or selection |
| `/chatid` | Show the current group's ID |

Choose a result, check the details and confirm. Requests use the admin's defaults unless you select other permitted profiles, folders or monitoring options.

Addarr marks items already in the library and checks again when you submit a request. It rejects duplicate movie and whole-series requests, even while the media is still downloading. Use **Options** to request missing, unmonitored seasons. Album requests monitor only the selected album. New requests for missing seasons or albums keep the existing library settings.

The bot and web interface each have a language selector. Both support English, German, Spanish, French, Italian, Dutch, Polish, Portuguese and Russian.

## Approve or cancel requests

Requests need approval by default. Admins can approve or reject them in **Requests** or with `/requests`. To skip manual approval for new requests from approved users and allowed groups, turn on **Automatically approve all requests** in **Settings**, under **Requests**. Pending requests still need review. If the global setting is off, per-user approval settings still apply.

Admins can cancel or delete requests in the web interface. Cancelling stops Addarr from submitting or tracking the request. Deleting removes it from the lists and keeps the audit history. Both leave media and downloads that are already in Radarr, Sonarr or Lidarr alone.

## Group chats

1. Add the bot to your group and send `/chatid@YourBot` with your bot's username. It replies even if the group is not on the allowlist.
2. In **Settings**, open **Group chats**, add the group ID and save. Enter IDs on separate lines or separate them with commas. Clear the list to disable group access.
3. Send `/movie@YourBot` or `/series@YourBot` and reply to the search prompt. You can also include the title in the command, as in `/movie@YourBot Alien`.

Members of allowed groups can request without individual access approval. Blocked users remain blocked. Request approval follows the same settings as private chats. Group access gives members no private-chat access or admin rights. Only the person who starts a search can use its result buttons.

Addarr keeps searches separate by person, group and forum topic. In a group, `/requests` shows your requests from that group and topic. Updates go back to the same place. Addarr never posts private requests in a group. Removing a group ID stops pending submissions and notifications for that group. If Telegram converts the group to a supergroup, replace the old ID.

You can leave [Telegram privacy mode](https://core.telegram.org/bots/faq#what-messages-will-my-bot-get) on. Telegram passes commands addressed to the bot and replies to the bot's messages. Addarr does not support broadcast channels or anonymous group senders.

## Download progress

An added request has reached Radarr, Sonarr or Lidarr. Addarr marks it available after that service imports the files. Change Telegram notifications in **Settings**.

For more detail, open **Downloads** and enter the SABnzbd URL and API key. Test the connection and enable it. If an Arr service has several download clients, select the one that points to this SABnzbd instance.

The web request list and `/requests` show progress, pauses, post-processing and failures. Telegram sends a message when the phase changes. Addarr matches downloads by ID and only reads SABnzbd status. Cancelling in Addarr stops tracking and leaves the download running.
