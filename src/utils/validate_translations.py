"""
Filename: validate_translations.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Translation validation script.

This script validates translation files against the template to ensure
all required keys are present and properly formatted.
"""

import yaml
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

def load_yaml(file_path: str) -> Dict[str, Any]:
    """Load YAML file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"{Fore.RED}Error loading {file_path}: {e}")
        return {}

def get_all_keys(data: Dict[str, Any], prefix: str = "", required_sections: Set[str] = None) -> List[str]:
    """Get all keys from nested dictionary
    
    Args:
        data: Dictionary to extract keys from
        prefix: Current key prefix for nested keys
        required_sections: Set of section names that must be present
        
    Returns:
        List of all keys in dot notation
    """
    keys = []
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        
        # Check if this is a required section
        if required_sections and key in required_sections:
            if not isinstance(value, dict):
                print(f"{Fore.RED}⚠️ Section {key} should be a dictionary")
                continue
                
        if isinstance(value, dict):
            keys.extend(get_all_keys(value, full_key))
        else:
            keys.append(full_key)
    return keys

def validate_translation(template_data: Dict[str, Any], translation_data: Dict[str, Any], lang_code: str) -> Tuple[List[str], List[str], List[str]]:
    """Validate translation against template
    
    Args:
        template_data: Template data to validate against
        translation_data: Translation data to validate
        lang_code: Language code being validated
        
    Returns:
        Tuple of (missing_keys, extra_keys, format_errors)
    """
    template_keys = get_all_keys(template_data["template"])
    translation_keys = get_all_keys(translation_data.get(lang_code, {}))
    
    # Find missing and extra keys
    missing_keys = [key for key in template_keys if key not in translation_keys]
    extra_keys = [key for key in translation_keys if key not in template_keys]
    
    # Check format strings
    format_errors = []
    for key in translation_keys:
        template_value = get_nested_value(template_data["template"], key)
        trans_value = get_nested_value(translation_data[lang_code], key)
        
        if isinstance(template_value, str) and isinstance(trans_value, str):
            template_placeholders = get_format_placeholders(template_value)
            trans_placeholders = get_format_placeholders(trans_value)
            
            if template_placeholders != trans_placeholders:
                format_errors.append(f"{key}: Mismatched placeholders - expected {template_placeholders}, got {trans_placeholders}")
    
    return missing_keys, extra_keys, format_errors

def get_nested_value(data: Dict[str, Any], key: str) -> Any:
    """Get value from nested dictionary using dot notation key"""
    current = data
    for part in key.split('.'):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current

def get_format_placeholders(text: str) -> Set[str]:
    """Extract format string placeholders from text"""
    return set(re.findall(r'%{(\w+)}', text))

def check_emoji_consistency(template_data: Dict[str, Any], translations: Dict[str, Dict[str, Any]]) -> List[str]:
    """Check emoji consistency across translations"""
    errors = []
    emoji_pattern = r'[\U0001F300-\U0001F9FF]'
    
    for key, value in template_data["template"].items():
        if isinstance(value, str) and re.search(emoji_pattern, value):
            for lang_code, trans in translations.items():
                trans_value = get_nested_value(trans[lang_code], key)
                if isinstance(trans_value, str) and not re.search(emoji_pattern, trans_value):
                    errors.append(f"Missing emoji in {lang_code} for key {key}")
    
    return errors

def main():
    """Main validation function"""
    print(f"{Fore.CYAN}🔍 Validating translation files...")
    
    # Load template
    template_path = "translations/addarr.template.yml"
    template_data = load_yaml(template_path)
    if not template_data:
        print(f"{Fore.RED}❌ Failed to load template file")
        return
    
    # Required sections that must be dictionaries
    required_sections = {
        "messages", "searchresults", "Transmission", "Sabnzbd", 
        "Error", "SystemStatus", "Notifications"
    }
    
    # Get all translation files
    translations_dir = Path("translations")
    translation_files = translations_dir.glob("addarr.*.yml")
    
    all_valid = True
    translations = {}
    
    for file in translation_files:
        if file.name == "addarr.template.yml":
            continue
            
        lang_code = file.stem.split('.')[1]
        print(f"\n{Fore.CYAN}Checking {lang_code} translation...")
        
        translation_data = load_yaml(str(file))
        if not translation_data:
            print(f"{Fore.RED}❌ Failed to load {file}")
            all_valid = False
            continue
            
        translations[lang_code] = translation_data
        
        missing_keys, extra_keys, format_errors = validate_translation(
            template_data, translation_data, lang_code
        )
        
        if missing_keys:
            print(f"{Fore.YELLOW}⚠️ Missing keys in {lang_code}:")
            for key in missing_keys:
                print(f"  • {key}")
            all_valid = False
            
        if extra_keys:
            print(f"{Fore.YELLOW}⚠️ Extra keys in {lang_code}:")
            for key in extra_keys:
                print(f"  • {key}")
            all_valid = False
            
        if format_errors:
            print(f"{Fore.YELLOW}⚠️ Format errors in {lang_code}:")
            for error in format_errors:
                print(f"  • {error}")
            all_valid = False
            
        if not missing_keys and not extra_keys and not format_errors:
            print(f"{Fore.GREEN}✅ {lang_code} translation is valid")
            
    # Check emoji consistency
    emoji_errors = check_emoji_consistency(template_data, translations)
    if emoji_errors:
        print(f"\n{Fore.YELLOW}⚠️ Emoji consistency issues:")
        for error in emoji_errors:
            print(f"  • {error}")
        all_valid = False
            
    if all_valid:
        print(f"\n{Fore.GREEN}✅ All translations are valid!")
    else:
        print(f"\n{Fore.YELLOW}⚠️ Some translations need attention")
        print("Run this script again after fixing the issues")

if __name__ == "__main__":
    main()