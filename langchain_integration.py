from typing import Dict, List, Optional, Union
import openai
from note_manager import NoteManager
from models import MeetingNote, FolderStructure
import json
import os
from dotenv import load_dotenv

load_dotenv()

class SliteNoteManager:
    def __init__(self, openai_api_key: Optional[str] = None):
        if openai_api_key is None:
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                raise ValueError("OpenAI API key is required")
        
        self.note_manager = NoteManager()
        openai.api_key = openai_api_key
    
    def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API with the given prompt"""
        try:
            response = openai.Completion.create(
                model="gpt-3.5-turbo-instruct",
                prompt=prompt,
                max_tokens=1000,
                temperature=0.5,
                stop=None
            )
            return response.choices[0].text.strip()
        except Exception as e:
            print(f"Error calling OpenAI API: {str(e)}")
            return ""
    
    def process_meeting_notes(self, meeting_notes: str, folder_id: Optional[str] = None) -> str:
        """Process meeting notes and create a well-structured note in Slite"""
        prompt = f"""
        Process these meeting notes and create a well-structured note with the following sections:
        - Summary
        - Action Items
        - Decisions Made
        - Next Steps
        
        Meeting Notes:
        {meeting_notes}
        
        Format the output in markdown.
        """
        
        structured_content = self._call_openai(prompt)
        if not structured_content:
            return "Failed to process meeting notes"
        
        # Create note in Slite
        note = MeetingNote(
            title=f"Meeting Notes - {structured_content.split('\\n')[0]}",
            content=structured_content,
            folder_id=folder_id
        )
        note_id = self.note_manager.create_note(note)
        
        return f"Created note with ID: {note_id}"
    
    def organize_content(self, content: str, parent_folder_id: Optional[str] = None) -> str:
        """Organize content into appropriate folders"""
        prompt = f"""
        Analyze this content and suggest a folder structure with appropriate titles and descriptions:
        
        Content:
        {content}
        
        Format the output as a JSON structure like this:
        {{
            "folders": [
                {{
                    "name": "folder name",
                    "description": "folder description",
                    "parent_id": null,
                    "subfolders": [
                        {{
                            "name": "subfolder name",
                            "description": "subfolder description"
                        }}
                    ]
                }}
            ]
        }}
        """
        
        structure_suggestion = self._call_openai(prompt)
        if not structure_suggestion:
            return "Failed to organize content"
        
        try:
            structure = json.loads(structure_suggestion)
            created_folders = []
            
            def create_folder_structure(folders, parent_id=None):
                for folder_data in folders:
                    folder = FolderStructure(
                        name=folder_data["name"],
                        description=folder_data.get("description", ""),
                        parent_id=parent_id or parent_folder_id
                    )
                    folder_id = self.note_manager.create_folder(folder)
                    created_folders.append({
                        "id": folder_id,
                        "name": folder_data["name"]
                    })
                    
                    if "subfolders" in folder_data:
                        create_folder_structure(folder_data["subfolders"], folder_id)
            
            create_folder_structure(structure["folders"])
            return f"Created folders: {json.dumps(created_folders, indent=2)}"
        except Exception as e:
            return f"Error creating folder structure: {str(e)}"
    
    def search_and_update(self, query: str, update_content: str) -> str:
        """Search for notes matching the query and update them"""
        prompt = f"""
        Given this update content, generate a summary of changes to be made:
        
        Update Content:
        {update_content}
        
        Format the output as:
        1. Summary of changes
        2. Updated content in markdown
        """
        
        update_suggestion = self._call_openai(prompt)
        if not update_suggestion:
            return "Failed to process update"
        
        # Search for notes
        results = self.note_manager.search_notes(query)
        if not results:
            return "No notes found matching the query"
        
        updates_made = []
        for result in results:
            note = MeetingNote(
                title=result["title"],
                content=update_suggestion.split("2. Updated content")[1].strip(),
                folder_id=result.get("folder_id")
            )
            success = self.note_manager.update_note(result["id"], note)
            if success:
                updates_made.append(result["title"])
        
        return f"Updated notes: {', '.join(updates_made)}"
