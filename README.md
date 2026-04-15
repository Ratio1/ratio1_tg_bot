# Ratio1 Telegram Bot

A Telegram bot for the Ratio1 community.

The bot deploys a Ratio1 `create_telegram_simple_bot` pipeline that:

- posts an epoch summary to the configured Telegram chat when a new Ratio1 epoch is available;
- lets users watch Ethereum wallets that own Ratio1 nodes;
- sends Telegram alerts when watched nodes go offline, reminders while they stay offline, and recovery messages when they come back online.

## Repository Layout

- `ratio1_tg_bot.py` - bot entry point, Telegram command handlers, periodic processing, and pipeline deployment.
- `ver.py` - bot version used by the deployed pipeline.
- `.github/workflows/cd-update-bot.yml` - redeploys the bot on `main` when `ver.py` changes.

## Requirements

- Python 3.
- The Ratio1 Python SDK.
- Ratio1 SDK credentials configured for the environment where the bot runs.
- A Telegram bot token from BotFather.
- A Telegram chat ID where epoch summaries should be posted.
- A target Ratio1 node address.

Install the SDK if it is not already available:

```bash
python3 -m pip install ratio1
```

## Configuration

The bot reads these environment variables:

| Variable | Required | Description |
| --- | --- | --- |
| `RATIO1_NODE` | Yes | Target Ratio1 node where the Telegram bot pipeline is deployed. |
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token. |
| `TELEGRAM_CHAT_ID` | Yes | Telegram chat ID used for epoch summary messages. |

Example local environment:

```bash
export RATIO1_NODE="<ratio1-node-address>"
export TELEGRAM_BOT_TOKEN="<telegram-bot-token>"
export TELEGRAM_CHAT_ID="<telegram-chat-id>"
```

## Running Locally

Start the bot deployment:

```bash
python3 ratio1_tg_bot.py
```

The script waits for `RATIO1_NODE`, deploys the `ratio1_telegram_bot` pipeline, and keeps the Ratio1 session alive long enough for deployment and message processing setup.

To stop the deployed pipeline, change the `COMMAND` value in `ratio1_tg_bot.py` from `START` to `STOP` and run the script again.

## Telegram Commands

The bot ignores commands sent in the configured community chat and responds to direct/private chats.

| Command | Description |
| --- | --- |
| `/start` | Shows the initial usage message. |
| `/watch <wallet_address>` | Watches an Ethereum wallet and alerts when its Ratio1 nodes are offline. |
| `/unwatch <wallet_address>` | Stops watching one wallet. |
| `/unwatchall` | Stops watching all wallets for the current chat. |
| `/watchlist` | Lists watched wallets for the current chat. |
| `/nodes` | Lists watched wallets and their nodes, including online/offline status. |
| `/network_status` | Reports how many Ratio1 nodes are currently online. |
| `/ver` | Shows the deployed bot version. |
| `/last_epoch_info` | Admin-only command that forces the next loop to send the last epoch summary. |

## Runtime Behavior

During periodic processing, the bot:

1. loads cached epoch review, watched wallet, and offline alert data from Ratio1 disk storage;
2. checks watched wallet nodes every configured loop interval;
3. sends offline alerts after a node has been seen offline at least `offline_node_min_seens` times;
4. sends reminders after 1, 6, 12, 24, and then recurring 24-hour intervals;
5. sends recovery messages when previously offline nodes come back online;
6. sends one epoch summary per epoch to `TELEGRAM_CHAT_ID`.

Epoch summary data comes from:

- Ratio1 network monitoring data through the SDK;
- Ratio1 blockchain/license helpers through the SDK;
- `https://dapp-api.ratio1.ai/token/bot-stats`;
- ERC-721 `totalSupply()` calls on Base through `https://base.drpc.org`.

## Persisted Data

The bot persists state through the Ratio1 plugin disk API:

- `ratio1_epoch_review_data.pkl` - epochs already summarized.
- `ratio1_watched_wallets_data.pkl` - watched wallets by Telegram chat/user ID.
- `ratio1_offline_node_alerts_data.pkl` - offline alert and reminder state.

These files are managed by the deployed plugin runtime and are not committed to this repository.

## Deployment

The repository includes a GitHub Actions workflow:

```text
.github/workflows/cd-update-bot.yml
```

It runs when `ver.py` changes on `main`. The workflow uses `Ratio1/ratio1-setup-action@v1`, configures the Ratio1 environment, and runs:

```bash
python3 ratio1_tg_bot.py
```

Required GitHub secrets:

- `RATIO1_PRIVATE_KEY_PEM`
- `RATIO1_NODE`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Version Updates

Update `VERSION` in `ver.py` when publishing a new bot version. Pushing that change to `main` triggers the CD workflow.
