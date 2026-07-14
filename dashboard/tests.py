import os
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import Resume

class ResumeDashboardTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Paths for sample files
        self.test_pdf_content = b"%PDF-1.4 test pdf content with John Doe email: john.doe@example.com phone: 1234567890 github: github.com/octocat/Spoon-Knife. Core skills: python django postgresql docker."
        
    def test_resume_upload_and_parsing(self):
        """Tests that uploading a PDF parses the content, creates a database entry, and extracts data correctly."""
        url = reverse('api_resume_upload')
        uploaded_file = SimpleUploadedFile(
            "test_resume.pdf", 
            self.test_pdf_content, 
            content_type="application/pdf"
        )
        
        # Patch the actual PDF text extraction to return predefined text so we don't rely on PyMuPDF file reading bugs
        with patch('dashboard.parser.extract_text_from_pdf') as mock_extract:
            mock_extract.return_value = "John Doe\nEmail: john.doe@example.com\nPhone: 1234567890\nGitHub: github.com/octocat/Spoon-Knife\nSkills: python, django, postgresql, docker."
            
            response = self.client.post(url, {'resume': uploaded_file})
            
            self.assertEqual(response.status_code, 201)
            response_data = response.json()
            
            # Assert DB record created
            self.assertEqual(Resume.objects.count(), 1)
            resume = Resume.objects.first()
            
            # Assert details parsed correctly
            self.assertEqual(resume.candidate_name, "John Doe")
            self.assertEqual(resume.email, "john.doe@example.com")
            self.assertEqual(resume.phone, "1234567890")
            self.assertIn("https://github.com/octocat/spoon-knife", resume.github_links)
            
            # Check JSON response elements
            self.assertEqual(response_data['candidate_name'], "John Doe")
            self.assertEqual(response_data['email'], "john.doe@example.com")
            self.assertIn("skills_data", response_data)
            self.assertIn("ai_summary", response_data)

    def test_resume_list_api(self):
        """Tests listing all candidates profiles."""
        Resume.objects.create(
            candidate_name="Alice Smith",
            email="alice@example.com",
            phone="987654321",
            skills_data={"nodes": [], "edges": []},
            github_links=[],
            ai_summary={}
        )
        Resume.objects.create(
            candidate_name="Bob Jones",
            email="bob@example.com",
            phone="111222333",
            skills_data={"nodes": [], "edges": []},
            github_links=[],
            ai_summary={}
        )
        
        url = reverse('api_resume_list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['candidate_name'], "Bob Jones") # Sorted by uploaded_at desc
        self.assertEqual(data[1]['candidate_name'], "Alice Smith")

    def test_resume_detail_api(self):
        """Tests getting details of a specific candidate profile."""
        resume = Resume.objects.create(
            candidate_name="Alice Smith",
            email="alice@example.com",
            phone="987654321",
            skills_data={"nodes": [{"id": "python", "label": "Python"}], "edges": []},
            github_links=["https://github.com/alice/my-app"],
            ai_summary={"summary": "Alice summary", "strengths": ["Quick learner"]}
        )
        
        url = reverse('api_resume_detail', kwargs={'pk': resume.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['candidate_name'], "Alice Smith")
        self.assertEqual(data['email'], "alice@example.com")
        self.assertEqual(data['skills_data']['nodes'][0]['label'], "Python")
        self.assertIn("https://github.com/alice/my-app", data['github_links'])

    @patch('requests.get')
    def test_github_proxy_api(self, mock_get):
        """Tests checking repository statistics and readme fetching through proxy API."""
        url = reverse('api_github_check')
        
        # Configure mocked response object for repository details and readme
        class MockResponse:
            def __init__(self, json_data, status_code):
                self.json_data = json_data
                self.status_code = status_code
                self.text = "raw text"
            
            def json(self):
                return self.json_data

        # We will mock requests.get to return fake response data
        # First call is repository info, second call is readme, third is languages
        mock_get.side_effect = [
            MockResponse({
                "stargazers_count": 42,
                "forks_count": 7,
                "description": "Octocat's Spoon-Knife project",
                "owner": {"avatar_url": "https://avatars.githubusercontent.com/u/583234?v=4"}
            }, 200),
            MockResponse({
                "content": "IyBTcG9vbi1LbmlmZQpUaGlzIGlzIGEgZmFrZSByZWFkbWU="  # Base64 for "# Spoon-Knife\nThis is a fake readme"
            }, 200),
            MockResponse({
                "HTML": 12000,
                "CSS": 8000
            }, 200)
        ]
        
        response = self.client.get(url, {'url': 'https://github.com/octocat/Spoon-Knife'})
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertTrue(data['is_valid'])
        self.assertEqual(data['owner'], 'octocat')
        self.assertEqual(data['repo'], 'Spoon-Knife')
        self.assertEqual(data['stars'], 42)
        self.assertEqual(data['forks'], 7)
        self.assertEqual(data['languages']['HTML'], 12000)
        self.assertIn("This is a fake readme", data['readme'])
