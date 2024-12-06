from typing import Dict, List, Optional
import json
import os
from datetime import datetime
from models import MeetingNote, FolderStructure
from slite_api import SliteAPI
from utils import logger, retry_with_backoff, Cache, ValidationError

class NoteManager:
    def __init__(self, notes_file: str = "note_registry.json"):
        self.notes_file = notes_file
        self.api = SliteAPI()
        self.cache = Cache('note_manager_cache.json')
        self.notes_registry = self._load_registry()
        self.folders_registry = self._load_folders_registry()

    def _load_registry(self) -> Dict:
        """Load the notes registry from file"""
        try:
            if not os.path.exists(self.notes_file):
                with open(self.notes_file, 'w') as f:
                    json.dump({}, f)
            with open(self.notes_file, 'r') as f:
                registry = json.load(f)
                # Ensure all required keys exist
                if "notes" not in registry:
                    registry["notes"] = {}
                if "folders" not in registry:
                    registry["folders"] = {}
                if "folder_hierarchy" not in registry:
                    registry["folder_hierarchy"] = {}
                return registry
        except Exception as e:
            logger.error(f"Error loading registry: {str(e)}")
            return {
                "notes": {},
                "folders": {},
                "folder_hierarchy": {}
            }

    def _load_folders_registry(self) -> Dict:
        """Load the folders registry from file"""
        try:
            if not os.path.exists(self.notes_file):
                with open(self.notes_file, 'w') as f:
                    json.dump({}, f)
            with open(self.notes_file, 'r') as f:
                registry = json.load(f)
                # Ensure all required keys exist
                if "folders" not in registry:
                    registry["folders"] = {}
                return registry["folders"]
        except Exception as e:
            logger.error(f"Error loading folders registry: {str(e)}")
            return {}

    def _save_registry(self):
        """Save the current state of the registry"""
        try:
            with open(self.notes_file, 'w') as f:
                json.dump(self.notes_registry, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving registry: {str(e)}")
            raise

    def _save_folders_registry(self):
        """Save the current state of the folders registry"""
        try:
            with open(self.notes_file, 'w') as f:
                json.dump(self.folders_registry, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving folders registry: {str(e)}")
            raise

    def _validate_note(self, note: MeetingNote):
        """Validate note data"""
        if not note.title:
            raise ValidationError("Note title is required")
        if not note.content:
            raise ValidationError("Note content is required")

    @retry_with_backoff(retries=3)
    def create_note(self, note: MeetingNote, parent_id: Optional[str] = None) -> Optional[str]:
        """Create a new note"""
        try:
            logger.info(f"Creating note: {note.title}")
            self._validate_note(note)
            
            response = self.api.create_note(note, parent_id)
            note_id = response.note_id
            
            # Update registry
            self.notes_registry["notes"][note_id] = {
                "id": note_id,
                "title": note.title,
                "created_at": datetime.now().isoformat(),
                "parent_id": parent_id,
                "project": note.project,
                "department": note.department
            }
            self._save_registry()
            
            # Update cache
            self.cache.set(f"note_{note_id}", {
                "title": note.title,
                "content": note.content,
                "folder_id": parent_id
            })
            
            return note_id
        except Exception as e:
            logger.error(f"Error creating note: {str(e)}")
            raise

    @retry_with_backoff(retries=3)
    def update_note(self, note_id: str, note: MeetingNote) -> bool:
        """Update an existing note"""
        try:
            logger.info(f"Updating note: {note_id}")
            self._validate_note(note)
            
            if note_id not in self.notes_registry["notes"]:
                raise ValidationError(f"Note {note_id} not found")
            
            response = self.api.update_note(note_id, note)
            
            # Update registry
            self.notes_registry["notes"][note_id].update({
                "title": note.title,
                "parent_id": note.parent_id,
                "updated_at": datetime.now().isoformat()
            })
            self._save_registry()
            
            # Update cache
            self.cache.set(f"note_{note_id}", {
                "title": note.title,
                "content": note.content,
                "folder_id": note.parent_id
            })
            
            return True
        except Exception as e:
            logger.error(f"Error updating note: {str(e)}")
            return False

    @retry_with_backoff(retries=3)
    def delete_note(self, note_id: str) -> bool:
        """Delete a note"""
        try:
            logger.info(f"Deleting note: {note_id}")
            if note_id not in self.notes_registry["notes"]:
                raise ValidationError(f"Note {note_id} not found")
            
            success = self.api.delete_note(note_id)
            if success:
                # Update registry
                del self.notes_registry["notes"][note_id]
                self._save_registry()
                
                # Clear cache
                self.cache.set(f"note_{note_id}", None)
            
            return success
        except Exception as e:
            logger.error(f"Error deleting note: {str(e)}")
            return False

    def get_note(self, note_id: str) -> Optional[Dict]:
        """Get a note by ID"""
        try:
            logger.info(f"Getting note: {note_id}")
            # Try cache first
            cached_note = self.cache.get(f"note_{note_id}")
            if cached_note:
                return cached_note
            
            note = self.api.get_note(note_id)
            if note:
                # Update cache
                self.cache.set(f"note_{note_id}", note)
            return note
        except Exception as e:
            logger.error(f"Error getting note: {str(e)}")
            return None

    @retry_with_backoff(retries=3)
    def create_folder(self, folder: FolderStructure) -> Optional[str]:
        """Create a new folder"""
        try:
            logger.info(f"Creating folder: {folder.name}")
            response = self.api.create_folder(folder)
            folder_id = response.folder_id
            
            # Update registry
            self.folders_registry[folder_id] = {
                "id": folder_id,
                "name": folder.name,
                "description": folder.description,
                "created_at": datetime.now().isoformat(),
                "parent_id": folder.parent_id
            }
            self._save_folders_registry()
            
            # Update folder hierarchy
            if folder.parent_id:
                if folder.parent_id not in self.notes_registry["folder_hierarchy"]:
                    self.notes_registry["folder_hierarchy"][folder.parent_id] = []
                self.notes_registry["folder_hierarchy"][folder.parent_id].append(folder_id)
            
            self._save_registry()
            
            return folder_id
        except Exception as e:
            logger.error(f"Error creating folder: {str(e)}")
            raise

    def update_folder(self, folder_id: str, folder: FolderStructure) -> bool:
        """Update a folder"""
        try:
            logger.info(f"Updating folder: {folder_id}")
            if folder_id not in self.folders_registry:
                raise ValidationError(f"Folder {folder_id} not found")
            
            response = self.api.update_folder(folder_id, folder)
            if response and response.status == "success":
                self.folders_registry[folder_id].update({
                    "name": folder.name,
                    "description": folder.description
                })
                self._save_folders_registry()
                return True
        except Exception as e:
            logger.error(f"Error updating folder: {str(e)}")
            return False

    def delete_folder(self, folder_id: str) -> bool:
        """Delete a folder and all its contents"""
        try:
            logger.info(f"Deleting folder: {folder_id}")
            if folder_id not in self.folders_registry:
                raise ValidationError(f"Folder {folder_id} not found")
            
            # First, delete all notes in the folder
            if folder_id in self.notes_registry["folder_hierarchy"]:
                for note_id in self.notes_registry["folder_hierarchy"][folder_id][:]:
                    self.delete_note(note_id)
            
            # Delete all subfolders recursively
            if folder_id in self.notes_registry["folder_hierarchy"]:
                for subfolder_id in self.notes_registry["folder_hierarchy"][folder_id][:]:
                    self.delete_folder(subfolder_id)
            
            # Delete the folder itself
            if self.api.delete_folder(folder_id):
                # Remove from parent's children list
                parent_id = self.folders_registry[folder_id]["parent_id"]
                if parent_id and parent_id in self.notes_registry["folder_hierarchy"]:
                    self.notes_registry["folder_hierarchy"][parent_id].remove(folder_id)
                
                # Clean up registry
                del self.folders_registry[folder_id]
                if folder_id in self.notes_registry["folder_hierarchy"]:
                    del self.notes_registry["folder_hierarchy"][folder_id]
                
                self._save_folders_registry()
                self._save_registry()
                return True
        except Exception as e:
            logger.error(f"Error deleting folder: {str(e)}")
            return False

    def get_folder(self, folder_id: str) -> Optional[Dict]:
        """Get folder details"""
        try:
            logger.info(f"Getting folder: {folder_id}")
            if folder_id not in self.folders_registry:
                raise ValidationError(f"Folder {folder_id} not found")
            
            folder_data = self.api.get_folder(folder_id)
            if folder_data:
                # Update registry with latest data
                self.folders_registry[folder_id].update({
                    "name": folder_data["title"],
                    "description": folder_data.get("content", "")
                })
                self._save_folders_registry()
                # Convert API response to our format
                return {
                    "id": folder_data["id"],
                    "name": folder_data["title"],
                    "description": folder_data.get("content", ""),
                    "parent_id": folder_data.get("parentNoteId")
                }
        except Exception as e:
            logger.error(f"Error getting folder: {str(e)}")
            return None

    def list_subfolders(self, parent_id: Optional[str] = None) -> List[Dict]:
        """List all subfolders of a parent folder"""
        try:
            logger.info(f"Listing subfolders of parent: {parent_id}")
            if parent_id is None:
                # Return top-level folders
                return [
                    folder for folder in self.folders_registry.values()
                    if not folder["parent_id"]
                ]
            elif parent_id in self.notes_registry["folder_hierarchy"]:
                return [
                    self.folders_registry[folder_id]
                    for folder_id in self.notes_registry["folder_hierarchy"][parent_id]
                    if folder_id in self.folders_registry
                ]
        except Exception as e:
            logger.error(f"Error listing subfolders: {str(e)}")
            return []

    def get_folder_path(self, folder_id: str) -> List[Dict]:
        """Get the path from root to the specified folder"""
        try:
            logger.info(f"Getting folder path: {folder_id}")
            path = []
            current_id = folder_id
            
            while current_id and current_id in self.folders_registry:
                folder = self.folders_registry[current_id]
                path.insert(0, folder)
                current_id = folder["parent_id"]
            
            return path
        except Exception as e:
            logger.error(f"Error getting folder path: {str(e)}")
            return []

    def list_folder_notes(self, folder_id: str) -> List[Dict]:
        """List all notes in a specific folder"""
        try:
            logger.info(f"Listing notes in folder: {folder_id}")
            if folder_id in self.notes_registry["folders"]:
                notes = []
                for note_id in self.notes_registry["folders"][folder_id]:
                    note_info = self.notes_registry["notes"].get(note_id)
                    if note_info:
                        notes.append(note_info)
                return notes
        except Exception as e:
            logger.error(f"Error listing folder notes: {str(e)}")
            return []

    def list_all_notes(self) -> List[Dict]:
        """List all tracked notes"""
        try:
            logger.info("Listing all notes")
            return list(self.notes_registry["notes"].values())
        except Exception as e:
            logger.error(f"Error listing all notes: {str(e)}")
            return []

    def search_notes(self, query: str) -> List[Dict]:
        """Search notes by title, project, or department"""
        try:
            logger.info(f"Searching notes with query: {query}")
            query = query.lower()
            results = []
            for note_info in self.notes_registry["notes"].values():
                if (query in note_info["title"].lower() or
                    (note_info["project"] and query in note_info["project"].lower()) or
                    (note_info["department"] and query in note_info["department"].lower())):
                    results.append(note_info)
            return results
        except Exception as e:
            logger.error(f"Error searching notes: {str(e)}")
            return []
