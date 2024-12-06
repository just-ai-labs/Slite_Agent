import os
import requests
from dotenv import load_dotenv
from datetime import datetime
from models import MeetingNote, FolderStructure, NoteResponse, FolderResponse
from typing import Optional, List, Dict
import json
from utils import (
    logger, retry_with_backoff, Cache, APIError, RateLimitError,
    AuthenticationError, NotFoundError, ValidationError
)

# Load environment variables
load_dotenv()

class SliteAPI:
    def __init__(self):
        self.api_key = os.getenv('SLITE_API_KEY')
        self.base_url = 'https://api.slite.com/v1'
        self.cache = Cache()
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'x-slite-api-key': self.api_key
        }
        
    def _handle_response(self, response: requests.Response) -> Dict:
        """Handle API response and raise appropriate errors"""
        try:
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                raise RateLimitError("API rate limit exceeded", response.status_code)
            elif response.status_code == 401:
                raise AuthenticationError("Invalid API key", response.status_code)
            elif response.status_code == 404:
                raise NotFoundError("Resource not found", response.status_code)
            elif response.status_code == 400:
                raise ValidationError("Invalid request", response.status_code)
            else:
                raise APIError(f"API request failed: {response.text}", response.status_code)
        except json.JSONDecodeError:
            raise APIError("Invalid JSON response from API")

    @retry_with_backoff(retries=3)
    def test_connection(self):
        """Test the API connection using a known document ID"""
        test_doc_id = "lRzWKw9G6XtOUT"  # Using the Agent_Integration document
        try:
            response = requests.get(
                f'{self.base_url}/notes/{test_doc_id}',
                headers=self.headers
            )
            data = self._handle_response(response)
            return data
        except requests.exceptions.RequestException as e:
            print(f"Error connecting to Slite API: {e}")
            return None

    @retry_with_backoff(retries=3)
    def create_note(self, note: MeetingNote, parent_note_id: Optional[str] = None) -> NoteResponse:
        """Create a new note"""
        try:
            # Prepare the content in the correct format
            content = f"# {note.title}\n\n{note.content}"
            if note.project:
                content += f"\n\n## Project\n{note.project}"
            if note.department:
                content += f"\n\n## Department\n{note.department}"
            if note.participants:
                content += f"\n\n## Participants\n" + "\n".join([f"- {p}" for p in note.participants])
            if note.tags:
                content += f"\n\n## Tags\n" + ", ".join(note.tags)
            
            payload = {
                "title": note.title,
                "content": content
            }
            if parent_note_id:
                payload["parentNoteId"] = parent_note_id
            
            response = requests.post(
                f'{self.base_url}/notes',
                headers=self.headers,
                json=payload
            )
            data = self._handle_response(response)
            
            return NoteResponse(
                note_id=data["id"],
                title=data["title"],
                folder_id=parent_note_id,
                created_at=datetime.now(),
                updated_at=datetime.fromisoformat(data["updatedAt"].replace("Z", "+00:00")),
                status="success"
            )
        except requests.exceptions.RequestException as e:
            print(f"Error creating note: {e}")
            return NoteResponse(
                note_id="",
                title=note.title,
                status="error",
                message=str(e),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )

    @retry_with_backoff(retries=3)
    def update_note(self, note_id: str, note: MeetingNote) -> NoteResponse:
        """Update an existing note"""
        try:
            # Prepare the content in the correct format
            content = f"# {note.title}\n\n{note.content}"
            if note.project:
                content += f"\n\n## Project\n{note.project}"
            if note.department:
                content += f"\n\n## Department\n{note.department}"
            if note.participants:
                content += f"\n\n## Participants\n" + "\n".join([f"- {p}" for p in note.participants])
            if note.tags:
                content += f"\n\n## Tags\n" + ", ".join(note.tags)
            
            payload = {
                "title": note.title,
                "content": content
            }
            
            response = requests.put(
                f'{self.base_url}/notes/{note_id}',
                headers=self.headers,
                json=payload
            )
            data = self._handle_response(response)
            
            return NoteResponse(
                note_id=data["id"],
                title=data["title"],
                folder_id=data.get("parentNoteId"),
                created_at=datetime.now(),
                updated_at=datetime.fromisoformat(data["updatedAt"].replace("Z", "+00:00")),
                status="success"
            )
        except requests.exceptions.RequestException as e:
            print(f"Error updating note: {e}")
            return NoteResponse(
                note_id=note_id,
                title=note.title,
                status="error",
                message=str(e),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )

    @retry_with_backoff(retries=3)
    def get_note(self, note_id: str) -> Optional[Dict]:
        """Get a specific note by ID"""
        cache_key = f"note_{note_id}"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            return cached_data

        try:
            response = requests.get(
                f'{self.base_url}/notes/{note_id}',
                headers=self.headers
            )
            data = self._handle_response(response)
            self.cache.set(cache_key, data)
            return data
        except requests.exceptions.RequestException as e:
            print(f"Error getting note: {e}")
            return None

    @retry_with_backoff(retries=3)
    def delete_note(self, note_id: str) -> bool:
        """Delete a note"""
        try:
            # Try direct deletion first
            response = requests.delete(
                f'{self.base_url}/notes/{note_id}',
                headers=self.headers,
                json={"archived": True}  # Add archived flag in the payload
            )
            data = self._handle_response(response)
            
            # Clear cache
            cache_key = f"note_{note_id}"
            self.cache.set(cache_key, None)
            
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error deleting note: {e}")
            return False

    @retry_with_backoff(retries=3)
    def list_notes(self, parent_id: Optional[str] = None) -> List[Dict]:
        """
        List notes. Note: The Slite API has limitations on listing all notes.
        It's recommended to:
        1. Keep track of note IDs when creating notes
        2. Use get_note() to fetch specific notes
        3. Provide a parent_id to list notes within a specific folder
        """
        try:
            if parent_id:
                # If parent_id is provided, try to get notes within that folder
                response = requests.get(
                    f'{self.base_url}/notes/{parent_id}/children',
                    headers=self.headers
                )
                data = self._handle_response(response)
                return data
            else:
                print("Warning: Listing all notes is not supported by the Slite API.")
                print("Please provide a parent_id to list notes within a specific folder,")
                print("or use get_note() to fetch specific notes by their IDs.")
                return []
        except requests.exceptions.RequestException as e:
            print(f"Error listing notes: {e}")
            return []

    @retry_with_backoff(retries=3)
    def update_block(self, doc_id: str, block_id: str, title: str, content: str, status: Optional[Dict] = None, url: Optional[str] = None) -> Dict:
        """Update a block in a document"""
        try:
            payload = {
                "title": title,
                "content": content
            }
            if status:
                payload["status"] = status
            if url:
                payload["url"] = url

            response = requests.put(
                f'{self.base_url}/notes/{doc_id}/tiles/{block_id}',
                headers=self.headers,
                json=payload
            )
            data = self._handle_response(response)
            return data
        except requests.exceptions.RequestException as e:
            print(f"Error updating block: {e}")
            return None

    # Folder Management Methods
    @retry_with_backoff(retries=3)
    def create_folder(self, folder: FolderStructure) -> FolderResponse:
        """Create a new folder"""
        try:
            payload = {
                "title": folder.name,  # Changed from name to title
                "content": folder.description or ""  # Changed from description to content
            }
            if folder.parent_id:
                payload["parentNoteId"] = folder.parent_id
            
            # Use the notes endpoint instead of folders
            response = requests.post(
                f'{self.base_url}/notes',
                headers=self.headers,
                json=payload
            )
            data = self._handle_response(response)
            
            return FolderResponse(
                folder_id=data["id"],
                name=data["title"],  # Changed from name to title
                created_at=datetime.now(),
                updated_at=datetime.fromisoformat(data["updatedAt"].replace("Z", "+00:00")),
                status="success",
                parent_id=folder.parent_id
            )
        except requests.exceptions.RequestException as e:
            print(f"Error creating folder: {e}")
            return FolderResponse(
                folder_id="",
                name=folder.name,
                status="error",
                message=str(e),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )

    @retry_with_backoff(retries=3)
    def update_folder(self, folder_id: str, folder: FolderStructure) -> FolderResponse:
        """Update an existing folder"""
        try:
            payload = {
                "title": folder.name,  # Changed from name to title
                "content": folder.description or ""  # Changed from description to content
            }
            
            response = requests.put(
                f'{self.base_url}/notes/{folder_id}',
                headers=self.headers,
                json=payload
            )
            data = self._handle_response(response)
            
            return FolderResponse(
                folder_id=data["id"],
                name=data["title"],  # Changed from name to title
                created_at=datetime.now(),
                updated_at=datetime.fromisoformat(data["updatedAt"].replace("Z", "+00:00")),
                status="success",
                parent_id=folder.parent_id
            )
        except requests.exceptions.RequestException as e:
            print(f"Error updating folder: {e}")
            return FolderResponse(
                folder_id=folder_id,
                name=folder.name,
                status="error",
                message=str(e),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )

    @retry_with_backoff(retries=3)
    def delete_folder(self, folder_id: str) -> bool:
        """Delete a folder"""
        try:
            response = requests.delete(
                f'{self.base_url}/notes/{folder_id}',
                headers=self.headers
            )
            
            # Clear cache
            cache_key = f"folder_{folder_id}"
            self.cache.set(cache_key, None)
            
            return response.status_code == 204
        except requests.exceptions.RequestException as e:
            print(f"Error deleting folder: {e}")
            return False

    @retry_with_backoff(retries=3)
    def get_folder(self, folder_id: str) -> Optional[Dict]:
        """Get a folder by ID"""
        cache_key = f"folder_{folder_id}"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            return cached_data

        try:
            response = requests.get(
                f'{self.base_url}/notes/{folder_id}',
                headers=self.headers
            )
            data = self._handle_response(response)
            self.cache.set(cache_key, data)
            return data
        except requests.exceptions.RequestException as e:
            print(f"Error getting folder: {e}")
            return None

if __name__ == "__main__":
    # Test the API connection
    slite = SliteAPI()
    
    print("Testing Slite API connection...")
    result = slite.test_connection()
    if result:
        print("Successfully connected to Slite API!")
        print(f"Notes: {result}")
    else:
        print("Failed to connect to Slite API. Please check your API key and internet connection.")
