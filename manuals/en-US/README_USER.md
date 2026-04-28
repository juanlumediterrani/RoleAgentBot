# RoleAgentBot — User Guide

RoleAgentBot is a personality-driven Discord companion. It is not just a command bot — it has a character, a voice, memory of past interactions, and a set of specialized capabilities it carries across your server. You can talk to it, rely on it for automated alerts, play with it, and configure it to fit your community.

---

## Personalities

The bot embodies one personality at a time per server. Each personality has a unique name, avatar, speech style, and tone that shapes every single response — conversations, notifications, reactions, everything.

Available personalities:

- **Rab** — futuristic android that can change his personality
- **Putre** — aggressive orc, blunt and direct
- **Yuki** — distinct style and voice
- **Hans** — distinct style and voice
- **Panigorr** — distinct style and voice

Each server can have a different active personality. Language is also configurable per server (English, Spanish, Chinese). Use `!canvas` to change personality and language for your server.

The bot also **evolves**. Every week it quietly analyzes the last seven days of server activity and subtly adjusts its character — not enough to feel like a different bot, but enough to feel like it grows over time.

---

## How to Talk to the Bot

Mention the bot or send it a direct message.

- In a **server channel**, mention it: `@BotName your message here`
- In **DMs**, just write directly — the experience is more personal and focused

The bot remembers recent exchanges and builds a picture of each user over time. It is not stateless — repeated interactions feel more continuous and familiar.

When the bot greets you privately (presence greeting, welcome message), you will see a **Reply** button. Pressing it pins that DM session to the server, so your private reply is handled in the right context.

---

## What the Bot Does on Its Own

RoleAgentBot is not only reactive. It acts without being explicitly invoked:

- **Presence greeting** — sends you a DM when you come online (if enabled)
- **Welcome message** — greets new members when they join the server (if enabled)
- **Taboo reactions** — reacts to configured words in watched channels
- **Scheduled role alerts** — sends curated notifications based on roles you have configured (news, price tracking, banker bonus, etc.)
- **Commentary** — makes short character-driven comments about active role activity

All of these behaviors can be enabled, disabled, or tuned by admins.

---

## Roles

Roles are feature packs that extend what the bot can do. Each role runs independently, but all of them share the same personality layer — the output always feels like the same bot.

Roles can be managed through the Canvas UI (`!canvas`) or via commands.

---

### News Watcher

A personalized news scout. You subscribe to topics and set premises; the bot filters incoming articles and delivers only what is relevant to you — no raw feed dumps.

You can browse available feeds and categories, subscribe to what interests you, and define keywords or premises that guide the bot's filtering. Articles are analyzed with AI and only those matching your preferences reach you. Users manage their own subscriptions, while admins can configure channel-level delivery.

---

### Scholar

An erudite archivist who draws from the bot's pre-trained knowledge and Wikipedia to answer your questions. Ask anything — the Scholar will respond with wisdom drawn from its vast library, using the bot's personality and memory of your relationship to make the answer feel personal. When the Scholar detects a topic that benefits from external reference, it can fetch Wikipedia extracts to provide richer context. The experience is like consulting a knowledgeable companion who remembers your past interactions and adapts its responses to your server's language.

---

### Treasure Hunter

A market lookout for **Path of Exile 2**. You track items; the bot monitors prices in the background and notifies you when conditions match your goal.

You tell the bot which items you care about, set the active league, and configure how often it checks. When prices move in a way that matches your criteria, you receive a notification. It is designed for players who want to stay aware of opportunities without manually watching the market.

---

### Trickster

Playful and game-oriented. The Trickster role is built for fun and surprise, and it connects to the virtual economy through the Banker role.

#### Dice Game Subrole

A simple dice game where you roll three dice against a fixed bet. The game has clear payout rules: `1-1-1` wins the entire pot, while other combinations like triples, straights, and pairs pay out according to the built-in system. The pot is shared across players, so wins feel more significant. You can check your personal stats, view the history of recent rolls, and see the server ranking. Admins can adjust the default bet and toggle whether results are announced publicly.

---

### Shaman

Interpretive and mystical. The Shaman role brings a different kind of interaction — symbolic, reflective, and personal.

#### Nordic Runes Subrole

Ask a question. The bot casts runes and provides a personalized AI-generated reading. You can choose from several spreads: `single` for a quick answer, `three` for past-present-future context, `cross` for a balanced perspective, or `runic_cross` for a deeper interpretation. Each reading is stored in your personal history, so you can revisit past sessions and see how the runes have guided you over time. The experience feels like a private ritual — the bot uses its personality and your relationship memory to make the reading feel tailored to you.

---

### Banker

The virtual economy layer of the bot. It tracks gold balances, processes transactions, and distributes daily bonuses. Other roles connect to it — the Trickster dice game uses a shared pot managed by the Banker.

#### Beggar Subrole

The bot periodically approaches a user on its own and asks for a donation — entirely in character. It uses its memory of recent interactions and its relationship with the target to personalize the request. The tone can range from playful to dramatic depending on the personality. Admins control how often this happens and where the requests are posted (DM or a specific channel). The funds collected feed into the virtual economy, supporting other activities like the dice game.

---

### Juggler

A playful role driven by a mystery mechanic. The bot is hunting for something (the "One Ring") and may question or accuse users over time.

#### Ring Subrole

The bot periodically engages with the server, building suspicion and eventually accusing a user. It does this through AI-generated dialogue — the bot can emit an accusation mid-conversation, and if the target does not match a real member, it reacts with a follow-up that keeps the narrative going. The experience unfolds like a slow-burn story: the bot asks questions, drops hints, and narrows down the list of suspects. Admins can control the frequency of these events and manually set a target if they want to steer the story in a particular direction.

---

### Music Controller (MC)

Practical music playback in Discord voice channels. Fully integrated — no configuration required to start using it.

You can ask the bot to play songs or URLs, add tracks to a queue, and view what is coming next. It handles YouTube playback, including retry logic for when access is restricted. When the voice channel is empty for a configured time, the bot disconnects automatically to keep things clean. The experience is straightforward: you request, the bot plays.

---

## Canvas — Interactive Configuration

Canvas is a guided interface with buttons, dropdowns, and structured views. It provides a more navigable way to interact with the bot compared to raw commands.

Open Canvas with `!canvas`. If your server has multiple bots, you can target a specific one: `!canvas <bot_name>`.

Through Canvas you can:

- Browse and configure roles
- Manage personal settings (subscriptions, preferences)
- Administer server-level behavior (admin only)
- Change the active personality and language for your server

---

## General Commands

You can access a help menu that shows all available options, check that the bot is responding, and receive this guide directly via DM for future reference. There is also a command to see the current bot identity — which personality and language are active on the server. For a playful character interaction, you can ask the bot for an insult delivered in its style.

---

## Admin Controls

Administrators have additional control over the bot's behavior:

- **Personality and language** — change which character the bot embodies and which language it uses on the server
- **Nickname** — set a custom display name for the bot
- **Greetings** — enable or disable automatic DMs when users come online
- **Welcome messages** — enable or disable greetings for new server members
- **Role activation** — enable or disable specific roles (News Watcher, Treasure Hunter, etc.)
- **Commentary** — control whether the bot makes character-driven comments about its activities

These controls are available both through commands and through the Canvas interface.

---

## Fatigue and Rate Limits

The bot has a built-in protection system to prevent overuse. If you reach the limit for your session (burst, hourly, or daily), the bot will let you know with a friendly message instead of calling the AI. The first few requests of the day are always allowed as a grace period.

---

## Public vs. Private

**In server channels**, the bot behaves like a visible community actor. It is aware that it is in a shared space, responds to mentions, and reacts to server events.

**In DMs**, the experience is more direct. Alerts, balance checks, subscription management, and personal configuration flows all work best in private messages.

A simple rule: the server is social, DMs are personal.

---

## Memory and Continuity

The bot maintains several layers of context per server:

- **Recent dialogue** — the current conversation window
- **Recent memory** — a rolling summary of recent activity, refreshed every few hours
- **Daily memory** — a short synthesis of the server's day, updated every 24 hours
- **Relationship memory** — a per-user summary refreshed hourly, capturing how the bot perceives each person over time

This is why the bot can feel like it remembers things. It does not retrieve full logs — it carries a synthesized picture that evolves continuously.

---

## Terms and License

Before using RoleAgentBot, review the [LICENSE](../../LICENSE) and [TERMS_OF_SERVICE.md](../../TERMS_OF_SERVICE.md) files.

Key points:

- Free for non-commercial use
- Commercial use requires prior written consent
- Software is in active development — use at your own risk
- Intended for adult users (18+)
- Not recommended for individuals with mental health conditions
- Privacy considerations apply to all LLM-processed conversations
