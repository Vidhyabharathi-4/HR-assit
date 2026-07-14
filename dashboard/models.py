from django.db import models

# Create your models here.
class Resume(models.Model):
    candidate_name = models.CharField(max_length=255, blank=True, null=True)
    email = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    resume_file = models.FileField(upload_to='resumes/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    skills_data = models.JSONField(blank=True, null=True)  # structure: {"nodes": [...], "edges": [...]}
    github_links = models.JSONField(blank=True, null=True)  # list of strings: ["https://github.com/user/repo", ...]
    ai_summary = models.JSONField(blank=True, null=True)    # structure: {"summary": "", "strengths": [...], "suited_roles": [...], "red_flags": [...]}

    def __str__(self):
        return self.candidate_name or f"Resume {self.id}"
