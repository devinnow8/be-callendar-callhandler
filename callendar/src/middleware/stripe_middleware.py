from fastapi import Depends, Request, HTTPException, status, Header
from src.services.supabase_service import OrgService, StripeService 
from uuid import UUID
from src.services.posthog_service import posthog_service
from datetime import datetime

# First create service instances
org_service = OrgService()
stripe_service = StripeService()


# Enhanced middleware for authentication
async def validate_stripe_subscription(token_data: dict):
    """
    Validate the Stripe subscription status for the user.

    This middleware checks if the user has an active Stripe subscription.
    If the user does not have an active subscription, it raises a 403 Forbidden error.
    """
    try:
        org_id = token_data["org_id"]

        # # Use the instantiated services
        # org = org_service.get_organisation_by_id(org_id)
        # if not org:
        #     posthog_service.capture_event(
        #         event_name="stripe_subscription_check_failed",
        #         distinct_id=org_id,
        #         properties={
        #             "error": "Organisation not found",
        #             "organisation_id": org_id
        #         }
        #     )
        #     error_response(400, "Organisation not found")

        # stripe_subscription = await stripe_service.get_stripe_subscription_by_org_id(org_id)
        # if not stripe_subscription:
        #     posthog_service.capture_event(
        #         event_name="stripe_subscription_check_failed",
        #         distinct_id=org_id,
        #         properties={
        #             "error": "Stripe subscription not found for the organisation",
        #             "organisation_id": org_id
        #         }
        #     )
        #     error_response(400, "Please subscribe to a desired plan to continue")

        # if stripe_subscription["status"] != "active":
        #     posthog_service.capture_event(
        #         event_name="stripe_subscription_check_failed",
        #         distinct_id=org_id,
        #         properties={
        #             "error": "Subscription not active",
        #             "organisation_id": org_id,
        #             "subscription_status": stripe_subscription["status"]
        #         }
        #     )
        #     return False
        #     # error_response(400, "Stripe subscription not active")

        # # check if the subscription has expired
        # current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S%z")
        # if stripe_subscription["end_date"] < current_time:
        #     posthog_service.capture_event(
        #         event_name="stripe_subscription_check_failed",
        #         distinct_id=org_id,
        #         properties={
        #             "error": "Subscription expired",
        #             "organisation_id": org_id
        #         }
        #     )
        #     return False
        #     # error_response(400, "Stripe subscription has expired")

        subscription_details = await org_service.get_organisation_subscription_details(
            org_id
        )

        if subscription_details.get("is_unlocked") == True:
            posthog_service.capture_event(
                event_name="stripe_subscription_check_success",
                distinct_id=org_id,
                properties={
                    "organisation_id": org_id,
                    "is_unlocked": True,
                },
            )
            return True

        if not subscription_details.get("total_call_minutes", 0):
            posthog_service.capture_event(
                event_name="stripe_subscription_check_failed",
                distinct_id=org_id,
                properties={
                    "error": "Stripe subscription not found for the organisation",
                    "organisation_id": org_id,
                },
            )
            return False

        remaining_calls = subscription_details.get("total_calls_allowed", 0) - (
            subscription_details.get("calls_consumed", 0)
        )
        remaining_call_minutes = subscription_details.get("total_call_minutes", 0) - (
            subscription_details.get("consumed_call_minutes", 0)
        )

        if remaining_calls <= 0 or remaining_call_minutes <= 0:
            posthog_service.capture_event(
                event_name="stripe_subscription_check_failed",
                distinct_id=org_id,
                properties={
                    "error": "No remaining calls or minutes",
                    "organisation_id": org_id,
                    "remaining_calls": remaining_calls,
                    "remaining_minutes": remaining_call_minutes,
                },
            )
            return False
            # error_response(400, "Stripe subscription has no remaining calls or minutes")

        posthog_service.capture_event(
            event_name="stripe_subscription_check_success",
            distinct_id=org_id,
            properties={
                "organisation_id": org_id,
                "remaining_calls": remaining_calls,
                "remaining_minutes": remaining_call_minutes,
            },
        )
        return True

    except HTTPException:
        raise

    except Exception as e:
        print(f"Error checking subscription: {str(e)}")
        posthog_service.capture_event(
            event_name="subscription_check_error",
            distinct_id=org_id if "org_id" in locals() else "unknown",
            properties={
                "error": str(e),
                "organisation_id": org_id if "org_id" in locals() else None,
            },
        )
        return False
