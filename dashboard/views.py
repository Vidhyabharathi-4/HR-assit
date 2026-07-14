import os
import re
import json
import base64
import requests
from django.shortcuts import render
from django.views.generic import TemplateView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Resume
from .parser import parse_resume

class IndexView(TemplateView):
    template_name = "dashboard/index.html"

class ResumeUploadAPI(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('resume')
        if not file_obj:
            return Response({"error": "No file uploaded"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Save file directly to a temporary Resume instance
        resume_instance = Resume(resume_file=file_obj)
        resume_instance.save()  # Saves file to media/resumes/
        
        # Parse the saved resume file
        file_path = resume_instance.resume_file.path
        try:
            parsed_data = parse_resume(file_path)
            
            # Update instance with parsed data
            resume_instance.candidate_name = parsed_data.get('candidate_name', 'Unknown')
            resume_instance.email = parsed_data.get('email', 'Unknown')
            resume_instance.phone = parsed_data.get('phone', 'Unknown')
            resume_instance.skills_data = parsed_data.get('skills_data', {})
            resume_instance.github_links = parsed_data.get('github_links', [])
            resume_instance.ai_summary = parsed_data.get('ai_summary', {})
            resume_instance.save()
            
            return Response({
                "id": resume_instance.id,
                "candidate_name": resume_instance.candidate_name,
                "email": resume_instance.email,
                "phone": resume_instance.phone,
                "uploaded_at": resume_instance.uploaded_at,
                "skills_data": resume_instance.skills_data,
                "github_links": resume_instance.github_links,
                "ai_summary": resume_instance.ai_summary
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            # Clean up if failed
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            resume_instance.delete()
            return Response({"error": f"Failed to parse resume: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ResumeListAPI(APIView):
    def get(self, request, *args, **kwargs):
        resumes = Resume.objects.all().order_by('-uploaded_at')
        data = [{
            "id": r.id,
            "candidate_name": r.candidate_name,
            "email": r.email,
            "uploaded_at": r.uploaded_at
        } for r in resumes]
        return Response(data, status=status.HTTP_200_OK)

class ResumeDetailAPI(APIView):
    def get(self, request, pk, *args, **kwargs):
        try:
            resume = Resume.objects.get(pk=pk)
            return Response({
                "id": resume.id,
                "candidate_name": resume.candidate_name,
                "email": resume.email,
                "phone": resume.phone,
                "uploaded_at": resume.uploaded_at,
                "skills_data": resume.skills_data,
                "github_links": resume.github_links,
                "ai_summary": resume.ai_summary
            }, status=status.HTTP_200_OK)
        except Resume.DoesNotExist:
            return Response({"error": "Resume not found"}, status=status.HTTP_404_NOT_FOUND)

class GithubProxyAPI(APIView):
    """
    Checks if a GitHub URL is valid and fetches metadata/README via the backend
    to bypass client CORS issues or load markdown contents safely.
    """
    def get(self, request, *args, **kwargs):
        repo_url = request.query_params.get('url')
        if not repo_url:
            return Response({"error": "No url parameter provided"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse owner and repo from url
        # Support matches: github.com/owner/repo or github.com/owner
        match = re.search(r'github\.com/([A-Za-z0-9_.-]+)(?:/([A-Za-z0-9_.-]+))?', repo_url)
        if not match:
            return Response({
                "is_valid": False, 
                "url": repo_url, 
                "message": "Invalid Github URL format"
            }, status=status.HTTP_200_OK)
            
        owner = match.group(1)
        repo = match.group(2)
        
        # If it's just a profile link, verify user exists
        if not repo:
            headers = {}
            token = os.environ.get("GITHUB_TOKEN")
            if token:
                headers["Authorization"] = f"token {token}"
            user_api_url = f"https://api.github.com/users/{owner}"
            try:
                resp = requests.get(user_api_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    user_data = resp.json()
                    return Response({
                        "is_valid": True,
                        "is_profile_only": True,
                        "url": repo_url,
                        "owner": owner,
                        "name": user_data.get("name", owner),
                        "bio": user_data.get("bio", ""),
                        "avatar_url": user_data.get("avatar_url", ""),
                        "public_repos": user_data.get("public_repos", 0),
                        "followers": user_data.get("followers", 0)
                    }, status=status.HTTP_200_OK)
                else:
                    return Response({
                        "is_valid": False,
                        "url": repo_url,
                        "message": f"Github user profile not found (Status {resp.status_code})"
                    }, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({
                    "is_valid": False,
                    "url": repo_url,
                    "message": f"Server error: {str(e)}"
                }, status=status.HTTP_200_OK)

        # Clean trailing .git or slashes
        repo = repo.replace('.git', '').rstrip('/')
        
        # Prepare requests headers (with optional Token)
        headers = {}
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"token {token}"
            
        repo_api_url = f"https://api.github.com/repos/{owner}/{repo}"
        
        try:
            # Fetch repo info
            repo_resp = requests.get(repo_api_url, headers=headers, timeout=10)
            if repo_resp.status_code == 404:
                return Response({
                    "is_valid": False,
                    "url": repo_url,
                    "message": "Repository not found (404)"
                }, status=status.HTTP_200_OK)
                
            if repo_resp.status_code != 200:
                return Response({
                    "is_valid": False,
                    "url": repo_url,
                    "message": f"Github returned status code {repo_resp.status_code}"
                }, status=status.HTTP_200_OK)
                
            repo_data = repo_resp.json()
            
            # Fetch README content
            readme_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
            readme_resp = requests.get(readme_url, headers=headers, timeout=10)
            
            readme_content = ""
            if readme_resp.status_code == 200:
                try:
                    content_b64 = readme_resp.json().get('content', '')
                    readme_content = base64.b64decode(content_b64).decode('utf-8')
                except Exception as b64_err:
                    print(f"Error decoding base64 readme: {b64_err}")
                    readme_content = "Failed to decode README content."
            else:
                readme_content = "# Project Documentation\nNo README.md found in this repository."
                
            # Fetch languages
            lang_url = f"https://api.github.com/repos/{owner}/{repo}/languages"
            lang_resp = requests.get(lang_url, headers=headers, timeout=10)
            languages = lang_resp.json() if lang_resp.status_code == 200 else {}
            
            return Response({
                "is_valid": True,
                "is_profile_only": False,
                "url": repo_url,
                "owner": owner,
                "repo": repo,
                "stars": repo_data.get("stargazers_count", 0),
                "forks": repo_data.get("forks_count", 0),
                "description": repo_data.get("description", ""),
                "languages": languages,
                "readme": readme_content,
                "avatar_url": repo_data.get("owner", {}).get("avatar_url", "")
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                "is_valid": False,
                "url": repo_url,
                "message": f"Server error verifying repository: {str(e)}"
            }, status=status.HTTP_200_OK)
