from . import base, server_info, local_voice, twilio, twilio_webhooks, logs, system_prompt, organizations

routers = [
    base.router,
    server_info.router,
    local_voice.router,
    twilio.router,
    twilio_webhooks.router,
    logs.router,
    system_prompt.router,
    organizations.router,
]

__all__ = ["routers"]

