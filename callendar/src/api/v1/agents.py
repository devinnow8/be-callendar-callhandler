
from fastapi import APIRouter, Depends, HTTPException, Request
from src.services.elevenlabs_service import ElevenLabsService
from src.schemas.agents import CreateAgentRequest
from src.middleware.auth_middleware import get_current_user, get_request_org_user
from src.services.auth import auth_service
from src.services.supabase_service import AgentSupabaseService, OrgService, OrgUserService,  UserService
from src.core.config import settings
import requests

router = APIRouter()

@router.get("/agents")  # protected by backend middleware
async def get_agents(
     user_org = Depends(get_request_org_user),
     agent_seupabase_service: AgentSupabaseService = Depends(),
    ):
    """
    Fetch agents for the current user along with their associated phone numbers.
    """
   

    try:
        organisation = user_org['organisation']
        agents = agent_seupabase_service.get_org_agents_by_organisation_id(org_id=organisation['id'])
        if not agents:
            raise HTTPException(status_code=400, detail="Agents not found")
        
        return agents
    
    except HTTPException as e:
        raise HTTPException(status_code=400, detail=e.detail)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


@router.post("/agents")
def create_agent(
    body: CreateAgentRequest,
    request: Request,
    agent_supabase_service: AgentSupabaseService = Depends(),
    org_supabase_service: OrgService = Depends(),
    org_user_supabase_service: OrgUserService = Depends(),
    user_org = Depends(get_request_org_user)

):
    try:
       # step1: check for the organisation who want to create the agent
       user = user_org['user']
       organisation = user_org['organisation']

       agent = agent_supabase_service.insert_agent_to_supabase({
            "organisation_id": organisation["id"],
            "template_id": body.template_id,
            "name": body.name,
            "description": body.description,
            "elevenlabs_agent_id": body.elevenlabs_agent_id,
            "type": body.type,
            "state": "active"
            })
       
       return agent
    
    except HTTPException as e:
        raise HTTPException(status_code=400, detail=e.detail)
      
    except Exception as e:
        raise HTTPException(status_code=400, detail="Failed to create agent")
# # we are gonna link agent to a phone while creating it only
# @router.post("/agents")
# def create_agent(
#     name: str,
#     prompt: str = "",
#     phone: str = "",
#     user = Depends(get_current_user)
# ):
#     """
#     Creates a new agent in ElevenLabs and then stores the agent_id in our local DB.
#     """
#     print("user is", user)
#     user_id = user["user"].user.id
#     payload = {
#         "conversation_config": {  
#             "agent": {
#                 "prompt": {
#                     "prompt": prompt,            # TODO: change prompt to be dynamic from user input and containing exact details including knowledge bases and tools etc
#                 "llm": "gemini-1.5-flash",# default LLM
#                 "max_tokens": -1,         # default is -1
#                 "temperature": 0,         # default is 0
#                 "tools": [                # We only add webhooks for now
#                     {
#                       "type": "webhook",
#                       "api_schema": {
#                         "url": f"{settings.URL}/api/v1/callendar/events",
#                         "method": "GET",
                       
#                         "query_params_schema": {
#                           "properties": {
#                             "startTime": {
#                               "type": "string",
#                               "description": "The start time for the calendar query in ISO8601 format"
#                             },
#                             "endTime": {
#                               "type": "string",
#                               "description": "The end time for the calendar query in ISO8601 format"
#                             }
#                           }
#                         }
#                       },
#                       "name": "Get_Available_Slots",
#                       "description": "This endpoint returns slots available in calendar from above API result",
#                     }

#                 ]
#             },
#             "knowledge_base": [],
#             "first_message": f"You are agent with name {name}"
#         }
#         },
#         "name": name
#     }

#     elevenlabs_api_key = settings.ELEVENLABS_API_KEY
#     if not elevenlabs_api_key:
#         raise HTTPException(
#             status_code=500,
#             detail="Missing ELEVENLABS_API_KEY in environment"
#         )

#     headers = {
#         "xi-api-key": elevenlabs_api_key,
#         "Content-Type": "application/json"
#     }

#     url = "https://api.elevenlabs.io/v1/convai/agents/create"
#     response = requests.post(url, headers=headers, json=payload)
#     print("response from agent creation is", response.json())

#     if not response.ok:
#         raise HTTPException(
#             status_code=response.status_code,
#             detail=f"Failed to create agent in ElevenLabs. {response.text}"
#         )

#     data = response.json()

#     agent_id = data["agent_id"]
#     print("agent_id is", agent_id)

#     auth_service.client.table("agents").insert({
#         "agent_id": agent_id,
#         "user_id": user_id,
#         "agent_name": name
#     }).execute()

#     if not agent_id:
#         raise HTTPException(
#             status_code=500,
#             detail="Could not find agent_id in ElevenLabs response."
#         )
    
#     phone_query = auth_service.client.table("phone_numbers").select("*").eq("phone_number", phone).eq("user_id", user_id).execute()
#     if not phone_query.data:
#         raise HTTPException(status_code=400, detail="Phone number does not belong to the current user.")
    
#     mapping_query = auth_service.client.table("phone_agent_mapping").select("*").eq("phone_number", phone).eq("agent_id", agent_id).execute()
#     if mapping_query.data:
#         raise HTTPException(status_code=400, detail="Phone number is already linked to this agent.")
    
#     auth_service.client.table("phone_agent_mapping").insert({
#             "phone_number": phone,
#             "agent_id": agent_id,
#             "user_id": user_id
#         }).execute()
#     # 5) Return success
#     return {
#         "message": "Agent created successfully",
#         "agent_id": agent_id,
#         "user_id": user_id,
#         "phone_number": phone
#     }







@router.post("/agents/duplicate/{agent_id}")
def duplicate_agent(agent_id: str):
    """
    Fetch an existing agent from ElevenLabs and create a duplicate agent with a new name.
    """
    print(f"Fetching existing agent details for agent_id: {agent_id}")

    # Step 1: Fetch the existing agent details
    ELEVENLABS_API_BASE_URL = "https://api.elevenlabs.io/v1/convai"
    elevenlabs_api_key = settings.ELEVENLABS_API_KEY
    if not elevenlabs_api_key:
        raise HTTPException(
            status_code=500,
            detail="Missing ELEVENLABS_API_KEY in environment"
        )

    HEADERS = {
        "xi-api-key": elevenlabs_api_key,
        "Content-Type": "application/json"
    }

    agent_url = f"{ELEVENLABS_API_BASE_URL}/agents/{agent_id}"
    agent_response = requests.get(agent_url, headers=HEADERS)
    print("agent_response is", agent_response.json())

    if agent_response.status_code != 200:
        raise HTTPException(status_code=agent_response.status_code, detail="Failed to fetch existing agent details")

    agent_data = agent_response.json()

    # Modify the name to include "dev"
    new_agent_name = f"{agent_data['name']}-dev"
    
    # Remove unnecessary fields that are not required for creation
    agent_data.pop("agent_id", None)  # Remove the existing agent ID
    agent_data["name"] = new_agent_name  # Change the name

    # Step 2: Create a new agent with modified details
    create_agent_url = f"{ELEVENLABS_API_BASE_URL}/agents/create"
    create_response = requests.post(create_agent_url, headers=HEADERS, json=agent_data)

    if create_response.status_code != 200:
        raise HTTPException(status_code=create_response.status_code, detail="Failed to create duplicate agent")

    new_agent = create_response.json()
    new_agent_id = new_agent.get("agent_id")
    print(f"New duplicated agent created with ID: {new_agent_id}")

    return {
        "message": "Agent duplicated successfully",
        "original_agent_id": agent_id,
        "new_agent_id": new_agent_id,
        "new_agent_name": new_agent_name
    }