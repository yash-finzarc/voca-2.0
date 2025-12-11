import os
import logging
from src.voca.gui.app import VocaApp


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("aiortc").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    # Disable Twilio HTTP client logging (too verbose)
    logging.getLogger("twilio.http_client").setLevel(logging.CRITICAL)
    logging.getLogger("twilio.http_client").disabled = True
    app = VocaApp()
    app.run()


if __name__ == "__main__":
    main()


