import csv
import codecs
import re
import json
import logging
import os
import phonenumbers
from openai import OpenAI
from twilio.rest import Client as TwilioClient
from django.contrib.auth import authenticate
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from core.models import Client
from django.contrib.auth import login, logout
from .forms import CSVUploadForm, RegisterForm, EventForm, SettingsForm, OrganisationForm, JoinOrganisationForm
from .models import Client, Event, Message, Organisation
from django.db.models import Sum, Count
from django.utils.dateformat import format
from django.db.models.functions import TruncDate
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.http import StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from phonenumbers import parse, is_valid_number, format_number, PhoneNumberFormat, NumberParseException


logger = logging.getLogger(__name__)

def logout_view(request):
    logout(request)
    print("User logged out successfully.")
    return render(request, 'core/logout.html', {"message": "You are now logged out."})


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        logger.info(f"Login attempt received for username: {username}")

        if not username or not password:
            logger.warning("Login failed: Missing username or password.")
            messages.error(request, "Please provide both username and password.")
            return render(request, 'core/login.html')

        # Authenticate user
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_active:
                login(request, user)
                logger.info(f"User {username} logged in successfully.")
                return redirect('home')  # Ensure this URL is valid
            else:
                logger.warning(f"Login failed: User {username} is inactive.")
                messages.error(request, "Your account is inactive. Please contact support.")
        else:
            logger.warning(f"Login failed: Invalid credentials for username: {username}.")
            messages.error(request, "Invalid username or password.")

    return render(request, 'core/login.html')

def home(request):
    return render(request, 'core/home.html')


def profile(request):
    return render(request, 'core/profile.html')


def analytics(request):
    return render(request, 'core/analytics.html')


@login_required
def client_list(request):
    # Separate personal and organisation clients
    personal_clients = Client.objects.filter(user=request.user)
    organisation_clients = Client.objects.filter(user__organisation=request.user.organisation) if request.user.organisation else []

    if request.method == 'POST':
        if 'delete_personal_selected' in request.POST:
            selected_ids = request.POST.getlist('selected_personal_clients')
            if selected_ids:
                # Delete selected personal clients
                personal_clients.filter(id__in=selected_ids).delete()
                messages.success(request, "Selected personal clients have been deleted.")
            else:
                messages.warning(request, "No clients selected for deletion.")

        elif 'export_to_organisation' in request.POST:
            if not request.user.organisation:
                messages.error(request, "You are not part of an organisation.")
                return redirect('client_list')

            selected_ids = request.POST.getlist('selected_personal_clients')
            if selected_ids:
                # Export personal clients to organisation
                clients_to_export = personal_clients.filter(id__in=selected_ids)
                for client in clients_to_export:
                    # Duplicate the client under the organisation
                    Client.objects.create(
                        user=request.user.organisation.created_by,  # Or another user in the organisation
                        name=client.name,
                        email=client.email,
                        phone=client.phone,
                        total_spent=client.total_spent,
                        last_purchase_date=client.last_purchase_date,
                        unsubscribed=client.unsubscribed,
                    )
                messages.success(request, "Selected clients have been exported to the organisation.")
            else:
                messages.warning(request, "No clients selected for export.")

    return render(request, 'core/client_list.html', {
        'personal_clients': personal_clients,
        'organisation_clients': organisation_clients,
    })

@login_required
def upload_csv(request):
    if request.method == 'POST':
        form = CSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = form.cleaned_data['csv_file']
            try:
                decoded_file = codecs.iterdecode(csv_file, 'utf-8-sig')  # Handle BOM
                csv_reader = csv.reader(decoded_file)
                next(csv_reader)  # Skip header row
                for i, row in enumerate(csv_reader, start=2):
                    try:
                        if len(row) != 5:
                            raise ValueError(f"Row {i} does not have the required number of columns.")

                        name, email, phone, total_spent, last_purchase_date = row

                        if not name or not email or not phone:
                            raise ValueError(f"Row {i}: Name, email, and phone are required.")
                        if total_spent and not total_spent.replace('.', '', 1).isdigit():
                            raise ValueError(f"Row {i}: Total spent must be a valid number.")
                        if last_purchase_date and not re.match(r"\d{4}-\d{2}-\d{2}", last_purchase_date):
                            raise ValueError(f"Row {i}: Last purchase date must be in YYYY-MM-DD format.")

                        Client.objects.create(
                            user=request.user,
                            name=name,
                            email=email,
                            phone=phone,
                            total_spent=float(total_spent),
                            last_purchase_date=last_purchase_date or None
                        )
                    except ValueError as ve:
                        logger.warning(f"Skipping row {i}: {ve}")
                        messages.warning(request, f"Row {i} skipped: {ve}")
                        continue

                messages.success(request, "Clients successfully uploaded from CSV.")
                return redirect('client_list')

            except Exception as e:
                logger.error(f"Unexpected error during CSV processing: {e}")
                messages.error(request, "Failed to upload clients. Please ensure the file format is correct.")
        else:
            messages.error(request, "Invalid form submission. Please try again.")
    else:
        form = CSVUploadForm()
    return render(request, 'core/upload_csv.html', {'form': form})
@login_required
def calendar_view(request):
    global_events = Event.objects.filter(is_global=True)
    user_events = Event.objects.filter(user=request.user)
    events = [
        {
            "id": event.id,
            "title": event.title,
            "start": event.start.isoformat(),
            "end": event.end.isoformat(),
            "description": event.description,
            "is_global": event.is_global,
        }
        for event in list(global_events) + list(user_events)
    ]
    clients = Client.objects.filter(user=request.user)
    form = EventForm(user=request.user)
    return render(request, 'core/calendar.html', {'events': events, 'form': form, 'clients': clients})


@login_required
def add_event(request):
    if request.method == 'POST':
        form = EventForm(request.POST, user=request.user)
        is_global = form.cleaned_data.get('is_global', False)
        if is_global and not request.user.is_superuser:
            raise PermissionDenied("Only superusers can create global events.")
        event_id = request.POST.get('event_id', None)  # Get the event ID if provided

        # Check if updating an existing event
        if event_id:
            try:
                event = Event.objects.get(id=event_id, user=request.user)
            except Event.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Event not found.'}, status=404)
        else:
            event = Event(user=request.user)  # Create a new event if no ID is provided

        if form.is_valid():
            # Update event fields with form data
            event.title = form.cleaned_data['title']
            event.start = form.cleaned_data['start']
            event.end = form.cleaned_data['end']
            event.description = form.cleaned_data['description']

            # Handle "is_global" field based on user's superuser status
            is_global = form.cleaned_data.get('is_global', False)
            if is_global and not request.user.is_superuser:
                return JsonResponse({'success': False, 'message': 'Only superusers can create global events.'},
                                    status=403)

            event.is_global = is_global if request.user.is_superuser else False
            event.user = None if is_global else request.user
            event.save()
            form.save_m2m()  # Save many-to-many relationships for clients

            return JsonResponse({'success': True, 'message': 'Event saved successfully!', 'event_id': event.id})
        else:
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
    return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)

@login_required
def fetch_events(request):
    """
    Fetch global and user-specific events.
    """
    # Fetch global events and user-specific events
    global_events = Event.objects.filter(is_global=True)
    user_events = Event.objects.filter(user=request.user)

    # Combine and prepare events for JSON response
    events = [
        {
            "id": event.id,  # Include the unique event ID
            "title": event.title,
            "start": event.start.isoformat(),
            "end": event.end.isoformat(),
            "allDay": False,  # Ensure this remains false unless needed otherwise
            "description": event.description,
            "is_global": event.is_global,  # Include global status for frontend use
        }
        for event in global_events.union(user_events)  # Avoid duplicates
    ]

    return JsonResponse(events, safe=False)

@login_required
def messages_view(request):
    if request.method == 'POST':
        # Debugging: Print incoming POST data
        print("POST Data received at messages_view:", request.POST)
        print("POST request received at messages_view")  # Debug Point 1

        # Get form values with default or fallback values
        selected_clients = request.POST.getlist('clients[]')
        data_fields = request.POST.getlist('data_fields')

        # Debugging: Check retrieved values
        print("Selected Clients:", selected_clients)
        print("Data Fields:", data_fields)

        # Inspect raw POST data for potential mismatches
        print("Raw POST Keys:", request.POST.keys())
        print("Value of 'clients[]':", request.POST.getlist('clients[]'))
        print("Value of 'clients':", request.POST.getlist('clients'))

        # Error handling: Ensure clients and data fields are selected
        if not selected_clients or not data_fields:
            print("Error Debug: Selected Clients or Data Fields are empty.")
            messages.error(request, "Please select at least one client and one data field.")
            return redirect('messages')  # Redirect back to the form with an error message

        # Debugging: Validate promotional event fields
        promotional_event = request.POST.get('promotional_event') == 'on'
        print("Promotional Event:", promotional_event)
        discount = request.POST.get('discount', '0')  # Default to "0" if missing
        print("Discount:", discount)

        # Other form fields
        tone = request.POST.get('tone', 'Professional, Personal').strip()  # Default tone to "Professional and Personal"
        print("Tone:", tone)
        topic = request.POST.get('topic', 'General')  # Default topic to "General"
        print("Topic:", topic)

        brand_specific = request.POST.get('brand_specific') == 'on'
        print("Brand Specific:", brand_specific)
        brand = request.POST.get('brand', 'N/A')  # Default to "N/A" if missing
        print("Brand:", brand)

        link = request.POST.get('link', '')  # Default to an empty string
        print("Link:", link)
        sign_off_name = request.POST.get('sign_off_name') == 'on'
        print("Include Sign Off Name:", sign_off_name)
        sign_off = request.POST.get('sign_off') or request.user.get_full_name().split(' ')[0]
        print("Sign Off:", sign_off)
        store_name = request.POST.get('store_name', 'Your Store')  # Default to "Your Store"
        print("Store Name:", store_name)

        # Process selected clients
        client_statements = []
        for client_id in selected_clients:
            try:
                # Fetch the client object
                client = Client.objects.get(id=client_id, user=request.user)
                print(f"Processing client: {client.name} (ID: {client.id})")  # Debug Point 3

                # Build the client statement
                statement = {
                    'name': client.name if 'name' in data_fields else '',
                    'phone_number': client.phone if 'phone_number' in data_fields else '',
                    'email': client.email if 'email' in data_fields else '',
                    'last_purchase_date': client.last_purchase_date.strftime('%Y-%m-%d') if 'last_purchase_date' in data_fields else '',
                    'promotional_event': "Yes" if promotional_event else "No",
                    'discount': f"{discount}%" if promotional_event else "N/A",
                    'tone': tone,
                    'topic': topic,
                    'brand_specific': "Yes" if brand_specific else "No",
                    'brand': brand if brand_specific else "N/A",
                    'link': link,
                    'sign_off': sign_off,
                    'store_name': store_name,
                }

                # Append to the client statements list
                client_statements.append(statement)

            except Client.DoesNotExist:
                # Handle case where the client does not exist
                print(f"Client with ID {client_id} does not exist or does not belong to the user.")  # Debug Point 4
                continue

        # Debugging: Print final client statements
        print("Generated Client Statements:", client_statements)  # Debug Point 5

        # Save client statements to session
        request.session['client_statements'] = client_statements
        print("Session data saved successfully for client_statements")  # Debug Point 6

        # Redirect to the message summary page
        print("Redirecting to message_summary with URL name 'message_summary'")  # Debug Point 7
        return redirect('message_summary')

    # Render the form page with available clients
    print("Rendering messages form with available clients")  # Debug Point 8
    clients = Client.objects.filter(user=request.user)
    print(f"Clients available for selection: {[client.id for client in clients]}")  # Debug Point 9
    return render(request, 'core/messages.html', {'clients': clients})
@login_required
def message_summary(request):
    # Retrieve client statements from the session
    client_statements = request.session.get('client_statements', [])
    print("Client statements retrieved for summary:", client_statements)

    # Pass the data to the template for rendering
    return render(request, 'core/message_summary.html', {'client_statements': client_statements})


@login_required
def settings_view(request):
    user = request.user
    if request.method == 'POST':
        form = SettingsForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            if form.cleaned_data.get('password'):
                user.set_password(form.cleaned_data['password'])
            form.save()
            messages.success(request, "Account details updated successfully.")
            return redirect('settings')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = SettingsForm(instance=user)
    return render(request, 'core/settings.html', {'form': form, 'user': user})


def purchase_credit(request):
    return render(request, 'core/purchase_credit.html')


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            print(f"New user created: {user.username}")
            login(request, user)
            print(f"User {user.username} logged in successfully.")
            messages.success(request, "Registration successful. Welcome!")
            return redirect('home')
        else:
            messages.error(request, "Registration failed. Please correct the errors below.")
    else:
        form = RegisterForm()
    return render(request, 'core/register.html', {'form': form})


@login_required
def delete_event(request):
    if request.method == 'POST':
        try:
            # Parse request data
            data = json.loads(request.body)
            event_id = data.get('id')

            print("Received Event ID for deletion:", event_id)  # Debug log

            # Validate event ID
            if not event_id or not event_id.isdigit():
                return JsonResponse({'success': False, 'message': 'Invalid or missing Event ID.'}, status=400)

            # Attempt to retrieve the event
            event = Event.objects.get(id=int(event_id))

            # Check permissions
            if event.is_global and not request.user.is_superuser:
                return JsonResponse(
                    {'success': False, 'message': 'You do not have permission to delete global events.'}, status=403)
            if event.user != request.user and not request.user.is_superuser:
                return JsonResponse({'success': False, 'message': 'You can only delete your own events.'}, status=403)

            # Delete the event
            event.delete()
            return JsonResponse({'success': True, 'message': 'Event deleted successfully!'})

        except Event.DoesNotExist:
            # Handle case where event does not exist
            return JsonResponse({'success': False, 'message': 'Event not found.'}, status=404)

        except Exception as e:
            # Log unexpected errors
            logger.error(f"Unexpected error in delete_event: {e}")
            return JsonResponse({'success': False, 'message': 'An error occurred while deleting the event.'}, status=500)

    return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)

@login_required
def analytics_data(request):
    user = request.user

    # Clients and Spend
    clients = Client.objects.filter(user=user)
    total_clients = clients.count()
    client_names = list(clients.values_list('name', flat=True))
    client_spends = list(clients.values_list('total_spent', flat=True))
    total_spend = clients.aggregate(total=Sum('total_spent'))['total'] or 0.0

    # Messages Sent vs Spend
    messages_vs_spend = clients.annotate(
        message_count=Count('message')
    ).values('name', 'total_spent', 'message_count')

    spend_vs_message_names = [item['name'] for item in messages_vs_spend]
    spend_vs_message_spends = [item['total_spent'] for item in messages_vs_spend]
    spend_vs_message_counts = [item['message_count'] for item in messages_vs_spend]

    # Events and Participation
    events = Event.objects.filter(user=user).annotate(client_count=Count('clients'))
    total_events = events.count()
    event_names = [event.title for event in events]
    event_counts = [event.client_count for event in events]

    # Messages
    messages = Message.objects.filter(client__user=user)
    total_messages = messages.count()
    message_stats = (
        messages.annotate(date=TruncDate('sent_date'))
        .values('date')
        .annotate(count=Count('id'))
        .order_by('date')
    )
    message_dates = [format(stat['date'], 'Y-m-d') for stat in message_stats]
    messages_per_day = [stat['count'] for stat in message_stats]

    return JsonResponse({
        'total_clients': total_clients,
        'total_spend': total_spend,
        'client_names': client_names,
        'client_spends': client_spends,
        'spend_vs_message_names': spend_vs_message_names,
        'spend_vs_message_spends': spend_vs_message_spends,
        'spend_vs_message_counts': spend_vs_message_counts,
        'total_events': total_events,
        'event_names': event_names,
        'event_counts': event_counts,
        'total_messages': total_messages,
        'message_dates': message_dates,
        'messages_per_day': messages_per_day,
    })

# Instantiate OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@csrf_exempt
@login_required
def generate_ai_messages_stream(request):
    """
    View to generate AI messages for client data and return them as a streamed response.
    Deduct 1 credit per message generated.
    """
    print("Stream endpoint hit.")
    print(f"Request headers: {request.headers}")
    print(f"Request method: {request.method}")

    # Retrieve the current user
    user = request.user
    print(f"Generating messages for user: {user.username}")

    # Retrieve client statements from the session
    client_statements = request.session.get('client_statements', [])
    if not client_statements or not isinstance(client_statements, list):
        print("No client statements available or invalid data format.")
        messages.error(request, "No client statements available. Please create some.")
        return redirect('messages')  # Redirect to the messages form page

    # Ensure the user has sufficient credits
    required_credits = len(client_statements)
    if user.credits < required_credits:
        print(f"Insufficient credits for user {user.username}. Required: {required_credits}, Available: {user.credits}")
        messages.error(request, "Insufficient credits to generate messages.")
        return redirect('message_summary')  # Redirect back to the message summary page

    # Deduct credits in a transaction-safe manner
    try:
        with transaction.atomic():
            user.credits -= required_credits
            user.save()
            print(f"Deducted {required_credits} credits from user {user.username}. Remaining credits: {user.credits}")
    except Exception as e:
        print("Error deducting credits:", str(e))
        messages.error(request, "Failed to deduct credits. Please try again later.")
        return redirect('message_summary')

    def stream_responses():
        """
        Generator function to stream responses to the frontend as JSON objects.
        """
        try:
            # Build a detailed prompt
            prompt = f"""
            Generate personalized marketing text messages for the following customer data. Each message should:
            - Start with a greeting using the customer's first name.
            - Include the promotional event and discount if specified.
            - Reference the topic and related brand if specified.
            - Do not use emojis, the text should appear as if it's from a person, avoid using "we," instead use "I."
            - Close with an appropriate sign-off and the store name if specified.
            - Include the provided link at the end if provided.
            Output each message in the following JSON format:
            {{
                "name": "<Customer Name>",
                "phone_number": "<Phone Number>",
                "message": "<Generated Message>"
            }}

            Data: {client_statements}
            """
            print("Generated prompt for streaming:", repr(prompt))

            # Use the streaming API to get responses
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                stream=True,
            )
            print("Streaming API request initiated.")

            buffer = ""  # Initialize a buffer to collect content

            # Process streaming responses
            for chunk in response:
                # Safely access chunk content
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    content = delta.content
                    print("Chunk content received:", repr(content))
                    buffer += content

                    # Try to parse complete JSON objects in the buffer
                    while True:
                        message_start = buffer.find('{')
                        message_end = buffer.find('}', message_start) + 1
                        if message_start == -1 or message_end == 0:
                            break  # No complete JSON object found in the buffer

                        # Extract the complete JSON object
                        json_message = buffer[message_start:message_end]
                        buffer = buffer[message_end:]  # Remove the processed part from the buffer

                        try:
                            # Parse the JSON object
                            parsed_message = json.loads(json_message)
                            print("Parsed JSON message:", parsed_message)
                            yield f"data: {json.dumps(parsed_message)}\n\n"
                        except json.JSONDecodeError as e:
                            print("JSON parsing error, waiting for more chunks:", str(e))

            # End the stream
            print("All chunks processed. Ending stream.")
            yield "event: end\ndata: Streaming completed\n\n"

        except Exception as e:
            print("Error while processing streaming response:", str(e))
            yield f"event: error\ndata: {str(e)}\n\n"

    try:
        # Return a streaming response
        print("Returning StreamingHttpResponse.")
        return StreamingHttpResponse(
            stream_responses(),
            content_type="text/event-stream",
        )

    except Exception as e:
        print("Error while returning StreamingHttpResponse:", str(e))
        messages.error(request, "Failed to generate AI messages. Please try again later.")
        return redirect('message_summary')



@login_required
def generate_ai_messages_page(request):
    """
    Render the HTML template with placeholders for streaming messages.
    """
    return render(request, 'core/generated_ai_messages.html')


@login_required
def add_credits(request):
    if request.method == "POST":
        try:
            amount = int(request.POST.get("amount", 0))
            if amount > 0:
                request.user.credits += amount
                request.user.save()
                messages.success(request, f"{amount} credits added successfully!")
            else:
                messages.error(request, "Invalid amount.")
        except ValueError:
            messages.error(request, "Enter a valid amount.")
    return redirect("profile")

@login_required
def deduct_credits(request):
    if request.method == "POST":
        try:
            amount = int(request.POST.get("amount", 0))
            if 0 < amount <= request.user.credits:
                request.user.credits -= amount
                request.user.save()
                messages.success(request, f"{amount} credits deducted successfully!")
            else:
                messages.error(request, "Invalid amount or insufficient credits.")
        except ValueError:
            messages.error(request, "Enter a valid amount.")
    return redirect("profile")

@login_required  # Optional: Require user login to view the page
def policy_agreement(request):
    return render(request, 'core/policy_agreement.html')

@login_required
def accept_policies(request):
    """
    View to handle policy acceptance.
    """
    # Mark policies as accepted for the user (modify as per your model structure)
    user = request.user
    user.has_accepted_policies = True
    user.save()

    messages.success(request, "You have successfully accepted the policies.")
    return redirect('home')  # Redirect to the homepage or another page


@csrf_exempt
def send_message_view(request):
    if request.method == "POST":
        try:
            # Parse JSON data from request body
            data = json.loads(request.body)
            phone_number = data.get("phone_number")
            message_body = data.get("message")

            # Validation: Check for missing fields
            if not phone_number or not message_body:
                logger.error("Missing phone number or message body.")
                return JsonResponse({"success": False, "error": "Missing phone number or message body."})

                # Validate phone number using phonenumbers library
            try:
                country_code = getattr(settings, "DEFAULT_COUNTRY_CODE", "AU")
                parsed_number = phonenumbers.parse(phone_number, country_code)
                if not phonenumbers.is_valid_number(parsed_number):
                    logger.error(f"Invalid phone number format: {phone_number}")
                    return JsonResponse({"success": False, "error": "Invalid phone number format."})

                # Ensure phone number includes the '+' symbol
                phone_number = f"+{parsed_number.country_code}{parsed_number.national_number}"
                logger.info(f"Validated and formatted phone number: {phone_number}")
            except NumberParseException as e:
                logger.error(f"Phone number validation failed: {str(e)}")
                return JsonResponse({"success": False, "error": "Invalid phone number format."})

            # Twilio setup
            twilio_client = TwilioClient(
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN
            )
            twilio_from_number = settings.TWILIO_PHONE_NUMBER

            # Send the message using Twilio
            try:
                twilio_response = twilio_client.messages.create(
                    body=message_body,
                    from_=twilio_from_number,
                    to=phone_number,
                )
                logger.info(f"Message sent successfully to {phone_number}. SID: {twilio_response.sid}")
                return JsonResponse({"success": True, "sid": twilio_response.sid})
            except Exception as e:
                logger.error(f"Failed to send message to {phone_number}: {str(e)}")
                return JsonResponse({"success": False, "error": f"Failed to send message: {str(e)}"})

        except json.JSONDecodeError as e:
            logger.error(f"JSON decoding error: {str(e)}")
            return JsonResponse({"success": False, "error": "Invalid JSON payload."})
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return JsonResponse({"success": False, "error": "An unexpected error occurred."})

    return JsonResponse({"success": False, "error": "Invalid request method."})


@login_required
def add_organisation(request):
    if request.method == "POST":
        form = OrganisationForm(request.POST)
        if form.is_valid():
            organisation = form.save(commit=False)
            organisation.created_by = request.user
            organisation.save()

            # Assign the user who created the organisation to it
            request.user.organisation = organisation
            request.user.save()

            messages.success(request, f"Organisation '{organisation.name}' created successfully! You are now a member.")
            return redirect("profile")  # Redirect to user's profile or another relevant page
    else:
        form = OrganisationForm()

    return render(request, "core/add_organisation.html", {"form": form})

@login_required
def join_organisation(request):
    if request.method == "POST":
        form = JoinOrganisationForm(request.POST)
        if form.is_valid():
            organisation_id = form.cleaned_data["organisation_id"]
            organisation = Organisation.objects.filter(organisation_id=organisation_id).first()

            if organisation:
                if request.user.organisation == organisation:
                    messages.warning(request, f"You are already a member of '{organisation.name}'.")
                else:
                    # Assign the user to the organisation
                    request.user.organisation = organisation
                    request.user.save()
                    messages.success(request, f"You have successfully joined the organisation '{organisation.name}'.")
                return redirect("profile")
            else:
                messages.error(request, "Invalid Organisation ID. Please check and try again.")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = JoinOrganisationForm()

    return render(request, "core/join_organisation.html", {"form": form})