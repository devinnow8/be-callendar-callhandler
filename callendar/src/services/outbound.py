from abc import ABC, abstractmethod
from datetime import datetime, timedelta
import enum
from typing import Dict, Optional
from fastapi import HTTPException
import pytz
from src.services.supabase_service import (
    CampaignService,
    ScheduledCallService,
    AgentSupabaseService,
)


class BaseOutboundCall(ABC):
    def __init__(
        self,
        customer_id: str,
    ):
        self.customer_id = customer_id

    @abstractmethod
    async def get_call_details(self) -> Dict:
        """Get call details for the specific outbound call type"""
        pass

    @abstractmethod
    async def update_call_details_on_trigger(
        self, status: bool, call_details: Optional[Dict] = None
    ):
        """Update call details when call is triggered"""
        pass

    @abstractmethod
    async def update_call_details_on_hangup(self, status: bool):
        """Update call details when call is hung up"""
        pass

    @abstractmethod
    async def get_agent_conversation_data(self):
        """Get agent conversation data"""
        pass
    
    @abstractmethod
    async def stop_outbound_calls(self, *args, **kwargs):
        """To stop or properly finish the ongoing calls in case of subscription over or other similar scenarios"""
        pass

class CampaignOutboundCall(BaseOutboundCall):
    """Campaign outbound call specific operations"""

    def __init__(self, customer_id: str):
        super().__init__(customer_id)
        self.campaign_service = CampaignService()
        self.agent_service = AgentSupabaseService()

    async def get_call_details(self):
        """Get campaign call details"""
        scheduled_call = self.campaign_service.get_campaign_call_by_id(
            id=self.customer_id,
            fields="phone_number, campaign_id, agent_id, total_calls, retry, from_number, data",
        )

        if not scheduled_call:
            raise HTTPException(status_code=404, detail="Scheduled call not found")

        campaign = self.campaign_service.get_campaign_by_id(
            scheduled_call["campaign_id"], fields="organisation_id, agent_id"
        )

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        scheduled_call["organisation_id"] = campaign["organisation_id"]
        scheduled_call["usecase_id"] = scheduled_call["campaign_id"]
        scheduled_call["agent_id"] = campaign["agent_id"]  # in case if campaign agent is updated we are going to use the campaign agent for this call.
        scheduled_call["to_number"] = scheduled_call["phone_number"]
        scheduled_call["type"] = "campaign_outbound"
        scheduled_call["customer_id"] = self.customer_id
        return scheduled_call

    async def update_call_details_on_trigger(
        self, status: bool, call_details: Optional[Dict] = None
    ):
        """Update campaign details on call creation"""
        if not status:
            return self.campaign_service.update_campaign_scheduled_call(
                id=self.customer_id,
                data={
                    "agent_id": call_details["agent_id"],  # in case if campaign agent is updated we are going to use the campaign agent for this call.
                    "status": "Not Initiated",
                    "retry": call_details["retry"] - 1,
                    "next_possible_call_date": (
                        datetime.now(pytz.utc).date() + timedelta(days=1)
                    ).strftime("%Y-%m-%d"),
                },
            )

        call = self.campaign_service.update_campaign_scheduled_call(
            id=self.customer_id,
            data={
                "agent_id": call_details[
                    "agent_id"
                ],  # in case if campaign agent is updated we are going to use the campaign agent for this call.
                "status": "In Process",
                "total_calls": call_details["total_calls"] + 1,
                "retry": call_details["retry"] - 1,
            },
        )

        self.campaign_service.update_campaign_phone_number_status(
            campaign_id=call_details["campaign_id"],
            phone_number=call_details["from_number"],
            status="Unavailable",
        )

        print(
            "call triggered on provider service successfully for customer id: ",
            self.customer_id,
            " and call logs id: ",
            call_details["call_logs_id"],
        )

        return call

    async def update_call_details_on_hangup(
        self,
        status: bool,
    ) -> Dict:
        """Update campaign with call on hangup"""
        data = {}
        if status:
            data = {"status": "Completed"}

        else:
            data = {
                "status": "Not Initiated",
                "next_possible_call_date": (
                    datetime.now(pytz.utc).date() + timedelta(days=1)
                ).strftime("%Y-%m-%d"),
            }
        call = self.campaign_service.update_campaign_scheduled_call(
            id=self.customer_id, data=data
        )

        # update the campaign phone number status
        self.campaign_service.update_campaign_phone_number_status(
            campaign_id=call["campaign_id"],
            phone_number=call["from_number"],
            status="available",
        )

        return call

    async def get_agent_conversation_data(self):
        """Get agent conversation data"""
        call_details = self.campaign_service.get_campaign_call_by_id(
            id=self.customer_id,
            fields="agent_id, data",
        )

        # get the agent data
        agent_data = self.agent_service.get_agent_by_id(
            id=call_details["agent_id"],
            fields="id, elevenlabs_agent_id, metadata",
        )

        agent_data["data"] = call_details["data"]
        return agent_data

    async def stop_outbound_calls(self, *args, **kwargs):
        """
        Stop outbound calls
        Keyword Args:
            campaign_id: str
        """
        print(f"stopping outbound calls for campaign id: {kwargs['campaign_id']}: reason: {kwargs['reason']}")
        return self.campaign_service.update_campaign(
            campaign_id=kwargs["campaign_id"],
            data={
                "status": "Stopped"
            },
        )

class ScheduledOutboundCall(BaseOutboundCall):
    """Scheduled outbound call specific operations"""

    def __init__(self, customer_id: str):
        super().__init__(customer_id)
        self.scheduled_call_service = ScheduledCallService()
        self.agent_service = AgentSupabaseService()

    async def get_call_details(self):
        """Get fixed timestamp scheduled call details"""
        print("getting call details")
        scheduled_call = self.scheduled_call_service.get_scheduled_call_by_call_id(
            call_id=self.customer_id,
            fields="to_number, agent_id, organisation_id, from_number",
        )
        print(f"scheduled call: {scheduled_call}")

        if not scheduled_call:
            print("scheduled call not found")
            raise HTTPException(status_code=404, detail="Scheduled call not found")

        scheduled_call["customer_id"] = self.customer_id
        scheduled_call["usecase_id"] = self.customer_id
        scheduled_call["type"] = "scheduled_outbound"
        print(f"scheduled call: {scheduled_call}")
        return scheduled_call

    async def update_call_details_on_trigger(
        self, status: bool, call_details: Optional[Dict] = None
    ):
        """Update scheduled call details on creation"""
        status = "Failed" if not status else "In Process"
        print(f"updating scheduled call details on creation: {status}")
        return self.scheduled_call_service.update_scheduled_call(
            call_id=self.customer_id, data={"status": status}
        )

    async def update_call_details_on_hangup(self, status: bool):
        """Update scheduled call details on hangup"""
        print("updating scheduled call details on hangup")
        return self.scheduled_call_service.update_scheduled_call(
            call_id=self.customer_id, data={"status": "Completed"}
        )

    async def stop_outbound_calls(self, *args, **kwargs):
        """
        Stop outbound calls
        Keyword Args:
            reason: str
        """
        return self.scheduled_call_service.update_scheduled_call(
            call_id=self.customer_id, data={"status": "Failed", "metadata": {"reason": kwargs.get("reason", "Unknown")}}
        )

    async def get_agent_conversation_data(self):
        """Get agent conversation data"""
        call_details = self.scheduled_call_service.get_scheduled_call_by_call_id(
            call_id=self.customer_id,
            fields="agent_id, data",
        )

        # get the agent data
        agent_data = self.agent_service.get_agent_by_id(
            id=call_details["agent_id"],
            fields="id, elevenlabs_agent_id, metadata",
        )

        agent_data["data"] = call_details["data"]
        return agent_data
