from django.db import models


class Job(models.Model):
    title = models.CharField(max_length=500)
    company = models.CharField(max_length=200)
    location = models.CharField(max_length=250, blank=True)
    posted_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    url = models.URLField(max_length=1000, unique=True)
    source = models.CharField(max_length=100, default='workday')
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-posted_date', '-last_seen', 'company', 'title']
        indexes = [
            models.Index(fields=['company']),
            models.Index(fields=['location']),
            models.Index(fields=['posted_date']),
            models.Index(fields=['title']),
        ]

    def __str__(self):
        return f"{self.company} | {self.title}"
