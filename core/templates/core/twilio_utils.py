from twilio.rest import Client
from django.conf import settings

def send_message(to, body):
    """
    Sends a message using the Twilio API.
    """
    try:
        # Initialize Twilio client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        # Send the message
        message = client.messages.create(
            to=to,
            from_=settings.TWILIO_PHONE_NUMBER,
            body=body
        )
        return {"success": True, "sid": message.sid}
    except Exception as e:
        return {"success": False, "error": str(e)}