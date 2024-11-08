"""
Filename: states.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Conversation states for the bot handlers
"""

class States:
    """States for conversation handlers"""
    
    # Media states
    SEARCHING = 1
    SELECTING = 2
    QUALITY_SELECT = 3
    SEASON_SELECT = 4
    
    # Delete states
    AWAITING_DELETE_CONFIRMATION = "awaiting_delete_confirmation"
    
    # System states
    AWAITING_STATUS_ACTION = "awaiting_status_action"
    AWAITING_SETTING_ACTION = "awaiting_setting_action"
    AWAITING_SPEED_INPUT = "awaiting_speed_input"
    
    # Auth states
    PASSWORD = 0
    
    # General states
    END = "end"