"""
registry.py - OneAtlas AppSpec Engine Integration Registry
Single source of truth for all supported integrations.

Usage:
    from compiler.integrations.registry import REGISTRY, get_integration, list_integration_ids

REGISTRY is a dict[str, Integration] keyed by integration id.
All validation of integration references resolves against this dict at runtime.

Implemented (6): slack, gmail, stripe, whatsapp, webhook, google_sheets
Stubbed (4):     jira, hubspot, notion, twilio_sms

is_stub=True means the interface is correct and validated, but the actual
HTTP call is not implemented. A developer can implement the call from the metadata alone.
"""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


# -- Schema types --------------------------------------------------------------

class ActionInputField(BaseModel):
    name: str
    type: str       # "string" | "number" | "boolean" | "object" | "array"
    required: bool
    description: str


class ActionDescriptor(BaseModel):
    id: str
    display_name: str
    description: str
    input_schema: list[ActionInputField]
    output_schema: dict[str, str]
    is_stub: bool = False


class TriggerDescriptor(BaseModel):
    id: str
    display_name: str
    entity_events: list[str]
    description: str


class Integration(BaseModel):
    id: str
    display_name: str
    auth_type: Literal["oauth2", "api_key", "webhook_secret", "none"]
    description: str
    triggers: list[TriggerDescriptor]
    actions: list[ActionDescriptor]
    is_stub: bool = False


# -- Registry ------------------------------------------------------------------

REGISTRY: dict[str, Integration] = {

    "slack": Integration(
        id="slack",
        display_name="Slack",
        auth_type="api_key",
        description="Send messages, DMs, and formatted blocks to Slack channels.",
        triggers=[
            TriggerDescriptor(
                id="record_event",
                display_name="Record Event",
                entity_events=["created", "updated", "deleted", "status_changed"],
                description="Fires when a record in the app changes state.",
            ),
        ],
        actions=[
            ActionDescriptor(
                id="send_message",
                display_name="Send Channel Message",
                description="Post a plain-text or formatted message to a Slack channel.",
                input_schema=[
                    ActionInputField(name="channel", type="string", required=True,
                                     description="Slack channel ID or name, e.g. #general"),
                    ActionInputField(name="text", type="string", required=True,
                                     description="Message body. Supports Slack mrkdwn."),
                    ActionInputField(name="username", type="string", required=False,
                                     description="Display name override for the bot."),
                ],
                output_schema={"ts": "string - Slack message timestamp", "channel": "string"},
            ),
            ActionDescriptor(
                id="send_dm",
                display_name="Send Direct Message",
                description="Send a DM to a specific Slack user.",
                input_schema=[
                    ActionInputField(name="user_id", type="string", required=True,
                                     description="Slack user ID, e.g. U012AB3CD"),
                    ActionInputField(name="text", type="string", required=True,
                                     description="Message body."),
                ],
                output_schema={"ts": "string", "channel": "string"},
            ),
            ActionDescriptor(
                id="post_block",
                display_name="Post Block Kit Message",
                description="Post a structured Block Kit message to a channel.",
                input_schema=[
                    ActionInputField(name="channel", type="string", required=True,
                                     description="Slack channel ID or name."),
                    ActionInputField(name="blocks", type="array", required=True,
                                     description="Array of Slack Block Kit block objects."),
                    ActionInputField(name="text", type="string", required=False,
                                     description="Fallback plain-text for notifications."),
                ],
                output_schema={"ts": "string", "channel": "string"},
            ),
        ],
    ),

    "gmail": Integration(
        id="gmail",
        display_name="Gmail / Google Workspace",
        auth_type="oauth2",
        description="Send emails and create calendar events via Google Workspace.",
        triggers=[
            TriggerDescriptor(
                id="record_event",
                display_name="Record Event",
                entity_events=["created", "updated", "status_changed"],
                description="Fires when a record changes state, triggering an email action.",
            ),
        ],
        actions=[
            ActionDescriptor(
                id="send_email",
                display_name="Send Email",
                description="Send an email from the authenticated Google account.",
                input_schema=[
                    ActionInputField(name="to", type="string", required=True,
                                     description="Recipient email address."),
                    ActionInputField(name="subject", type="string", required=True,
                                     description="Email subject line."),
                    ActionInputField(name="body", type="string", required=True,
                                     description="Email body - plain text or HTML."),
                    ActionInputField(name="cc", type="string", required=False,
                                     description="CC recipients, comma-separated."),
                ],
                output_schema={"message_id": "string", "thread_id": "string"},
            ),
            ActionDescriptor(
                id="create_calendar_event",
                display_name="Create Calendar Event",
                description="Create a Google Calendar event.",
                input_schema=[
                    ActionInputField(name="title", type="string", required=True,
                                     description="Event title."),
                    ActionInputField(name="start_time", type="string", required=True,
                                     description="ISO 8601 start datetime."),
                    ActionInputField(name="end_time", type="string", required=True,
                                     description="ISO 8601 end datetime."),
                    ActionInputField(name="attendees", type="array", required=False,
                                     description="List of attendee email addresses."),
                    ActionInputField(name="description", type="string", required=False,
                                     description="Event description."),
                ],
                output_schema={"event_id": "string", "html_link": "string"},
            ),
        ],
    ),

    "stripe": Integration(
        id="stripe",
        display_name="Stripe",
        auth_type="api_key",
        description="Create customers, charge cards, manage subscriptions, and issue refunds.",
        triggers=[
            TriggerDescriptor(
                id="payment_event",
                display_name="Payment Event",
                entity_events=["created", "status_changed"],
                description="Fires when a payment or subscription entity changes.",
            ),
        ],
        actions=[
            ActionDescriptor(
                id="create_customer",
                display_name="Create Customer",
                description="Create a new Stripe customer record.",
                input_schema=[
                    ActionInputField(name="email", type="string", required=True,
                                     description="Customer email address."),
                    ActionInputField(name="name", type="string", required=False,
                                     description="Customer full name."),
                    ActionInputField(name="metadata", type="object", required=False,
                                     description="Key-value metadata to attach to the customer."),
                ],
                output_schema={"customer_id": "string - Stripe cus_ id",
                               "created": "number - unix timestamp"},
            ),
            ActionDescriptor(
                id="create_charge",
                display_name="Create Charge",
                description="Charge a payment method for a specific amount.",
                input_schema=[
                    ActionInputField(name="amount", type="number", required=True,
                                     description="Amount in smallest currency unit (e.g. cents)."),
                    ActionInputField(name="currency", type="string", required=True,
                                     description="ISO 4217 currency code, e.g. usd."),
                    ActionInputField(name="customer_id", type="string", required=True,
                                     description="Stripe customer ID."),
                    ActionInputField(name="description", type="string", required=False,
                                     description="Human-readable charge description."),
                ],
                output_schema={"charge_id": "string", "status": "string"},
            ),
            ActionDescriptor(
                id="manage_subscription",
                display_name="Manage Subscription",
                description="Create, update, or cancel a Stripe subscription.",
                input_schema=[
                    ActionInputField(name="customer_id", type="string", required=True,
                                     description="Stripe customer ID."),
                    ActionInputField(name="price_id", type="string", required=True,
                                     description="Stripe Price ID for the plan."),
                    ActionInputField(name="action", type="string", required=True,
                                     description="One of: create | update | cancel"),
                ],
                output_schema={"subscription_id": "string", "status": "string"},
            ),
            ActionDescriptor(
                id="issue_refund",
                display_name="Issue Refund",
                description="Issue a full or partial refund for a charge.",
                input_schema=[
                    ActionInputField(name="charge_id", type="string", required=True,
                                     description="Stripe charge ID to refund."),
                    ActionInputField(name="amount", type="number", required=False,
                                     description="Partial refund amount in smallest unit. Omit for full refund."),
                ],
                output_schema={"refund_id": "string", "status": "string"},
            ),
        ],
    ),

    "whatsapp": Integration(
        id="whatsapp",
        display_name="WhatsApp via Twilio",
        auth_type="api_key",
        description="Send WhatsApp template messages and notifications via the Twilio API.",
        triggers=[
            TriggerDescriptor(
                id="record_event",
                display_name="Record Event",
                entity_events=["created", "updated", "status_changed", "deleted"],
                description="Fires when a record changes state, triggering a WhatsApp message.",
            ),
        ],
        actions=[
            ActionDescriptor(
                id="send_template_message",
                display_name="Send Template Message",
                description="Send a pre-approved WhatsApp message template via Twilio.",
                input_schema=[
                    ActionInputField(name="to", type="string", required=True,
                                     description="Recipient phone number in E.164 format, e.g. +14155552671"),
                    ActionInputField(name="template_sid", type="string", required=True,
                                     description="Twilio content template SID."),
                    ActionInputField(name="template_variables", type="object", required=False,
                                     description="Key-value pairs for template variable substitution."),
                ],
                output_schema={"message_sid": "string", "status": "string"},
            ),
            ActionDescriptor(
                id="send_notification",
                display_name="Send Notification",
                description="Send a freeform WhatsApp notification message.",
                input_schema=[
                    ActionInputField(name="to", type="string", required=True,
                                     description="Recipient phone number in E.164 format."),
                    ActionInputField(name="body", type="string", required=True,
                                     description="Message body text."),
                ],
                output_schema={"message_sid": "string", "status": "string"},
            ),
        ],
    ),

    "webhook": Integration(
        id="webhook",
        display_name="Generic Webhook",
        auth_type="webhook_secret",
        description="POST a structured payload to any configured URL with HMAC-SHA256 signature.",
        triggers=[
            TriggerDescriptor(
                id="any_event",
                display_name="Any Event",
                entity_events=["created", "updated", "deleted", "status_changed"],
                description="Fires on any entity event - fully configurable.",
            ),
        ],
        actions=[
            ActionDescriptor(
                id="post_payload",
                display_name="POST Payload",
                description="POST a JSON payload to the configured URL with HMAC signature header.",
                input_schema=[
                    ActionInputField(name="url", type="string", required=True,
                                     description="Target URL to POST to."),
                    ActionInputField(name="payload", type="object", required=True,
                                     description="JSON payload to send. Field mappings from the entity."),
                    ActionInputField(name="secret", type="string", required=False,
                                     description="HMAC secret for X-Signature header. Omit to skip signing."),
                    ActionInputField(name="headers", type="object", required=False,
                                     description="Additional HTTP headers to include."),
                ],
                output_schema={"status_code": "number", "response_body": "string"},
            ),
        ],
    ),

    "jira": Integration(
        id="jira",
        display_name="Jira",
        auth_type="api_key",
        description="Create issues, update status, add comments, assign users in Jira projects.",
        is_stub=True,
        triggers=[
            TriggerDescriptor(
                id="task_event",
                display_name="Task / Issue Event",
                entity_events=["created", "updated", "status_changed"],
                description="Fires when a task or issue entity changes.",
            ),
        ],
        actions=[
            ActionDescriptor(
                id="create_issue",
                display_name="Create Issue",
                description="Create a new Jira issue. [STUB - HTTP call not implemented]",
                is_stub=True,
                input_schema=[
                    ActionInputField(name="project_key", type="string", required=True,
                                     description="Jira project key, e.g. ENG"),
                    ActionInputField(name="summary", type="string", required=True,
                                     description="Issue summary / title."),
                    ActionInputField(name="issue_type", type="string", required=True,
                                     description="Issue type: Bug | Task | Story | Epic"),
                    ActionInputField(name="description", type="string", required=False,
                                     description="Issue description body."),
                    ActionInputField(name="assignee", type="string", required=False,
                                     description="Assignee account ID or email."),
                ],
                output_schema={"issue_key": "string", "issue_id": "string", "url": "string"},
            ),
            ActionDescriptor(
                id="update_status",
                display_name="Update Issue Status",
                description="Transition a Jira issue to a new status. [STUB]",
                is_stub=True,
                input_schema=[
                    ActionInputField(name="issue_key", type="string", required=True,
                                     description="Jira issue key, e.g. ENG-42"),
                    ActionInputField(name="transition_name", type="string", required=True,
                                     description="Target status name, e.g. In Progress"),
                ],
                output_schema={"success": "boolean"},
            ),
        ],
    ),

    "google_sheets": Integration(
        id="google_sheets",
        display_name="Google Sheets",
        auth_type="oauth2",
        description="Append rows, update cells, create sheet tabs, and batch-update Google Sheets via the Sheets API v4.",
        is_stub=False,
        triggers=[
            TriggerDescriptor(
                id="data_event",
                display_name="Data Export Event",
                entity_events=["created", "updated", "deleted"],
                description="Fires when records change and should be synced to a spreadsheet.",
            ),
            TriggerDescriptor(
                id="scheduled_export",
                display_name="Scheduled Export",
                entity_events=["status_changed"],
                description="Fires on a schedule or status change to export aggregate data.",
            ),
        ],
        actions=[
            ActionDescriptor(
                id="append_row",
                display_name="Append Row",
                description="Append a new row to a Google Sheet using the spreadsheets.values.append API.",
                is_stub=False,
                input_schema=[
                    ActionInputField(name="spreadsheet_id", type="string", required=True,
                                     description="Google Sheets document ID from the URL."),
                    ActionInputField(name="sheet_name", type="string", required=True,
                                     description="Name of the tab/sheet, e.g. Sheet1."),
                    ActionInputField(name="values", type="array", required=True,
                                     description="Array of cell values for the new row, e.g. [id, name, status]."),
                    ActionInputField(name="value_input_option", type="string", required=False,
                                     description="How values are interpreted: RAW or USER_ENTERED. Defaults to USER_ENTERED."),
                ],
                output_schema={"updated_range": "string", "updated_rows": "number", "spreadsheet_id": "string"},
            ),
            ActionDescriptor(
                id="update_cell",
                display_name="Update Cell",
                description="Update a specific cell or range using spreadsheets.values.update.",
                is_stub=False,
                input_schema=[
                    ActionInputField(name="spreadsheet_id", type="string", required=True,
                                     description="Google Sheets document ID."),
                    ActionInputField(name="range", type="string", required=True,
                                     description="A1 notation range, e.g. Sheet1!B2 or Sheet1!A1:C3."),
                    ActionInputField(name="values", type="array", required=True,
                                     description="2D array of values to write, e.g. [[val1, val2]]."),
                    ActionInputField(name="value_input_option", type="string", required=False,
                                     description="RAW or USER_ENTERED. Defaults to USER_ENTERED."),
                ],
                output_schema={"updated_range": "string", "updated_cells": "number"},
            ),
            ActionDescriptor(
                id="create_sheet_tab",
                display_name="Create Sheet Tab",
                description="Add a new tab/sheet to an existing spreadsheet via batchUpdate.",
                is_stub=False,
                input_schema=[
                    ActionInputField(name="spreadsheet_id", type="string", required=True,
                                     description="Google Sheets document ID."),
                    ActionInputField(name="title", type="string", required=True,
                                     description="Title for the new sheet tab."),
                    ActionInputField(name="index", type="number", required=False,
                                     description="Position index for the new sheet (0-based). Appends at end if omitted."),
                ],
                output_schema={"sheet_id": "number", "title": "string"},
            ),
            ActionDescriptor(
                id="batch_update_rows",
                display_name="Batch Update Rows",
                description="Write multiple ranges in a single API call using spreadsheets.values.batchUpdate.",
                is_stub=False,
                input_schema=[
                    ActionInputField(name="spreadsheet_id", type="string", required=True,
                                     description="Google Sheets document ID."),
                    ActionInputField(name="data", type="array", required=True,
                                     description="Array of {range, values} objects for batch write."),
                    ActionInputField(name="value_input_option", type="string", required=False,
                                     description="USER_ENTERED or RAW."),
                ],
                output_schema={"total_updated_cells": "number", "total_updated_rows": "number"},
            ),
        ],
    ),

    "hubspot": Integration(
        id="hubspot",
        display_name="HubSpot",
        auth_type="api_key",
        description="Create/update contacts, add to sequences, update deal stages in HubSpot.",
        is_stub=True,
        triggers=[
            TriggerDescriptor(
                id="contact_event",
                display_name="Contact or Deal Event",
                entity_events=["created", "updated", "status_changed"],
                description="Fires on CRM contact or deal entity changes.",
            ),
        ],
        actions=[
            ActionDescriptor(
                id="create_contact",
                display_name="Create Contact",
                description="Create or update a HubSpot contact. [STUB]",
                is_stub=True,
                input_schema=[
                    ActionInputField(name="email", type="string", required=True,
                                     description="Contact email address."),
                    ActionInputField(name="firstname", type="string", required=False,
                                     description="First name."),
                    ActionInputField(name="lastname", type="string", required=False,
                                     description="Last name."),
                    ActionInputField(name="properties", type="object", required=False,
                                     description="Additional HubSpot contact properties."),
                ],
                output_schema={"contact_id": "string", "vid": "number"},
            ),
            ActionDescriptor(
                id="update_deal_stage",
                display_name="Update Deal Stage",
                description="Move a HubSpot deal to a new pipeline stage. [STUB]",
                is_stub=True,
                input_schema=[
                    ActionInputField(name="deal_id", type="string", required=True,
                                     description="HubSpot deal ID."),
                    ActionInputField(name="stage_id", type="string", required=True,
                                     description="Target pipeline stage ID."),
                ],
                output_schema={"deal_id": "string", "stage_id": "string"},
            ),
        ],
    ),

    "notion": Integration(
        id="notion",
        display_name="Notion",
        auth_type="api_key",
        description="Create pages, append blocks, and update database rows in Notion.",
        is_stub=True,
        triggers=[
            TriggerDescriptor(
                id="data_change",
                display_name="Data Change",
                entity_events=["created", "updated"],
                description="Fires when data should be synced to a Notion database.",
            ),
        ],
        actions=[
            ActionDescriptor(
                id="create_page",
                display_name="Create Page",
                description="Create a new page in a Notion database. [STUB]",
                is_stub=True,
                input_schema=[
                    ActionInputField(name="database_id", type="string", required=True,
                                     description="Notion database ID."),
                    ActionInputField(name="title", type="string", required=True,
                                     description="Page title."),
                    ActionInputField(name="properties", type="object", required=False,
                                     description="Database property values for the new page."),
                ],
                output_schema={"page_id": "string", "url": "string"},
            ),
            ActionDescriptor(
                id="append_block",
                display_name="Append Block",
                description="Append a content block to an existing Notion page. [STUB]",
                is_stub=True,
                input_schema=[
                    ActionInputField(name="page_id", type="string", required=True,
                                     description="Notion page ID to append to."),
                    ActionInputField(name="block_type", type="string", required=True,
                                     description="Block type: paragraph | heading_1 | bulleted_list_item"),
                    ActionInputField(name="content", type="string", required=True,
                                     description="Text content for the block."),
                ],
                output_schema={"block_id": "string"},
            ),
        ],
    ),

    "twilio_sms": Integration(
        id="twilio_sms",
        display_name="Twilio SMS",
        auth_type="api_key",
        description="Send SMS notifications and OTP flows via Twilio.",
        is_stub=True,
        triggers=[
            TriggerDescriptor(
                id="user_action",
                display_name="User Action or Status Change",
                entity_events=["created", "updated", "status_changed"],
                description="Fires on user-facing events that require an SMS notification.",
            ),
        ],
        actions=[
            ActionDescriptor(
                id="send_sms",
                display_name="Send SMS",
                description="Send an SMS message to a phone number via Twilio. [STUB]",
                is_stub=True,
                input_schema=[
                    ActionInputField(name="to", type="string", required=True,
                                     description="Recipient phone number in E.164 format."),
                    ActionInputField(name="body", type="string", required=True,
                                     description="SMS message body (max 160 chars for single segment)."),
                    ActionInputField(name="from_number", type="string", required=False,
                                     description="Sender Twilio phone number. Uses account default if omitted."),
                ],
                output_schema={"message_sid": "string", "status": "string"},
            ),
            ActionDescriptor(
                id="trigger_otp",
                display_name="Trigger OTP Flow",
                description="Send a one-time passcode via Twilio Verify. [STUB]",
                is_stub=True,
                input_schema=[
                    ActionInputField(name="to", type="string", required=True,
                                     description="Recipient phone number in E.164 format."),
                    ActionInputField(name="channel", type="string", required=True,
                                     description="Delivery channel: sms | call"),
                ],
                output_schema={"verification_sid": "string", "status": "string"},
            ),
        ],
    ),
}


# -- Public helpers ------------------------------------------------------------

def get_integration(integration_id: str) -> Integration | None:
    """Return an Integration by id, or None if not registered."""
    return REGISTRY.get(integration_id)


def list_integration_ids() -> list[str]:
    """Return all registered integration IDs."""
    return list(REGISTRY.keys())


def get_action(integration_id: str, action_id: str) -> ActionDescriptor | None:
    """Return a specific action descriptor, or None if not found."""
    integration = REGISTRY.get(integration_id)
    if not integration:
        return None
    for action in integration.actions:
        if action.id == action_id:
            return action
    return None
