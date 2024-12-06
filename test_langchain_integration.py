import unittest
from langchain_integration import SliteNoteManager
import os
from dotenv import load_dotenv

load_dotenv()

class TestSliteNoteManager(unittest.TestCase):
    def setUp(self):
        self.manager = SliteNoteManager()
    
    def test_process_meeting_notes(self):
        notes = """
        Project Kickoff Meeting
        Date: 2023-11-15
        
        Discussion:
        - Reviewed project goals and timeline
        - Assigned initial tasks to team members
        - Discussed potential risks and mitigation strategies
        
        Next Steps:
        1. Create project documentation
        2. Set up development environment
        3. Schedule weekly check-ins
        """
        
        result = self.manager.process_meeting_notes(notes)
        self.assertIsInstance(result, str)
        self.assertTrue("Created note with ID:" in result)
    
    def test_organize_content(self):
        content = """
        Technical Documentation:
        - System Architecture
        - API Documentation
        - Database Schema
        
        Project Management:
        - Sprint Planning
        - Team Updates
        - Risk Register
        """
        
        result = self.manager.organize_content(content)
        self.assertIsInstance(result, str)
        self.assertTrue("Created folders:" in result)
    
    def test_search_and_update(self):
        query = "Project Kickoff"
        update_content = """
        Updated project timeline:
        - Phase 1: Requirements (2 weeks)
        - Phase 2: Development (6 weeks)
        - Phase 3: Testing (2 weeks)
        - Phase 4: Deployment (1 week)
        """
        
        result = self.manager.search_and_update(query, update_content)
        self.assertIsInstance(result, str)

if __name__ == "__main__":
    unittest.main()
