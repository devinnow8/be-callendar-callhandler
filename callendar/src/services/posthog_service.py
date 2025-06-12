import posthog
from typing import Dict, Any, Optional, List
import logging
from ..core.config import settings
from datetime import datetime

logger = logging.getLogger(__name__)

class PostHogService:
    """
    Service for handling PostHog analytics and event tracking.
    """
    
    def __init__(self):
        """Initialize PostHog client with API key and host."""
        self.client = posthog.Client(
            api_key=settings.POSTHOG_API_KEY,
            host=settings.POSTHOG_HOST,
            debug=settings.POSTHOG_DEBUG
        )
        print("key...:", settings.POSTHOG_API_KEY)
        print("posthog initialized..........: ", self.client)
        logger.info(f"PostHog initialized with host: {settings.POSTHOG_HOST}")
    
    def capture_event(
        self,
        event_name: str,
        distinct_id: str,
        properties: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
        organization_id: Optional[str] = None,
        user_id: Optional[str] = None,
        # user_agent: Optional[str] = None,
    ) -> bool:
        """
        Capture an event in PostHog.
        
        Args:
            event_name: Name of the event
            distinct_id: Unique identifier for the user
            properties: Additional properties for the event
            timestamp: When the event occurred
            organization_id: ID of the organization
            user_id: ID of the user
            user_agent: User agent string
            
        Returns:
            bool: True if event was captured successfully
        """
        try:
            # Prepare properties
            event_properties = properties or {}
            
            # Add standard properties
            if organization_id:
                event_properties["organization_id"] = organization_id
            if user_id:
                event_properties["user_id"] = user_id
            
            # Capture the event
            self.client.capture(
                distinct_id=distinct_id,
                event=event_name,
                properties=event_properties,
                timestamp=timestamp,
                # user_agent=user_agent,
            )
            
            logger.debug(f"Captured event: {event_name} for user: {distinct_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to capture PostHog event: {str(e)}")
            return False
    
    def identify_user(
        self,
        distinct_id: str,
        properties: Optional[Dict[str, Any]] = None,
        organization_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Identify a user in PostHog.
        
        Args:
            distinct_id: Unique identifier for the user
            properties: Additional properties for the user
            organization_id: ID of the organization
            user_id: ID of the user
            
        Returns:
            bool: True if user was identified successfully
        """
        try:
            # Prepare properties
            user_properties = properties or {}
            
            # Add standard properties
            if organization_id:
                user_properties["organization_id"] = organization_id
            if user_id:
                user_properties["user_id"] = user_id
            
            # Identify the user
            self.client.identify(
                distinct_id=distinct_id,
                properties=user_properties,
            )
            
            logger.debug(f"Identified user: {distinct_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to identify PostHog user: {str(e)}")
            return False
    
    def set_user_properties(
        self,
        distinct_id: str,
        properties: Dict[str, Any],
    ) -> bool:
        """
        Set properties for a user in PostHog.
        
        Args:
            distinct_id: Unique identifier for the user
            properties: Properties to set for the user
            
        Returns:
            bool: True if properties were set successfully
        """
        try:
            # Set user properties
            self.client.people_set(
                distinct_id=distinct_id,
                properties=properties,
            )
            
            logger.debug(f"Set properties for user: {distinct_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set PostHog user properties: {str(e)}")
            return False
    
    def increment_user_property(
        self,
        distinct_id: str,
        property_name: str,
        increment_by: int = 1,
    ) -> bool:
        """
        Increment a property for a user in PostHog.
        
        Args:
            distinct_id: Unique identifier for the user
            property_name: Name of the property to increment
            increment_by: Amount to increment by
            
        Returns:
            bool: True if property was incremented successfully
        """
        try:
            # Increment user property
            self.client.people_increment(
                distinct_id=distinct_id,
                properties={property_name: increment_by},
            )
            
            logger.debug(f"Incremented property {property_name} for user: {distinct_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to increment PostHog user property: {str(e)}")
            return False
    
    def group_identify(
        self,
        group_type: str,
        group_key: str,
        properties: Dict[str, Any],
    ) -> bool:
        """
        Identify a group in PostHog.
        
        Args:
            group_type: Type of the group (e.g., 'organization')
            group_key: Key of the group
            properties: Properties for the group
            
        Returns:
            bool: True if group was identified successfully
        """
        try:
            # Identify the group
            self.client.group_identify(
                group_type=group_type,
                group_key=group_key,
                properties=properties,
            )
            
            logger.debug(f"Identified group: {group_type}:{group_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to identify PostHog group: {str(e)}")
            return False
    
    def group_set(
        self,
        group_type: str,
        group_key: str,
        properties: Dict[str, Any],
    ) -> bool:
        """
        Set properties for a group in PostHog.
        
        Args:
            group_type: Type of the group (e.g., 'organization')
            group_key: Key of the group
            properties: Properties to set for the group
            
        Returns:
            bool: True if properties were set successfully
        """
        try:
            # Set group properties
            self.client.group_set(
                group_type=group_type,
                group_key=group_key,
                properties=properties,
            )
            
            logger.debug(f"Set properties for group: {group_type}:{group_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set PostHog group properties: {str(e)}")
            return False
    
    def group_increment(
        self,
        group_type: str,
        group_key: str,
        property_name: str,
        increment_by: int = 1,
    ) -> bool:
        """
        Increment a property for a group in PostHog.
        
        Args:
            group_type: Type of the group (e.g., 'organization')
            group_key: Key of the group
            property_name: Name of the property to increment
            increment_by: Amount to increment by
            
        Returns:
            bool: True if property was incremented successfully
        """
        try:
            # Increment group property
            self.client.group_increment(
                group_type=group_type,
                group_key=group_key,
                properties={property_name: increment_by},
            )
            
            logger.debug(f"Incremented property {property_name} for group: {group_type}:{group_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to increment PostHog group property: {str(e)}")
            return False

# Create a singleton instance
posthog_service = PostHogService() 