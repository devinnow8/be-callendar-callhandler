import math
from fastapi import APIRouter, Query, Depends, HTTPException, Request, status
import requests
from datetime import datetime, timedelta, timezone
from fastapi.responses import JSONResponse
import requests
import supabase
from datetime import datetime, timedelta
from src.middleware.auth_middleware import get_request_org_user
from src.services.supabase_service import AgentSupabaseService, CallLogService
from src.core.config import settings
import pandas as pd
from dateutil.relativedelta import relativedelta  

router = APIRouter()


def get_start_date(duration: str):
    """ Calculate the date from which we have to filter the call_logs"""
    # Determine the start date based on filter
    today = datetime.utcnow()

    if duration == "last_day":
        start_date = today - timedelta(days=1)
    elif duration == "last_week":
        start_date = today - timedelta(weeks=1)
    else:  # Default to last_month
        start_date = today - timedelta(days=30)

    return start_date.strftime("%Y-%m-%d")


@router.get("/dashboard-metrics")
async def get_dashboard_metrics(
    user_org = Depends(get_request_org_user),
    duration: str = Query("last_month", enum=["last_day", "last_week", "last_month"]),
    agent_seupabase_service: AgentSupabaseService = Depends(),
    call_log_seupabase_service: CallLogService = Depends(),

    ):
    """
    Fetches:
    - Call Metrics (Total Calls, Duration, Cost)
    - Call Trends (Filtered by last_day, last_week, or last_month)
    - Agent Performance
    """
    try:
        # Determine the start date based on filter
        start_date_str = get_start_date(duration)
        user = user_org['user']
        organisation = user_org['organisation']
        # ------------------ Fetch Call Data from Supabase ------------------
        org_agent_list = agent_seupabase_service.get_org_agents_by_organisation_id(org_id=organisation['id'], fields='id')
        if not org_agent_list:
            return {
                "call_metrics": {"total_calls": 0, "total_duration": 0, "total_cost": 0},
                "call_trends": [],
                "agents": []
            }
        
        agent_list = [agent['id'] for agent in  org_agent_list] 
        response = call_log_seupabase_service.get_duration_filtered_call_logs_of_an_org(start_date=start_date_str, agent_list=agent_list)
        if not response:
            return {
                "call_metrics": {"total_calls": 0, "total_duration": 0, "total_cost": 0},
                "call_trends": [],
                "agents": []
            }

        df = response

        # ------------------ Call Metrics ------------------
        total_calls = len(df)
        total_duration = sum(call["duration_billed"] for call in df if call["duration_billed"] is not None)
        total_cost = sum(call["total_cost"] for call in df if call["total_cost"] is not None)

        call_metrics = {
            "total_calls": total_calls,
            "total_duration": total_duration,
            "total_cost": total_cost
        }

        # ------------------ Call Trends ------------------
        call_counts = {}
        for entry in df:
            date_str = entry["created_at"][:10]  # Extract YYYY-MM-DD
            call_counts[date_str] = call_counts.get(date_str, 0) + 1

        call_trends = [{"date": date, "total_calls": count} for date, count in sorted(call_counts.items())]

        # ------------------ Agent Performance ------------------
        agent_stats = {}
        for entry in df:
            agent_id = entry["agent_id"]
            # agent_name = entry["human_name"]
            duration_tmp = entry["duration_billed"] if entry["duration_billed"] is not None else 0
            is_success = 1 if entry["hangup_cause"] == "Normal Hangup" else 0

            if agent_id not in agent_stats:
                agent_stats[agent_id] = {
                    "agent_id": agent_id,
                    # "agent_name": agent_name,
                    "calls_handled": 0,
                    "successful_calls": 0,
                    "total_duration": 0
                }

            agent_stats[agent_id]["calls_handled"] += 1
            agent_stats[agent_id]["successful_calls"] += is_success
            agent_stats[agent_id]["total_duration"] += duration_tmp

        agents = []
        for stats in agent_stats.values():
            success_rate = (stats["successful_calls"] / stats["calls_handled"]) * 100 if stats["calls_handled"] > 0 else 0
            avg_duration = stats["total_duration"] / stats["calls_handled"] if stats["calls_handled"] > 0 else 0

            agents.append({
                "agent_id": stats["agent_id"],
                # "agent_name": stats["agent_name"],
                "calls_handled": stats["calls_handled"],
                "success_rate": round(success_rate, 2),
                "average_call_duration": round(avg_duration, 2)
            })

        # ------------------ Return Combined Response ------------------
        return {
            "duration": duration,  # Return duration for frontend reference
            "call_metrics": call_metrics,
            "call_trends": call_trends,
            "agents_performance": agents
        }
    
    except HTTPException as e:
        raise HTTPException(status_code=400, detail=e.detail)

    except Exception as e:
        print("error is", e)
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")




@router.get("/call-logs/{agent_id}")
async def get_call_logs(
    agent_id: str,
    user_org = Depends(get_request_org_user),
    agent_seupabase_service: AgentSupabaseService = Depends(),
    call_log_seupabase_service: CallLogService = Depends(),
    page: int = Query(1, description="Page number"),
    page_size: int = Query(10, description="Number of records per page"),
):
    try:
        organisation = user_org['organisation']
        agent = agent_seupabase_service.get_agent_by_id(id= agent_id, fields="id, organisation_id")
        if not agent or agent['organisation_id'] != organisation['id']:
            raise HTTPException(status_code=400, detail="agent not found")
        
        # Query to get the total count of records for the agent_id
        count_response = call_log_seupabase_service.get_total_count_of_call_logs_by_agent_id(agent_id=agent_id)
        
        # Get total records count, default to 0 if no result
        total_records = count_response.count or 0

        # Calculate total pages
        total_pages = math.ceil(total_records / page_size)

        # If total_records is greater than the current page range, proceed with data query
        if total_records > (page - 1) * page_size:
            # Main query to fetch paginated data
            response = call_log_seupabase_service.get_paginated_call_logs_by_agent_id(
                agent_id = agent_id,
                page=page,
                page_size=page_size,
                fields="call_logs_id, duration_billed, phone_number, elevenlabs_conversation_id, created_at, agent_id, human_name, hangup_cause"
            )

            # Check for errors in response
            if not response:
                raise HTTPException(status_code=400, detail=f"Database error")

            return {
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "data": response,
            }
        
        # If no data to show for the requested page, return empty data
        return {
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "data": [],
        }

    except Exception as e:
        # Handle unexpected errors
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.get("/stats/{agent_id}")
async def get_agent_stats(
    agent_id: str,
    user_org = Depends(get_request_org_user),
    agent_seupabase_service: AgentSupabaseService = Depends(),
    call_log_seupabase_service: CallLogService = Depends(),
    duration: str = Query("last_month", enum=["last_day", "last_week", "last_month"])
):
    try:
        """
        Fetches:
        - Call Metrics (Total Calls, Duration, Cost) for a specific agent
        - Call Trends (Filtered by last_day, last_week, or last_month)
        - Agent Performance
        - Call Success Rate (Normal Hangup %)
        """
        organisation = user_org['organisation']
        agent = agent_seupabase_service.get_agent_by_id(id= agent_id, fields="id, organisation_id")
        if not agent or agent['organisation_id'] != organisation['id']:
            raise HTTPException(status_code=400, detail="agent not found")
        
        # Determine the start date based on filter
        start_date_str = get_start_date(duration)

        # ------------------ Fetch Call Data from Supabase ------------------
        
        response = call_log_seupabase_service.get_duration_filtered_call_logs_of_an_agent(agent_id= agent_id,  fields = "call_logs_id, duration, duration_billed, total_cost, created_at, agent_id, human_name, hangup_cause", start_date=start_date_str)
            

        if not response:
            return {
                "call_metrics": {"total_calls": 0, "total_duration": 0, "total_cost": 0, "call_success_rate": 100.00},
                "call_trends": [],
                "agents": [],
                # "hangup_cause_distribution": {}
            }

        df = response

        # ------------------ Call Metrics ------------------
        total_calls = len(df)
        total_duration = sum(call["duration_billed"] for call in df if call["duration_billed"] is not None)
        total_cost = sum(call["total_cost"] for call in df if call["total_cost"] is not None)

        call_metrics = {
            "total_calls": total_calls,
            "total_duration": total_duration,
            "total_cost": total_cost
        }

        # ------------------ Call Trends ------------------
        call_counts = {}
        for entry in df:
            date_str = entry["created_at"][:10]  # Extract YYYY-MM-DD
            call_counts[date_str] = call_counts.get(date_str, 0) + 1

        call_trends = [{"date": date, "total_calls": count} for date, count in sorted(call_counts.items())]

        # ------------------ Agent Performance ------------------
        agent_stats = {}
        successful_calls = 0
        # hangup_cause_counts = {}
        for entry in df:
            agent_id = entry["agent_id"]
            # agent_name = entry["human_name"]
            duration_tmp = entry["duration_billed"] if entry["duration_billed"] is not None else 0
            is_success = 1 if entry["hangup_cause"] == "Normal Hangup" else 0

            successful_calls += is_success

            # hangup_cause = entry["hangup_cause"]
            # hangup_cause_counts[hangup_cause] = hangup_cause_counts.get(hangup_cause, 0) + 1
            
            if agent_id not in agent_stats:
                agent_stats[agent_id] = {
                    "agent_id": agent_id,
                    # "agent_name": agent_name,
                    "calls_handled": 0,
                    "successful_calls": 0,
                    "total_duration": 0
                }

            agent_stats[agent_id]["calls_handled"] += 1
            agent_stats[agent_id]["successful_calls"] += is_success
            agent_stats[agent_id]["total_duration"] += duration_tmp

        agents = []
        for stats in agent_stats.values():
            success_rate = (stats["successful_calls"] / stats["calls_handled"]) * 100 if stats["calls_handled"] > 0 else 0
            avg_duration = stats["total_duration"] / stats["calls_handled"] if stats["calls_handled"] > 0 else 0

            agents.append({
                "agent_id": stats["agent_id"],
                # "agent_name": stats["agent_name"],
                "calls_handled": stats["calls_handled"],
                "success_rate": round(success_rate, 2),
                "average_call_duration": round(avg_duration, 2)
            })

        # ------------------ Call Success Rate ------------------
        call_success_rate = (successful_calls / total_calls) * 100 if total_calls > 0 else 0.0

        # ------------------ Return Combined Response ------------------
        return {
            "duration": duration,
            "agent_id": agent_id,
            "call_metrics": {
                **call_metrics,
                "call_success_rate": round(call_success_rate, 2)
            },
            "call_trends": call_trends,
            "agents_performance": agents,
            # "hangup_cause_distribution": hangup_cause_counts
            
        }

    except Exception as e:
        # Handle unexpected errors
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


