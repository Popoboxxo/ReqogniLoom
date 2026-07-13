import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'reqflow.settings')
django.setup()
from django.test import Client
c = Client()
r = c.get('/admin/login/')
print('GET /admin/login/ status:', r.status_code)
r = c.post('/admin/login/', {'username': 'admin', 'password': 'admin12345', 'next': '/admin/'}, follow=True)
print('POST /admin/login/ status:', r.status_code)
print('Redirect chain:', r.redirect_chain)
needle = b"Django administration"
print('Body contains needle:', needle in r.content)
print('Body length:', len(r.content), 'bytes')
