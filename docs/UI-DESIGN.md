# Addarr interface

Addarr lets users request movies, series and music through Telegram. The web interface is for managing requests, users and connected services.

## Wording

Use short, direct labels and instructions. Describe what a page or action does. Avoid slogans, sales copy, film puns and unnecessary reassurance. Use normal terms such as users, requests and settings. Empty states should name what is missing. Only add helper text when it answers a practical question.

For example: "Set up Addarr", "No requests yet", "Test connection" and "At least 12 characters". Apply the same approach to every translation and Telegram message.

The interface uses charcoal surfaces, coral actions, cinematic artwork, and a consistent line icon family. Movie, series, and music services have separate warm, blue, and olive identities. Actual request and connection states drive the dashboard. No sample movies or invented activity appear in the application.

Account setup introduces the media theme and explains the local setup key. The dashboard provides recent requests and connection status. Service configuration presents one service at a time with connection testing before request defaults; advanced choices stay expandable. Every service form remains available without JavaScript. Mobile navigation retains backup and sign-out, with keyboard focus containment and Escape dismissal. The interface honours reduced motion and keeps assets local.

All interface copy is in the nine-language catalog. Existing form actions, CSRF checks, local authentication, and service draft handling remain in place.

Saved services load quality profiles and root folders from their APIs when the settings page opens. Lidarr also supplies metadata profiles. New connections load these choices through the connection test. An unavailable service leaves saved values in place and does not stop other services from loading. Removed choices stay visible until the administrator replaces them.

Settings includes global automatic approval for new requests from active users. It is off by default. Existing pending requests still need review, and individual user approval settings continue to apply when the global option is off. Request policy can be saved independently of Telegram connection settings.

Radarr, Sonarr, Lidarr and Telegram use bundled upstream logos on their cards and settings. Asset sources are recorded in `addarr/static/logos/SOURCES.md`.

Addarr's mark uses a segmented circular ring and a coral plus sign on a graphite base. Its shape fits alongside the other *arr services, while the plus identifies its request and add function. The header, sidebar and favicon all use `addarr/static/logos/addarr.svg`.

## Artwork

The original backdrop is saved at `addarr/static/cinema.png`. It was created with the built-in image generation tool. The application serves the asset locally, without an external image or font service.

Generation prompt:

> Create a premium cinematic photographic background image for a private movies, television and music app called Addarr. Image only, absolutely no text, no lettering, no logos, no UI, no border. Portrait 1024x1536 composition. A lone tiny silhouetted traveler standing on a dark rocky ridge in lower middle, immense burnt orange eclipsed sun low in the sky behind layers of hazy mountain ranges, rich dark teal shadows, smoky copper light, restrained coral orange highlights, fine analog film grain, anamorphic cinema atmosphere, realistic film still with enormous scale and beautiful light. Top third mostly dark near-black teal sky with fine stars and orange ambient glow, lower quarter deep dark shadow to allow white text overlay. Sophisticated arthouse science fiction film poster photography, tactile analog feeling, atmospheric, elegant, awe-inspiring. Composition keeps the eclipse in center at about 42 percent image height, mountains below, avoid oversaturated fantasy and glossy 3D render.

## Verification

`scripts/browser_smoke.py` exercises actual account setup, all admin pages, all nine locales, mobile layout and navigation, and login/logout against an isolated server. Screenshots are written to the ignored `artifacts/` directory. Backend tests and static checks run separately.
