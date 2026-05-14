from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from config import SLACK_BOT_TOKEN, SLACK_APP_TOKEN
from slack_handlers.onboarding import register_onboarding_handlers


app = App(token=SLACK_BOT_TOKEN)
register_onboarding_handlers(app)


if __name__ == "__main__":
    print("Starting OnboardFlow in Slack Socket Mode...")
    SocketModeHandler(app, SLACK_APP_TOKEN).start()