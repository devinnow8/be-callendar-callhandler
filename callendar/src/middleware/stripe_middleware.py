from fastapi import Depends, Request, HTTPException, status, Header
from src.services.supabase_service import OrgService, StripeService
from uuid import UUID
from src.services.posthog_service import posthog_service
from datetime import datetime

# First create service instances
org_service = OrgService()
stripe_service = StripeService()


# Enhanced middleware for authentication
async def validate_stripe_subscription(org_id: UUID):
    """
    Validate the Stripe subscription status for the user.

    This middleware checks if the user has an active Stripe subscription.
    If the user does not have an active subscription, it raises a 403 Forbidden error.
    """
    try:
        # org_id = token_data["org_id"]

        print("org_id", org_id)
        print("in validate_stripe_subscription...........")

        # Use the instantiated services
        org = org_service.get_organisation_by_id(
            org_id, fields="id, calls_consumed, consumed_call_minutes"
        )
        print("org...........", org)
        if not org:
            print("Organisation not found for org_id:", org_id)
            posthog_service.capture_event(
                event_name="stripe_subscription_check_failed",
                distinct_id=org_id,
                properties={
                    "error": "Organisation not found",
                    "organisation_id": org_id,
                },
            )
            return False
            # error_response(400, "Organisation not found")

        print("Found organisation:", org)
        stripe_subscription = await stripe_service.get_stripe_subscription_by_org_id(
            org_id
        )
        print("stripe_subscription...........", stripe_subscription)
        if not stripe_subscription:
            # print("No stripe subscription found for org_id:", org_id)
            posthog_service.capture_event(
                event_name="stripe_subscription_check_failed",
                distinct_id=org_id,
                properties={
                    "error": "Stripe subscription not found for the organisation",
                    "organisation_id": org_id,
                },
            )
            return False
            # error_response(400, "Stripe subscription not found")

        # print("Found stripe subscription:", stripe_subscription)
        if stripe_subscription["status"] != "active":
            # print("Stripe subscription not active. Status:", stripe_subscription["status"])
            posthog_service.capture_event(
                event_name="stripe_subscription_check_failed",
                distinct_id=org_id,
                properties={
                    "error": "Subscription not active",
                    "organisation_id": org_id,
                    "subscription_status": stripe_subscription["status"],
                },
            )
            return False
            # error_response(400, "Stripe subscription not active")

        # check if the subscription has expired
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S%z")
        print(
            "Checking subscription expiry. Current time:",
            current_time,
            "End date:",
            stripe_subscription["end_date"],
        )
        if stripe_subscription["end_date"] < current_time:
            print("Subscription expired")
            posthog_service.capture_event(
                event_name="stripe_subscription_check_failed",
                distinct_id=org_id,
                properties={"error": "Subscription expired", "organisation_id": org_id},
            )
            return False
            # error_response(400, "Stripe subscription has expired")

        remaining_calls = stripe_subscription["total_calls_allowed"] - (
            org["calls_consumed"] if org["calls_consumed"] else 0
        )
        remaining_call_minutes = stripe_subscription["total_call_minutes"] - (
            org["consumed_call_minutes"] if org["consumed_call_minutes"] else 0
        )

        print(
            "Remaining calls:",
            remaining_calls,
            "Remaining minutes:",
            remaining_call_minutes,
        )
        if remaining_calls <= 0 or remaining_call_minutes <= 0:
            print("No remaining calls or minutes available")
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

        print("Stripe subscription validation successful")
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
        # error_response(500, f"Error checking subscription: {str(e)}")
        # raise HTTPException(status_code=500, detail=f"Error checking subscription: {str(e)}")
